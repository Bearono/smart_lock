"""Compatibility entry point; implementation lives in paspberry_pi/app.py."""
try:
    from ._compat import export_module
except ImportError:
    from _compat import export_module

export_module('app', globals())

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
