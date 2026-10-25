"""Runs the Danish v5 model's own regression battery and self-reconciliation."""
import subprocess, sys
from pathlib import Path
import pytest

M = Path(__file__).parent.parent / "model" / "wave4" / "ube_model_v5"
pytestmark = pytest.mark.skipif(not (M / "regression_tests.py").exists(), reason="model/wave4/ube_model_v5 not present")

def _run(script):
    r = subprocess.run([sys.executable, script], cwd=M, capture_output=True, text=True, timeout=900)
    return r.returncode, r.stdout + r.stderr

def test_regression_battery():
    code, out = _run("regression_tests.py")
    assert "ALL REGRESSION TESTS PASS" in out, out[-3000:]

def test_results_reconcile():
    code, out = _run("verify_results_v5.py")
    assert "the file reconciles with itself" in out, out[-3000:]
