"""Vercel API Main Serverless Handler."""

import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))
sys.path.insert(0, str(root_dir))

from app.main import app, create_app

__all__ = ["app", "create_app"]
