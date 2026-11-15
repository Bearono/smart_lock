"""Compatibility entry point; implementation lives in apps/device/AesCBCalgorithm.py."""
try:
    from ._compat import export_module
except ImportError:
    from _compat import export_module

export_module('AesCBCalgorithm', globals())
