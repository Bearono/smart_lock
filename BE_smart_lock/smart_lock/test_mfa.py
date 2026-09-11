"""Compatibility command for the isolated MFA regression suite.

python test_mfa.py
For live end-to-end timing, use tests/perf/measure_e2e.py after preparing test accounts.
"""
from pathlib import Path
import unittest


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent / 'tests'), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
