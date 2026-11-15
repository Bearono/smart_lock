"""Build a debug APK with official SDK tools; no Gradle repository access is required."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
ANDROID = 'http://schemas.android.com/apk/res/android'
ET.register_namespace('android', ANDROID)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jdk', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, default=ROOT / '.tools/sdk')
    args = parser.parse_args()
    tools = args.sdk.resolve() / 'build-tools/36.0.0'
    platform = args.sdk.resolve() / 'platforms/android-36/android.jar'
    jdk = args.jdk.resolve() / 'bin'
    for required in (jdk / 'javac.exe', jdk / 'java.exe', tools / 'aapt2.exe', platform):
        if not required.is_file():
            raise FileNotFoundError(required)
    build = ROOT / 'app/build/sdk'
    classes, dex, generated = (build / name for name in ('classes', 'dex', 'generated'))
    for path in (classes, dex, generated):
        path.resolve().relative_to((ROOT / 'app/build').resolve())
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    def run(*command):
        subprocess.run([str(part) for part in command], cwd=ROOT, check=True)

    manifest = ET.parse(ROOT / 'app/src/main/AndroidManifest.xml')
    manifest.getroot().set('package', 'org.smartlock.course')
    manifest.getroot().find('application').set(f'{{{ANDROID}}}debuggable', 'true')
    manifest.write(build / 'AndroidManifest.xml', encoding='utf-8', xml_declaration=True)
    run(tools / 'aapt2.exe', 'compile', '--dir', ROOT / 'app/src/main/res', '-o', build / 'resources.zip')
    run(tools / 'aapt2.exe', 'link', '-o', build / 'resources.apk', '-I', platform,
        '--manifest', build / 'AndroidManifest.xml', '--min-sdk-version', '26',
        '--target-sdk-version', '36', '--version-code', '1', '--version-name', '1.0.0',
        '--java', generated, build / 'resources.zip')
    sources = sorted((ROOT / 'app/src/main/java').rglob('*.java')) + sorted(generated.rglob('*.java'))
    run(jdk / 'javac.exe', '--release', '17', '-encoding', 'UTF-8', '-cp', platform,
        '-d', classes, *sources)
    # Only this compilation's classes are included; removed source classes cannot leak from a prior build.
    expected_packages = {'org/smartlock/course'}
    class_files = sorted(classes.rglob('*.class'))
    with zipfile.ZipFile(build / 'classes.jar', 'w', zipfile.ZIP_DEFLATED) as output:
        source_stems = {source.stem for source in sources}
        for path in class_files:
            relative = path.relative_to(classes).as_posix()
            if str(Path(relative).parent).replace('\\', '/') in expected_packages and path.stem.split('$')[0] in source_stems:
                output.write(path, relative)
    run(jdk / 'java.exe', '-cp', tools / 'lib/d8.jar', 'com.android.tools.r8.D8',
        '--lib', platform, '--min-api', '26', '--output', dex, build / 'classes.jar')
    with zipfile.ZipFile(build / 'resources.apk') as resources, zipfile.ZipFile(build / 'unsigned.apk', 'w') as output:
        for entry in resources.infolist():
            output.writestr(entry, resources.read(entry.filename))
        for file in sorted(dex.glob('classes*.dex')):
            output.write(file, file.name)
    run(tools / 'zipalign.exe', '-f', '4', build / 'unsigned.apk', build / 'aligned.apk')
    key = ROOT / '.tools/debug.keystore'
    if not key.exists():
        run(jdk / 'keytool.exe', '-genkeypair', '-keystore', key, '-storepass', 'android',
            '-keypass', 'android', '-alias', 'androiddebugkey', '-keyalg', 'RSA', '-keysize', '2048',
            '-validity', '3650', '-dname', 'CN=Android Debug,O=Android,C=US')
    apk = ROOT / 'app/build/outputs/apk/debug/app-debug.apk'
    apk.parent.mkdir(parents=True, exist_ok=True)
    run(jdk / 'java.exe', '-jar', tools / 'lib/apksigner.jar', 'sign', '--ks', key,
        '--ks-pass', 'pass:android', '--key-pass', 'pass:android', '--out', apk, build / 'aligned.apk')
    run(jdk / 'java.exe', '-jar', tools / 'lib/apksigner.jar', 'verify', '--verbose', '--print-certs', apk)
    run(tools / 'zipalign.exe', '-c', '4', apk)
    evidence = {'apk': str(apk), 'sha256': hashlib.sha256(apk.read_bytes()).hexdigest(),
                'bytes': apk.stat().st_size, 'build_tools': '36.0.0', 'compile_sdk': 36,
                'min_sdk': 26, 'target_sdk': 36, 'type': 'debug',
                'source_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in sorted((ROOT / 'app/src/main').rglob('*')) if path.is_file()},
                'build_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (apk.parent / 'build-evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: evidence[key] for key in ('apk', 'sha256', 'bytes')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
