"""Focused tests for the CI pytest replay plugin."""
import json
import os
from pathlib import Path
import subprocess
import sys


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def run_suite(tmp_path, source, **extra_env):
    (tmp_path / "test_sample.py").write_text(source)
    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(PLUGIN_ROOT),
        "CI_REPLAY_BRANCH": "feature/replay",
        "CI_REPLAY_LANE": "unit",
        "CI_REPLAY_CACHE_DIR": str(tmp_path / "history"),
        "TRAVIS_REPO_SLUG": "varunsharma/pyresparser",
        "TRAVIS_PULL_REQUEST": "123",
        "TRAVIS_BUILD_ID": "456",
        "TRAVIS_JOB_ID": "789",
    })
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "ci_replay",
         "--confcutdir=" + str(tmp_path), "-q"],
        cwd=str(tmp_path), env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, universal_newlines=True)


def read_history(tmp_path):
    paths = list((tmp_path / "history").glob("*.json"))
    assert len(paths) == 1
    return json.loads(paths[0].read_text())


def test_first_failure_stops_and_saves_remaining_work(tmp_path):
    result = run_suite(tmp_path,
                       "def test_a(): assert False\ndef test_b(): assert False\n")
    assert result.returncode == 1, result.stdout
    state = read_history(tmp_path)
    assert state["failed"] == ["test_sample.py::test_a"]
    assert state["pending"] == ["test_sample.py::test_b"]
    assert state["contexts"][-1]["repository"] == "varunsharma/pyresparser"
    assert state["contexts"][-1]["pr"] == "123"
    assert state["contexts"][-1]["run"] == "456"


def test_known_failure_runs_before_pending_work_and_new_tests(tmp_path):
    source = ("def test_a(): pass\ndef test_b(): assert False\n"
              "def test_c(): assert False\n")
    assert run_suite(tmp_path, source).returncode == 1
    source = source.replace("def test_a(): pass", "def test_a(): assert False")
    result = run_suite(tmp_path, source)
    assert result.returncode == 1, result.stdout
    assert "FAILED test_sample.py::test_b" in result.stdout
    assert read_history(tmp_path)["failed"] == ["test_sample.py::test_b"]


def test_fixed_failure_and_pending_work_clear_only_after_real_pass(tmp_path):
    assert run_suite(tmp_path,
                     "def test_a(): assert False\ndef test_b(): pass\n").returncode == 1
    result = run_suite(tmp_path,
                       "def test_a(): pass\ndef test_b(): pass\n")
    assert result.returncode == 0, result.stdout
    state = read_history(tmp_path)
    assert state["failed"] == []
    assert state["pending"] == []


def test_skipped_previous_failure_remains_unresolved(tmp_path):
    assert run_suite(tmp_path, "def test_a(): assert False\n").returncode == 1
    result = run_suite(tmp_path,
                       "import pytest\n@pytest.mark.skip\ndef test_a(): pass\n")
    assert result.returncode == 0, result.stdout
    assert read_history(tmp_path)["failed"] == ["test_sample.py::test_a"]


def test_history_isolated_by_branch_and_python_lane(tmp_path):
    assert run_suite(tmp_path, "def test_a(): assert False\n").returncode == 1
    result = run_suite(tmp_path, "def test_a(): pass\n",
                       CI_REPLAY_BRANCH="other")
    assert result.returncode == 0, result.stdout
    assert len(list((tmp_path / "history").glob("*.json"))) == 2


def test_history_isolated_by_pull_request(tmp_path):
    assert run_suite(tmp_path, "def test_a(): assert False\n").returncode == 1
    result = run_suite(tmp_path, "def test_a(): pass\n",
                       TRAVIS_PULL_REQUEST="456")
    assert result.returncode == 0, result.stdout
    assert len(list((tmp_path / "history").glob("*.json"))) == 2


def test_corrupt_history_fails_before_running_tests(tmp_path):
    assert run_suite(tmp_path, "def test_a(): pass\n").returncode == 0
    history_path = list((tmp_path / "history").glob("*.json"))[0]
    history_path.write_text("{broken")
    marker = tmp_path / "executed"
    result = run_suite(tmp_path,
                       "open(%r, 'w').close()\ndef test_a(): pass\n" % str(marker))
    assert result.returncode != 0
    assert "Invalid replay history" in result.stdout
    assert not marker.exists()


def test_checkpoint_write_failure_blocks_test_execution(tmp_path):
    cache = tmp_path / "history"
    cache.write_text("not a directory")
    marker = tmp_path / "executed"
    result = run_suite(tmp_path,
                       "def test_a():\n    open(%r, 'w').close()\n" % str(marker))
    assert result.returncode != 0
    assert not marker.exists()


def test_prior_context_is_retained_after_later_success(tmp_path):
    assert run_suite(tmp_path, "def test_a(): assert False\n",
                     TRAVIS_BUILD_ID="old-run").returncode == 1
    result = run_suite(tmp_path, "def test_a(): pass\n",
                       TRAVIS_BUILD_ID="new-run")
    assert result.returncode == 0, result.stdout
    state = read_history(tmp_path)
    assert [context["run"] for context in state["contexts"]] == [
        "old-run", "new-run"]


def test_collection_error_is_prioritized_and_persisted(tmp_path):
    result = run_suite(tmp_path, "raise RuntimeError('collect failure')\n")
    assert result.returncode != 0
    state = read_history(tmp_path)
    assert state["failed"] == ["test_sample.py"]
    assert state["contexts"][-1]["run"] == "456"
