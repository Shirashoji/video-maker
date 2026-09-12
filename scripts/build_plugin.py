"""Build a self-contained plugin directory and archive without user media/secrets."""
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root / "dist" / "video-maker"
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True, exist_ok=True)
for name in [".codex-plugin", ".claude-plugin", "src", "skills", "docs", "examples"]:
    shutil.copytree(root / name, out / name, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
for name in [".mcp.json", "pyproject.toml", "uv.lock", "README.md"]:
    shutil.copyfile(root / name, out / name)
(out / "scripts").mkdir(exist_ok=True)
for name in ["start-mcp.sh", "serve.py", "create_demo.py", "create_keynote_demo.py"]:
    shutil.copyfile(root / "scripts" / name, out / "scripts" / name)
archive = root / "dist" / "video-maker.zip"
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for path in sorted(out.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            z.write(path, path.relative_to(out))
with tempfile.TemporaryDirectory(prefix="video-maker-plugin-") as staging:
    staged = Path(staging) / "video-maker.plugin"
    shutil.copyfile(archive, staged)
    cowork_archive = root / "dist" / "video-maker.plugin"
    shutil.copyfile(staged, cowork_archive)
print(json.dumps({"plugin": str(out), "archive": str(archive), "cowork_archive": str(cowork_archive), "bytes": archive.stat().st_size}, indent=2))
