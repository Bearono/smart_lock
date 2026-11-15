"""Course release must include new clients without leaking SDKs or local keys."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('course_package_release', ROOT / 'deploy/package_release.py')
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


class CoursePackagingTests(unittest.TestCase):
    def test_android_and_audio_launch_sources_are_included(self):
        names = {path.relative_to(ROOT).as_posix() for path in PACKAGE.collect_files()}
        for required in ('Start-CourseAudio.cmd', 'deploy/audio_console.py', 'deploy/audio_peer.py',
                         'apps/android/build_sdk.py', 'apps/android/app/src/main/AndroidManifest.xml',
                         'apps/android/app/src/main/java/org/smartlock/course/D2dCrypto.java',
                         'apps/android/app/src/main/java/org/smartlock/course/OfdmCodec.java',
                         'apps/android/app/src/main/res/xml/network_security_config.xml'):
            self.assertIn(required, names)

    def test_local_toolchains_keys_and_build_outputs_are_excluded(self):
        for path in PACKAGE.collect_files():
            relative = path.relative_to(ROOT)
            self.assertFalse({'.tools', '.gradle', 'build', 'instance', '.venv-course'} & set(relative.parts))
            self.assertNotIn(path.suffix, {'.apk', '.keystore', '.jks', '.key', '.db', '.sqlite3'})


if __name__ == '__main__':
    unittest.main()
