"""Explicit local enrollment of approved account identities; no anonymous HTTP uploads."""
import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'cv/code'))


def main():
    from template_store import install_template, load_templates, read_template, remove_template
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, help='Template directory; default SMART_LOCK_TEMPLATES_DIR')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    commands.add_parser('validate')
    install = commands.add_parser('install')
    install.add_argument('--username', required=True)
    install.add_argument('--vector', type=Path, required=True)
    install.add_argument('--replace', action='store_true')
    enroll = commands.add_parser('enroll')
    enroll.add_argument('--username', required=True)
    enroll.add_argument('--images', type=Path, nargs='+', required=True)
    enroll.add_argument('--replace', action='store_true')
    remove = commands.add_parser('remove')
    remove.add_argument('--username', required=True)
    args = parser.parse_args()
    try:
        if args.command in ('list', 'validate'):
            templates = load_templates(args.directory)
            if args.command == 'validate' and not templates:
                raise ValueError('No enrolled templates')
            print('\n'.join(templates) if args.command == 'list' else f'{len(templates)} valid templates')
        elif args.command == 'remove':
            remove_template(args.username, args.directory)
            print('Template removed. Reload device templates before allowing recognition.')
        else:
            if args.command == 'install':
                vector = read_template(args.vector)
            else:
                import cv2
                import numpy as np
                from face_detector import DnnFaceDetector, compute_embeddings
                if not 3 <= len(args.images) <= 20:
                    raise ValueError('Enrollment requires 3 to 20 distinct, operator-verified images')
                detector, vectors, seen = DnnFaceDetector(), [], set()
                for image in args.images:
                    if not image.is_file() or image.stat().st_size > 8 * 1024 * 1024:
                        raise ValueError('Image is missing or exceeds 8 MiB')
                    content = image.read_bytes()
                    digest = hashlib.sha256(content).digest()
                    if digest in seen:
                        raise ValueError('Repeated enrollment image')
                    seen.add(digest)
                    frame = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is None or frame.size > 24 * 1024 * 1024:
                        raise ValueError('Image cannot be decoded or is too large')
                    faces = detector.detect(frame)
                    if len(faces) != 1:
                        raise ValueError('Every enrollment image must contain exactly one face')
                    embeddings = compute_embeddings(frame, faces)
                    if len(embeddings) != 1:
                        raise ValueError('Unable to extract one face embedding')
                    vectors.append(embeddings[0]['embedding'])
                vector = np.mean(np.asarray(vectors, dtype=np.float32), axis=0)
            target = install_template(args.username, vector, args.directory, replace=args.replace)
            print(f'Template installed: {target.name}. Reload device templates to activate it.')
        return 0
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Enrollment failed: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
