"""MFA HTTP composition. Keep endpoint names and URL prefixes stable."""

from flask import Blueprint

mfa_bp = Blueprint("mfa", __name__)

# Import once after creating the blueprint; each module owns one endpoint group.
from . import credentials, bindings, door, guests  # noqa: E402,F401
