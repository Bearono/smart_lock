"""Compatibility entry point; implementation lives in apps/device/ECCalgorithm.py."""
try:
    from ._compat import export_module
except ImportError:
    from _compat import export_module

export_module('ECCalgorithm', globals())
