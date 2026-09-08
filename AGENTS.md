# Video Maker

This repository supplies local editing tools to AI agents. It edits existing media; it does not generate video imagery.

For video creation or editing, read `skills/video-editing/SKILL.md` and use the MCP or the CLI described there. User media belongs in `workspace/assets/`; original files should be preserved. `workspace/` is excluded from version control because it contains user-provided media and render output.

For implementation changes, run `.venv/bin/python -m pytest -q`. Use `uv sync --extra dev` if the virtual environment is missing. Core rendering uses FFmpeg; text is rasterized with Pillow so FFmpeg does not require libass/drawtext. The strict project schema is generated from `src/video_maker/models.py`; regenerate `docs/project.schema.json` after changing models.
