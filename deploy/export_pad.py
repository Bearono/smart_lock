"""Convert pinned MiniFASNetV2 weights to ONNX; never execute a pickle payload.

Run only in an explicit export environment with torch 2.9.0, onnx 1.19.1,
numpy 2.2.4 and OpenCV 4.11.0.86. Device inference needs only existing OpenCV.
Upstream source/models are Apache-2.0, Copyright 2020 Minivision.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import urllib.request

COMMIT = 'b6d5f04ad78778917853b25c778acef6d5626d15'
BASE = f'https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing/{COMMIT}/'
ASSETS = {
    'MiniFASNet.py': ('src/model_lib/MiniFASNet.py', 'e498c4ec5e1ddfaba62b941a126c19d65aa564999f3309661fe43ee8bf38acd7'),
    'model.pth': ('resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth', 'a5eb02e1843f19b5386b953cc4c9f011c3f985d0ee2bb9819eea9a142099bec0'),
    'LICENSE': ('LICENSE', 'daf94bf1dc9cc5700fe5af2c7c0cbd1836e70d509ed78fd0bebef7432edee6fb'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    for name, (remote, digest) in ASSETS.items():
        path = args.cache / name
        if not path.exists():
            with urllib.request.urlopen(BASE + remote, timeout=60) as response:
                content = response.read(8 * 1024 * 1024 + 1)
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError(f'Upstream checksum failed: {name}')
            path.write_bytes(content)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Cached checksum failed: {name}')
    import torch
    import cv2
    import numpy as np
    import onnx
    spec = importlib.util.spec_from_file_location('audited_minifasnet', args.cache / 'MiniFASNet.py')
    source = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(source)
    torch.set_num_threads(1)
    model = source.MiniFASNetV2(conv6_kernel=(5, 5)).eval()
    state = torch.load(args.cache / 'model.pth', map_location='cpu', weights_only=True)
    model.load_state_dict({key.removeprefix('module.'): value for key, value in state.items()}, strict=True)
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / 'minifasnet-v2.onnx'
    if target.exists():
        raise ValueError('Output exists; refuse replacement')
    example = torch.from_numpy(np.random.default_rng(42).integers(0, 256, (1, 3, 80, 80)).astype(np.float32))
    torch.onnx.export(model, example, target, opset_version=11, dynamo=False,
                      input_names=['image'], output_names=['logits'])
    onnx.checker.check_model(onnx.load(target))
    network = cv2.dnn.readNetFromONNX(str(target))
    errors = []
    for seed in range(5):
        data = np.random.default_rng(seed).integers(0, 256, (1, 3, 80, 80)).astype(np.float32)
        with torch.no_grad():
            expected = model(torch.from_numpy(data)).numpy()
        network.setInput(data)
        actual = network.forward()
        errors.append(float(np.max(np.abs(expected - actual))))
        if not np.allclose(expected, actual, atol=0.001, rtol=0.001):
            raise ValueError('OpenCV export parity failed')
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    # The device permits exactly this audited export; parity alone must not install another artifact.
    if digest != 'b5156dece1bdc64a6806d037a783a2e3db178fb054aa71c6518992de68d5b841':
        raise ValueError('Export differs from the pinned device artifact; review environment before deployment')
    shutil.copyfile(args.cache / 'LICENSE', args.output / 'MINIFASNET-LICENSE')
    report = {'upstream_commit': COMMIT, 'upstream_weights_sha256': ASSETS['model.pth'][1],
              'onnx_sha256': digest, 'torch_opencv_max_errors': errors, 'parity_passed': True,
              'input': 'BGR NCHW 80x80 float32, unnormalized 0..255',
              'live_class_index': 1, 'crop_scale': 2.7,
              'scope': 'export parity only; not a biometric attack evaluation'}
    (args.output / 'pad-export.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
