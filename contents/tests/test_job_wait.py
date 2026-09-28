"""
Unit tests for job-wait.py.

job-wait.py has a hyphenated filename, so it is loaded with importlib. It does
"import common", which resolves through the inserted sys.path to a module object
distinct from contents.common, so patches target job_wait.common.
"""

import importlib
import os
import sys
import unittest

from types import SimpleNamespace
from unittest.mock import patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

job_wait = importlib.import_module('job-wait')


def job(completed=False, succeeded=None):
    return SimpleNamespace(status=SimpleNamespace(
        conditions=None,
        completion_time='2026-09-27T20:40:00Z' if completed else None,
        succeeded=succeeded))


RUNNING = job()
SUCCEEDED = job(completed=True, succeeded=1)


def pods(*names):
    return SimpleNamespace(items=[
        SimpleNamespace(metadata=SimpleNamespace(name=name)) for name in names])


class LogStream:
    """Stands in for the urllib3 response that read_namespaced_pod_log
    returns with _preload_content=False: iterating it yields lines."""

    def __init__(self, lines):
        self.lines = [line.encode() + b'\n' for line in lines]
        self.released = False

    def __iter__(self):
        return iter(self.lines)

    def close(self):
        pass

    def release_conn(self):
        self.released = True


class TestParseLogTimestamp(unittest.TestCase):

    def test_orders_stamps_whose_fractions_have_different_lengths(self):
        # The kubelet trims trailing zeros, so neither the strings nor the
        # fractions read as plain integers sort in time order.
        self.assertLess(job_wait.parse_log_timestamp('2026-09-27T20:33:41.12Z'),
                        job_wait.parse_log_timestamp('2026-09-27T20:33:41.123456789Z'))
        self.assertLess(job_wait.parse_log_timestamp('2026-09-27T20:33:41.45Z'),
                        job_wait.parse_log_timestamp('2026-09-27T20:33:41.5Z'))

    def test_accepts_a_stamp_without_a_fraction(self):
        self.assertLess(job_wait.parse_log_timestamp('2026-09-27T20:33:41Z'),
                        job_wait.parse_log_timestamp('2026-09-27T20:33:41.000000001Z'))

    def test_compares_stamps_with_different_offsets(self):
        self.assertEqual(job_wait.parse_log_timestamp('2026-09-27T22:33:41.5+02:00'),
                         job_wait.parse_log_timestamp('2026-09-27T20:33:41.5Z'))

    def test_returns_none_for_text_that_is_not_a_stamp(self):
        self.assertIsNone(job_wait.parse_log_timestamp('PLAY'))
        self.assertIsNone(job_wait.parse_log_timestamp(''))


class TestWait(unittest.TestCase):

    def setUp(self):
        os.environ.clear()
        os.environ.update({
            'RD_CONFIG_NAME': 'my-job',
            'RD_CONFIG_NAMESPACE': 'default',
            'RD_CONFIG_RETRIES': '10',
            'RD_CONFIG_SLEEP': '1',
            'RD_CONFIG_SHOW_LOG': 'true',
        })

    def run_wait(self, passes, statuses):
        """Run wait(). Each time round its loop, the log stream yields the
        next entry of passes and the Job status is the next entry of statuses.
        Returns the pod log lines printed, in order."""
        self.streams = [LogStream(p) for p in passes]
        streams = iter(self.streams)

        def read_log(**kwargs):
            # Without follow it is the check that the log can be read yet.
            return next(streams) if kwargs.get('follow') else ''

        with patch.object(job_wait.common, 'connect'), \
                patch.object(job_wait.time, 'sleep'), \
                patch.object(job_wait.client, 'CoreV1Api') as core, \
                patch.object(job_wait.client, 'BatchV1Api') as batch, \
                self.assertLogs('kubernetes-wait-job', level='INFO') as logs, \
                self.assertRaises(SystemExit) as exited:
            core.return_value.list_namespaced_pod.return_value = pods('my-job-abcde')
            core.return_value.read_namespaced_pod_log.side_effect = read_log
            batch.return_value.read_namespaced_job.side_effect = statuses
            job_wait.wait()

        self.exit_code = exited.exception.code
        self.stream_calls = [
            c for c in core.return_value.read_namespaced_pod_log.call_args_list
            if c.kwargs.get('follow')]
        self.log_output = logs.output
        # Pod log lines are the only records logged as bytes.
        return [r.msg.decode() for r in logs.records if isinstance(r.msg, bytes)]

    def test_prints_the_log_once_when_the_job_completes_after_the_stream_ends(self):
        # The container exits, ending the stream, a moment before the Job
        # controller sets completion_time, so the loop streams the log again.
        log = ['2026-09-27T20:33:41.1Z PLAY [all]',
               '2026-09-27T20:33:42.2Z PLAY RECAP']

        printed = self.run_wait([log, log], [RUNNING, SUCCEEDED])

        self.assertEqual(['PLAY [all]', 'PLAY RECAP'], printed)
        self.assertEqual(2, len(self.stream_calls))
        self.assertEqual(0, self.exit_code)

    def test_prints_lines_written_after_an_earlier_stream_ended(self):
        printed = self.run_wait(
            [['2026-09-27T20:33:41.1Z one'],
             ['2026-09-27T20:33:41.1Z one', '2026-09-27T20:33:50.2Z two']],
            [RUNNING, SUCCEEDED])

        self.assertEqual(['one', 'two'], printed)

    def test_prints_the_log_of_a_restarted_container(self):
        # With restartPolicy OnFailure the next stream is the new container's
        # log, which starts again from its first line.
        printed = self.run_wait(
            [['2026-09-27T20:33:41.1Z attempt', '2026-09-27T20:33:42.1Z failed'],
             ['2026-09-27T20:34:01.1Z attempt', '2026-09-27T20:34:02.1Z done']],
            [RUNNING, SUCCEEDED])

        self.assertEqual(['attempt', 'failed', 'attempt', 'done'], printed)

    def test_skips_lines_printed_earlier_when_their_stamps_are_out_of_order(self):
        # stdout and stderr lines are stamped separately, so the last line
        # printed is not always the newest one.
        log = ['2026-09-27T20:33:41.200Z to stdout',
               '2026-09-27T20:33:41.100Z to stderr']

        printed = self.run_wait([log, log], [RUNNING, SUCCEEDED])

        self.assertEqual(['to stdout', 'to stderr'], printed)

    def test_keeps_blank_lines(self):
        printed = self.run_wait(
            [['2026-09-27T20:33:41.1Z one', '2026-09-27T20:33:41.2Z ',
              '2026-09-27T20:33:41.3Z two']],
            [SUCCEEDED])

        self.assertEqual(['one', '', 'two'], printed)

    def test_prints_a_line_without_a_timestamp_unchanged(self):
        printed = self.run_wait([['no timestamp here']], [SUCCEEDED])

        self.assertEqual(['no timestamp here'], printed)

    def test_requests_timestamps_and_keeps_the_output_format(self):
        # Existing jobs filter on "INFO: kubernetes-wait-job: b'...'", so the
        # printed line must look as it did before timestamps were requested.
        self.run_wait([['2026-09-27T20:33:41.1Z hello']], [SUCCEEDED])

        self.assertTrue(self.stream_calls[0].kwargs['timestamps'])
        self.assertIn("INFO:kubernetes-wait-job:b'hello'", self.log_output)

    def test_follows_the_raw_stream_and_releases_the_connection(self):
        # watch.Watch().stream() is avoided: kubernetes 36.0.0 to 36.0.2 pass
        # it watch=True for pod logs, which read_namespaced_pod_log rejects.
        self.run_wait([['2026-09-27T20:33:41.1Z hello']], [SUCCEEDED])

        kwargs = self.stream_calls[0].kwargs
        self.assertEqual(('my-job-abcde', 'default'), (kwargs['name'], kwargs['namespace']))
        self.assertIs(False, kwargs['_preload_content'])
        self.assertTrue(all(s.released for s in self.streams))


if __name__ == '__main__':
    unittest.main()
