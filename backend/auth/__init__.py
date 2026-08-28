"""Credential and session primitives: password hashing and signed session tokens.

Pure functions with no FastAPI or database imports, mirroring how ``backend/nutrition``
sits apart from ``backend/api``. The HTTP layer (``backend/api/auth.py``, ``deps.py``) is
the only caller.
"""
