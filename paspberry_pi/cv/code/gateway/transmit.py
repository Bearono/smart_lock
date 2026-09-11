"""Compatibility entry point; implementation lives in paspberry_pi/transmit.py."""
try:
    from ._compat import export_module
except ImportError:
    from _compat import export_module

export_module('transmit', globals())
