"""
Vercel serverless entrypoint for the FastAPI app.
Expose a top-level variable `app` (the ASGI callable) so the @vercel/python builder can serve it.
This file ensures the repository root is on sys.path so `from app import app` works.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Import the FastAPI instance from the main application module
from app import app as fastapi_app  # noqa: E402

# Expose as `app` for the Vercel Python adapter
app = fastapi_app
