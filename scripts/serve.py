"""Stable absolute-path MCP entry point; no working-directory dependency."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + "/opt/homebrew/bin:/usr/local/bin"

from video_maker.server import main

main()
