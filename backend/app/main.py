"""Expose the assembled application for ASGI servers."""

from app.bootstrap import create_app

app = create_app()
