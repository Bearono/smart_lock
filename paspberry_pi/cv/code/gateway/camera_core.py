"""Compatibility entry point; implementation lives in paspberry_pi/camera_core.py."""
try:
    from ._compat import export_module
except ImportError:
    from _compat import export_module

export_module('camera_core', globals())
