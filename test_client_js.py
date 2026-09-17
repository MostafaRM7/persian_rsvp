"""P3-10: run the client JavaScript suites (renderer + player) inside pytest.

Previously test_renderer.mjs / test_player_wpm.mjs could only be run manually
with `node`, so client regressions could pass `pytest` silently. This wrapper
makes `pytest -v` the single entry point for the whole suite. Skips cleanly
when Node.js is not installed on the host.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent

CLIENT_SUITES = [
    "test_renderer.mjs",
    "test_player_wpm.mjs",
]


@pytest.mark.parametrize("suite", CLIENT_SUITES)
def test_client_js_suite(suite: str):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed on this host")
    script = PROJECT_ROOT / suite
    assert script.exists(), f"missing client test script: {suite}"
    result = subprocess.run(
        [node, suite],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"client suite {suite} failed\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
