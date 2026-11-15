"""Regression guards for architecture boundaries and release independence."""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('repository_checks', ROOT / 'deploy/check_repository.py')
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class RepositoryContracts(unittest.TestCase):
    def test_shared_and_business_layers_reject_reverse_imports(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                'packages/protocol/impl.py': 'from flask import request\n',
                'apps/api/app/service.py': 'from app.routes.mfa import mfa_bp\n',
                'apps/api/app/__init__.py': 'from app.routes.mfa import mfa_bp\n',
            }
            for name, body in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding='utf-8')
            errors = checks.check_imports(root, [root / name for name in files])
            self.assertEqual(len(errors), 2)
            self.assertTrue(any('Shared protocol' in error for error in errors))
            self.assertTrue(any('Business service' in error for error in errors))

    def test_local_links_cannot_escape_release_or_hide_missing_targets(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            doc = root / 'README.md'
            doc.write_text('[bad](missing.md) [escape](../outside.md) [ok](#title) [web](https://example.com)', encoding='utf-8')
            self.assertEqual(len(checks.check_documents(root, [doc])), 2)

    def test_source_archive_scan_does_not_depend_on_git(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('source', encoding='utf-8')
            (root / 'build').mkdir()
            (root / 'build/stale.py').write_text('stale', encoding='utf-8')
            with patch.object(checks.subprocess, 'run', side_effect=FileNotFoundError):
                self.assertEqual(checks.source_files(root), [root / 'README.md'])

    def test_mfa_http_contract_is_preserved_across_module_split(self):
        sys.path.insert(0, str(ROOT / 'apps/api'))
        from app import create_app
        app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                          'SECRET_KEY': 'isolated-route-map-key-00000000000',
                          'JWT_SECRET_KEY': 'isolated-route-map-jwt-00000000000'})
        expected = json.loads((Path(__file__).parent / 'contracts/mfa_routes.json').read_text())
        actual = {rule.endpoint: (str(rule), sorted(rule.methods - {'HEAD', 'OPTIONS'}))
                  for rule in app.url_map.iter_rules() if rule.endpoint.startswith('mfa.')}
        self.assertEqual(actual, {item['endpoint']: (item['rule'], sorted(item['methods'])) for item in expected})


if __name__ == '__main__':
    unittest.main()
