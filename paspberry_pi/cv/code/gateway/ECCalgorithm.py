"""Compatibility entry point; implementation lives in paspberry_pi/ECCalgorithm.py."""
try:
    from ._compat import export_module
except ImportError:
    from _compat import export_module

export_module('ECCalgorithm', globals())
