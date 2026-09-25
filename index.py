"""Index entrypoint for FastAPI application (Vercel & serverless discovery)."""

import sys
from pathlib import Path

# Add src and root to path
root_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(root_dir / "src"))
sys.path.insert(0, str(root_dir))

from app.main import app, create_app

__all__ = ["app", "create_app"]
