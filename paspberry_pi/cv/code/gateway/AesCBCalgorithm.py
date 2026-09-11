"""Compatibility entry point; implementation lives in paspberry_pi/AesCBCalgorithm.py."""
try:
    from ._compat import export_module
except ImportError:
    from _compat import export_module

export_module('AesCBCalgorithm', globals())
