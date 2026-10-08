"""Verify serialized model ownership without loading camera or face libraries."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
from threading import Lock
import time
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('device_resource_guard', ROOT / 'paspberry_pi/cv/code/resource_guard.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DeviceResourceTests(unittest.TestCase):
    def test_inference_and_template_reload_share_one_owner(self):
        active, peak = 0, 0
        state = Lock()
        @module.serialized_inference
        def infer(value):
            nonlocal active, peak
            with state:
                active += 1
                peak = max(peak, active)
            time.sleep(0.001)
            with state:
                active -= 1
            return value
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(infer, range(30))), list(range(30)))
        self.assertEqual(peak, 1)

    def test_failure_releases_model_ownership(self):
        @module.serialized_inference
        def infer():
            raise ValueError('invalid frame')
        with self.assertRaises(ValueError):
            infer()
        with ThreadPoolExecutor(max_workers=1) as pool:
            self.assertEqual(pool.submit(module.serialized_inference(lambda: 'ready')).result(timeout=2), 'ready')
