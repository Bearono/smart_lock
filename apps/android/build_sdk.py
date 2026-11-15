"""Build a debug APK with official SDK tools; no Gradle repository access is required."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import ssl
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
ANDROID = 'http://schemas.android.com/apk/res/android'
ET.register_namespace('android', ANDROID)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jdk', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, default=ROOT / '.tools/sdk')
    parser.add_argument('--ca-cert', type=Path, help='Public course CA for this debug APK only; no OS trust change')
    parser.add_argument('--endpoint', default='', help='Optional initial HTTPS service origin')
    args = parser.parse_args()
    if args.endpoint:
        origin = urlsplit(args.endpoint)
        if (origin.scheme != 'https' or not origin.hostname or origin.username or origin.password
                or origin.query or origin.fragment or origin.path not in ('', '/')
                or '\\' in args.endpoint or origin.port == 0):
            raise ValueError('Endpoint must be a credential-free HTTPS origin')
        args.endpoint = args.endpoint.rstrip('/')
    ca_bytes = None
    if args.ca_cert:
        ca_bytes = args.ca_cert.read_bytes()
        if (len(ca_bytes) > 16384 or ca_bytes.count(b'-----BEGIN CERTIFICATE-----') != 1
                or not ca_bytes.strip().startswith(b'-----BEGIN CERTIFICATE-----')
                or not ca_bytes.strip().endswith(b'-----END CERTIFICATE-----')
                or b'PRIVATE KEY' in ca_bytes):
            raise ValueError('Expected one public PEM CA certificate, never a private key')
        ssl.create_default_context().load_verify_locations(cadata=ca_bytes.decode('ascii'))
    tools = args.sdk.resolve() / 'build-tools/36.0.0'
    platform = args.sdk.resolve() / 'platforms/android-36/android.jar'
    jdk = args.jdk.resolve() / 'bin'
    suffix = '.exe' if os.name == 'nt' else ''
    java, javac, keytool = (jdk / (name + suffix) for name in ('java', 'javac', 'keytool'))
    aapt2, zipalign = (tools / (name + suffix) for name in ('aapt2', 'zipalign'))
    for required in (javac, java, keytool, aapt2, zipalign, platform):
        if not required.is_file():
            raise FileNotFoundError(required)
    build = ROOT / 'app/build/sdk'
    classes, dex, generated, resources_dir = (build / name for name in ('classes', 'dex', 'generated', 'res'))
    for path in (classes, dex, generated, resources_dir):
        path.resolve().relative_to((ROOT / 'app/build').resolve())
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    def run(*command):
        subprocess.run([str(part) for part in command], cwd=ROOT, check=True)

    shutil.copytree(ROOT / 'app/src/main/res', resources_dir, dirs_exist_ok=True)
    strings = ET.parse(resources_dir / 'values/strings.xml')
    strings.find("./string[@name='default_service_url']").text = args.endpoint
    strings.write(resources_dir / 'values/strings.xml', encoding='utf-8', xml_declaration=True)
    if ca_bytes:
        (resources_dir / 'raw').mkdir(exist_ok=True)
        (resources_dir / 'raw/course_ca.pem').write_bytes(ca_bytes)
        network = ET.parse(resources_dir / 'xml/network_security_config.xml')
        debug = network.find('debug-overrides')
        if debug is not None:
            network.getroot().remove(debug)
        debug = ET.SubElement(network.getroot(), 'debug-overrides')
        anchors = ET.SubElement(debug, 'trust-anchors')
        ET.SubElement(anchors, 'certificates', {'src': '@raw/course_ca'})
        network.write(resources_dir / 'xml/network_security_config.xml', encoding='utf-8', xml_declaration=True)
    manifest = ET.parse(ROOT / 'app/src/main/AndroidManifest.xml')
    manifest.getroot().set('package', 'org.smartlock.course')
    manifest.getroot().find('application').set(f'{{{ANDROID}}}debuggable', 'true')
    manifest.write(build / 'AndroidManifest.xml', encoding='utf-8', xml_declaration=True)
    run(aapt2, 'compile', '--dir', resources_dir, '-o', build / 'resources.zip')
    run(aapt2, 'link', '-o', build / 'resources.apk', '-I', platform,
        '--manifest', build / 'AndroidManifest.xml', '--min-sdk-version', '26',
        '--target-sdk-version', '36', '--version-code', '2', '--version-name', '1.1.0',
        '--java', generated, build / 'resources.zip')
    sources = sorted((ROOT / 'app/src/main/java').rglob('*.java')) + sorted(generated.rglob('*.java'))
    run(javac, '--release', '17', '-encoding', 'UTF-8', '-cp', platform,
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
    run(java, '-cp', tools / 'lib/d8.jar', 'com.android.tools.r8.D8',
        '--lib', platform, '--min-api', '26', '--output', dex, build / 'classes.jar')
    with zipfile.ZipFile(build / 'resources.apk') as resources, zipfile.ZipFile(build / 'unsigned.apk', 'w') as output:
        for entry in resources.infolist():
            output.writestr(entry, resources.read(entry.filename))
        for file in sorted(dex.glob('classes*.dex')):
            output.write(file, file.name)
    run(zipalign, '-f', '4', build / 'unsigned.apk', build / 'aligned.apk')
    key = ROOT / '.tools/debug.keystore'
    if not key.exists():
        key.parent.mkdir(parents=True, exist_ok=True)
        run(keytool, '-genkeypair', '-keystore', key, '-storepass', 'android',
            '-keypass', 'android', '-alias', 'androiddebugkey', '-keyalg', 'RSA', '-keysize', '2048',
            '-validity', '3650', '-dname', 'CN=Android Debug,O=Android,C=US')
    apk = ROOT / 'app/build/outputs/apk/debug/app-debug.apk'
    apk.parent.mkdir(parents=True, exist_ok=True)
    run(java, '-jar', tools / 'lib/apksigner.jar', 'sign', '--ks', key,
        '--ks-pass', 'pass:android', '--key-pass', 'pass:android', '--out', apk, build / 'aligned.apk')
    run(java, '-jar', tools / 'lib/apksigner.jar', 'verify', '--verbose', '--print-certs', apk)
    run(zipalign, '-c', '4', apk)
    evidence = {'apk': str(apk), 'sha256': hashlib.sha256(apk.read_bytes()).hexdigest(),
                'bytes': apk.stat().st_size, 'build_tools': '36.0.0', 'compile_sdk': 36,
                'min_sdk': 26, 'target_sdk': 36, 'type': 'debug',
                'version': '1.1.0', 'default_endpoint': args.endpoint,
                'course_ca_sha256': hashlib.sha256(ca_bytes).hexdigest() if ca_bytes else None,
                'source_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in sorted((ROOT / 'app/src/main').rglob('*')) if path.is_file()},
                'build_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (apk.parent / 'build-evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: evidence[key] for key in ('apk', 'sha256', 'bytes')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
