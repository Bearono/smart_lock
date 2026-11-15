"""PAD preprocessing and fail-closed resource tests; excludes biometric accuracy."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cv/code'))
from anti_spoof import crop_patch, verify_pad_model
import anti_spoof
from model_manifest import PAD_DETECTOR_MODELS, verify_model_files


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

    def test_pad_detector_assets_must_be_present_and_verified(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                verify_model_files(directory, PAD_DETECTOR_MODELS)
            for name in PAD_DETECTOR_MODELS:
                (Path(directory) / name).write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                verify_model_files(directory, PAD_DETECTOR_MODELS)

    def test_pad_reference_detector_uses_bgr_mean_aspect_and_inclusive_box(self):
        network = Mock()
        network.forward.return_value = np.array([[[[0., 1., .99, .25, .25, .5, .5]]]])
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        with patch.object(anti_spoof, '_detector', network), patch.object(anti_spoof, '_detector_path', str(Path('/models'))):
            box = anti_spoof._pad_box(image, Path('/models'))
        self.assertEqual(box, {'x1': 160, 'y1': 120, 'x2': 321, 'y2': 241})
        blob, name = network.setInput.call_args.args
        self.assertEqual(name, 'data')
        self.assertEqual(blob.shape, (1, 3, 166, 221))
        np.testing.assert_array_equal(blob[0, :, 0, 0], [-104., -117., -123.])

    def test_pad_detector_rejects_multiple_missing_truncated_or_invalid_faces(self):
        valid = [0., 1., .99, .2, .2, .4, .4]
        network = Mock()
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        with patch.object(anti_spoof, '_detector', network), patch.object(anti_spoof, '_detector_path', str(Path('/models'))):
            for rows in ([valid, valid], [[0., 1., .2, .2, .2, .4, .4]], [[0., 1., .99, -.1, .2, .4, .4]]):
                network.forward.return_value = np.array(rows)
                self.assertIsNone(anti_spoof._pad_box(image, Path('/models')))
            for rows in ([[float('nan')] * 7], [[0., 1., .99]]):
                network.forward.return_value = np.array(rows)
                with self.assertRaises(ValueError):
                    anti_spoof._pad_box(image, Path('/models'))

    def test_pad_never_scores_another_face_or_identity_ambiguity(self):
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        detector, network = Mock(), Mock()
        identity_box = dict(zip(('x1', 'y1', 'x2', 'y2'), (50, 50, 100, 100)))
        other_box = dict(zip(('x1', 'y1', 'x2', 'y2'), (200, 200, 250, 250)))
        with patch.object(anti_spoof, 'verify_pad_model', return_value=Path('/models/minifasnet-v2.onnx')), \
                patch.object(anti_spoof, '_pad_box', return_value=other_box), patch.object(anti_spoof, '_network', network):
            for faces in ([], [{'box': identity_box}] * 2, [{'box': identity_box}]):
                detector.detect.return_value = faces
                self.assertEqual(anti_spoof.score_frame(image, detector), 0.)
        network.forward.assert_not_called()

    def test_pad_class_index_and_model_input_are_unchanged(self):
        image = np.zeros((240, 320, 3), dtype=np.uint8)
        image[:, :, 0] = 200
        box = dict(zip(('x1', 'y1', 'x2', 'y2'), (100, 80, 160, 150)))
        detector, network = Mock(), Mock()
        detector.detect.return_value = [{'box': box}]
        network.forward.return_value = np.array([[0., 2., 0.]])
        path = Path('/models/minifasnet-v2.onnx')
        with patch.object(anti_spoof, 'verify_pad_model', return_value=path), \
                patch.object(anti_spoof, '_pad_box', return_value=box), \
                patch.object(anti_spoof, '_network', network), patch.object(anti_spoof, '_model_path', str(path)):
            self.assertAlmostEqual(anti_spoof.score_frame(image, detector), np.exp(2) / (np.exp(2) + 2))
            np.testing.assert_array_equal(network.setInput.call_args.args[0][0, :, 0, 0], [200., 0., 0.])
            network.forward.return_value = np.array([[0., np.nan, 0.]])
            with self.assertRaises(ValueError):
                anti_spoof.score_frame(image, detector)


if __name__ == '__main__':
    unittest.main()
