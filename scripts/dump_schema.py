"""Regenerate docs/project.schema.json from the models (see AGENTS.md)."""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from video_maker.models import Project  # noqa: E402

target = root / "docs" / "project.schema.json"
target.write_text(json.dumps(Project.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8")
print(target)
