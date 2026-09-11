"""Compatibility entry point; implementation lives in paspberry_pi/security_protocol.py."""
try:
    from ._compat import export_module
except ImportError:
    from _compat import export_module

export_module('security_protocol', globals())
