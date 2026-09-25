"""Vercel Serverless Function Handler for FastAPI Backend."""

import os
import sys
from pathlib import Path

# Setup Python paths for root and src
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))
sys.path.insert(0, str(root_dir))

from app.main import create_app

app = create_app()
