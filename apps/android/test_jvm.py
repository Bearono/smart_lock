"""Compile and run the door client's origin and inline-image policy tests."""
import argparse
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jdk', type=Path, required=True)
    parser.add_argument('--junit', type=Path, default=ROOT / '.tools/junit-4.13.2.jar')
    parser.add_argument('--hamcrest', type=Path, default=ROOT / '.tools/hamcrest-core-1.3.jar')
    args = parser.parse_args()
    jars = [args.junit.resolve(), args.hamcrest.resolve()]
    for jar in jars:
        if not jar.is_file():
            raise FileNotFoundError(f'Install the pinned test dependency: {jar}')
    output = ROOT / 'app/build/jvm-test'
    output.mkdir(parents=True, exist_ok=True)
    main = ROOT / 'app/src/main/java/org/smartlock/course'
    tests = ROOT / 'app/src/test/java/org/smartlock/course'
    pure = ['OriginPolicy']
    cases = ['OriginPolicyTest']
    classpath = os.pathsep.join(str(jar) for jar in jars)
    suffix = '.exe' if os.name == 'nt' else ''
    subprocess.run([str(args.jdk / ('bin/javac' + suffix)), '--release', '17', '-encoding', 'UTF-8',
                    '-cp', classpath, '-d', str(output),
                    *[str(main / f'{name}.java') for name in pure],
                    *[str(tests / f'{name}.java') for name in cases]], check=True)
    subprocess.run([str(args.jdk / ('bin/java' + suffix)), '-cp', str(output) + os.pathsep + classpath,
                    'org.junit.runner.JUnitCore', *['org.smartlock.course.' + case for case in cases]], check=True)


if __name__ == '__main__':
    main()
