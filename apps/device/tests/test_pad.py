"""PAD preprocessing and fail-closed resource tests; excludes biometric accuracy."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cv/code'))
from anti_spoof import crop_patch, verify_pad_model


class PadTests(unittest.TestCase):
    def test_crop_boundary_scale_and_bgr_uint8(self):
        image = np.zeros((240, 320, 3), dtype=np.uint8)
        image[:, :, 0] = 200
        for box in ((100, 80, 150, 140), (0, 0, 60, 60), (260, 180, 319, 239)):
            patch = crop_patch(image, dict(zip(('x1', 'y1', 'x2', 'y2'), box)))
            self.assertEqual(patch.shape, (80, 80, 3))
            self.assertEqual(patch.dtype, np.uint8)
            self.assertTrue(np.all(patch[:, :, 0] == 200))
            self.assertTrue(np.all(patch[:, :, 2] == 0))

    def test_bad_boxes_and_missing_tampered_model_fail_closed(self):
        with self.assertRaises(ValueError):
            crop_patch(np.zeros((80, 80, 3), dtype=np.uint8),
                {'x1': -1, 'y1': 0, 'x2': 50, 'y2': 50})
        with TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                verify_pad_model(directory)
            (Path(directory) / 'minifasnet-v2.onnx').write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                verify_pad_model(directory)


if __name__ == '__main__':
    unittest.main()
