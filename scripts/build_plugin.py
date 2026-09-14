"""Build a self-contained plugin, its upload archive and a local marketplace, without user media/secrets.

dist/
  video-maker/                      plugin root (Claude and ChatGPT/Codex manifests)
  video-maker.zip                   upload file for Claude Desktop (Cowork)
  .claude-plugin/marketplace.json   local marketplace for Claude Code
  .agents/plugins/marketplace.json  local marketplace for ChatGPT desktop / Codex
"""
import datetime
import json
import shutil
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
dist = root / "dist"
out = dist / "video-maker"
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

# Installed plugins are cached per version string, so every build gets a distinct one;
# otherwise a reinstall can keep serving the previous build's files.
stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d%H%M%S")
for manifest in [out / ".claude-plugin" / "plugin.json", out / ".codex-plugin" / "plugin.json"]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["version"] = f"{data['version'].split('+')[0]}+build.{stamp}"
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
version = data["version"]

archive = dist / "video-maker.zip"
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for path in sorted(out.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            z.write(path, path.relative_to(out))
# Claude Desktop's upload accepts .zip only; drop the .plugin copy older builds produced.
(dist / "video-maker.plugin").unlink(missing_ok=True)

description = "録画素材をVOICEVOX・立ち絵・字幕で解説動画に編集するローカルツール。"
marketplace = "video-maker-local"
claude = dist / ".claude-plugin" / "marketplace.json"
claude.parent.mkdir(exist_ok=True)
claude.write_text(json.dumps({
    "name": marketplace,
    "owner": {"name": "takuma"},
    "description": "Video Makerのローカル配布用マーケットプレイス。",
    "plugins": [{"name": "video-maker", "source": "./video-maker", "description": description}],
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
codex = dist / ".agents" / "plugins" / "marketplace.json"
codex.parent.mkdir(parents=True, exist_ok=True)
codex.write_text(json.dumps({
    "name": marketplace,
    "interface": {"displayName": "Video Maker (local)"},
    "plugins": [{"name": "video-maker",
                 "source": {"source": "local", "path": "./video-maker"},
                 "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                 "category": "Productivity"}],
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(json.dumps({"plugin": str(out), "version": version, "archive": str(archive),
                  "marketplace": str(dist), "marketplace_name": marketplace,
                  "bytes": archive.stat().st_size}, ensure_ascii=False, indent=2))
