"""Load the maintained device implementation for legacy entry points."""
import importlib.util
from pathlib import Path
import sys

DEVICE_ROOT = Path(__file__).resolve().parents[3]


def export_module(name, namespace):
    root = str(DEVICE_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    module_name = '_smart_lock_device_' + name
    module = sys.modules.get(module_name)
    if module is None:
        spec = importlib.util.spec_from_file_location(module_name, DEVICE_ROOT / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    namespace.update({key: value for key, value in vars(module).items() if not key.startswith('__')})
