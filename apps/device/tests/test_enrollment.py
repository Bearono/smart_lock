"""Hardware-free tests using real NumPy, filesystem and device inference boundaries."""
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, Mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cv/code'))
import paths
import template_store as store
import model_manifest


class EnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.vector = np.ones(128, dtype=np.float32)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tools_and_inference_use_same_configurable_paths(self):
        with patch.dict(os.environ, {'SMART_LOCK_TEMPLATES_DIR': str(self.directory)}):
            self.assertEqual(paths.templates_dir(), self.directory)
            store.install_template('家人', self.vector)
            self.assertEqual(set(store.load_templates()), {'家人'})

    def test_invalid_vectors_and_identity_paths_are_rejected(self):
        for vector in (np.ones(127), np.zeros(128), np.full(128, np.nan), np.full(128, np.inf), ['x'] * 128):
            with self.subTest(shape=str(np.asarray(vector).shape)), self.assertRaises(ValueError):
                store.install_template('alice', vector, self.directory)
        for name in ('../alice', 'a/b', 'a\\b', '.', '', 'a\x00b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                store.install_template(name, self.vector, self.directory)
        self.assertFalse(list(self.directory.iterdir()))

    def test_existing_template_requires_explicit_replacement(self):
        path = store.install_template('alice', self.vector, self.directory)
        original = path.read_bytes()
        with self.assertRaises(FileExistsError):
            store.install_template('alice', np.arange(128), self.directory)
        self.assertEqual(path.read_bytes(), original)
        store.install_template('alice', np.arange(128), self.directory, replace=True)
        self.assertFalse(np.array_equal(store.read_template(path), store.normalize(self.vector)))
        self.assertEqual(len(list(self.directory.iterdir())), 1)

    def test_invalid_and_pickle_templates_fail_explicitly(self):
        path = self.directory / 'template_alice.npy'
        np.save(path, np.array([{'payload': 'object'}], dtype=object))
        with self.assertRaises(ValueError):
            store.load_templates(self.directory)

    def test_remove_preserves_other_accounts(self):
        for username in ('alice', 'bob'):
            store.install_template(username, self.vector, self.directory)
        store.remove_template('alice', self.directory)
        self.assertEqual(set(store.load_templates(self.directory)), {'bob'})

    def test_cli_install_validate_and_remove(self):
        source = self.directory / 'vector.npy'
        np.save(source, self.vector)
        target = self.directory / 'installed'
        cli = Path(__file__).resolve().parents[1] / 'manage_templates.py'
        def run(*args):
            return subprocess.run([sys.executable, str(cli), '--directory', str(target), *args],
                                  capture_output=True, text=True, timeout=20)
        self.assertNotEqual(run('validate').returncode, 0)
        self.assertEqual(run('install', '--username', 'alice', '--vector', str(source)).returncode, 0)
        self.assertEqual(run('validate').returncode, 0)
        self.assertNotEqual(run('install', '--username', 'alice', '--vector', str(source)).returncode, 0)
        self.assertEqual(run('remove', '--username', 'alice').returncode, 0)
        self.assertNotEqual(run('validate').returncode, 0)

    def test_model_missing_and_tampered_fail_checksums(self):
        with self.assertRaises(ValueError):
            model_manifest.verify_models(self.directory)
        for name in model_manifest.MODELS:
            (self.directory / name).write_bytes(b'untrusted model')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            model_manifest.verify_models(self.directory)

    def test_symlink_cannot_replace_or_escape_template_store(self):
        source = store.install_template('bob', self.vector, self.directory)
        target = self.directory / 'template_alice.npy'
        target.symlink_to(source)
        with self.assertRaises(ValueError):
            store.install_template('alice', self.vector, self.directory, replace=True)
        with self.assertRaises(ValueError):
            store.remove_template('alice', self.directory)
        with self.assertRaises(ValueError):
            store.load_templates(self.directory)
        self.assertTrue(source.is_file())

    def test_cache_switch_does_not_reuse_other_directory(self):
        import recognize
        first, second = self.directory / 'first', self.directory / 'second'
        store.install_template('alice', self.vector, first)
        store.install_template('bob', self.vector, second)
        recognize._templates_cache = None
        self.assertEqual(set(recognize._get_templates(str(first))), {'alice'})
        self.assertEqual(set(recognize._get_templates(str(second))), {'bob'})

    def test_multiple_faces_cannot_choose_one_for_authentication(self):
        import recognize
        store.install_template('alice', self.vector, self.directory)
        detector = Mock()
        detector.detect.return_value = [{}, {}]
        with patch.object(recognize, '_get_detector', return_value=detector), patch.object(recognize, 'compute_embeddings') as embeddings:
            self.assertEqual(recognize.recognize(np.zeros((32, 32, 3), dtype=np.uint8), str(self.directory)), (None, 0.0))
            embeddings.assert_not_called()


if __name__ == '__main__':
    unittest.main()
