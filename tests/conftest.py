"""Shared pytest setup — tests run read-only against the seeded database."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("MEDIA_DESK_ADMIN_TOKEN", "test-token")
