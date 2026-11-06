import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import textwrap
import unittest


@unittest.skipUnless("fork" in multiprocessing.get_all_start_methods(), "requires fork")
class TestForkCleanup(unittest.TestCase):
    def run_scenario(self, scenario: str) -> None:
        # Exercise interpreter shutdown too: an unreaped worker blocked in send()
        # can hang atexit even after the runner has propagated its exception.
        script = textwrap.dedent("""
            import multiprocessing
            from checkov.common.parallelizer.parallel_runner import ParallelRunner

            payload = b"x" * (2 * 1024 * 1024)

            def large_result(item):
                return item, payload

            def failing_task(item):
                if item == 0:
                    raise ValueError("synthetic runner failure")
                return large_result(item)

            runner = ParallelRunner(workers_number=3)
        """) + textwrap.dedent(scenario)
        env = dict(os.environ, CHECKOV_PARALLELIZATION_TYPE="fork", OBJC_DISABLE_INITIALIZE_FORK_SAFETY="YES")
        process = subprocess.Popen(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            # Kill the whole isolated test tree so a regression cannot wedge CI.
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
            self.fail(f"Fork runner hung during execution or shutdown.\n{stdout}\n{stderr}")
        self.assertEqual(process.returncode, 0, f"{stdout}\n{stderr}")

    def test_runner_exception_cleans_up_large_unread_results(self) -> None:
        for group_size in (1, 2):
            with self.subTest(group_size=group_size):
                self.run_scenario(f"""
                    try:
                        list(runner.run_function(failing_task, list(range(6)), group_size={group_size}))
                    except ValueError as error:
                        assert str(error) == "synthetic runner failure"
                    else:
                        raise AssertionError("Runner exception was swallowed")
                    assert not multiprocessing.active_children(), "Workers survived runner failure"
                """)

    def test_closing_consumer_cleans_up_large_unread_results(self) -> None:
        self.run_scenario("""
            results = runner.run_function(large_result, list(range(6)), group_size=2)
            assert next(results) == (0, payload)
            results.close()
            assert not multiprocessing.active_children(), "Workers survived consumer close"
        """)

    def test_success_preserves_all_grouped_results_and_reaps_children(self) -> None:
        self.run_scenario("""
            results = list(runner.run_function(large_result, list(range(6)), group_size=2))
            assert results == [(item, payload) for item in range(6)]
            assert not multiprocessing.active_children(), "Workers survived successful run"
            assert list(runner.run_function(large_result, [])) == []
        """)

    def test_start_failure_cleans_up_already_started_workers(self) -> None:
        self.run_scenario("""
            from multiprocessing.process import BaseProcess
            from unittest.mock import patch

            original_start = BaseProcess.start
            started = []

            def start(process):
                if started:
                    raise RuntimeError("synthetic process start failure")
                original_start(process)
                started.append(process)

            with patch.object(BaseProcess, "start", start):
                try:
                    list(runner.run_function(large_result, [0, 1], group_size=1))
                except RuntimeError as error:
                    assert str(error) == "synthetic process start failure"
                else:
                    raise AssertionError("Process start failure was swallowed")
            assert len(started) == 1
            assert started[0].exitcode is not None, "Started worker was not joined"
            assert not multiprocessing.active_children(), "Workers survived process start failure"
        """)
