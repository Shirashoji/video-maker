import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image

from .engine import load, scene_duration_for, synthesize_narration, validate
from .media import doctor, duration as media_duration, inside, probe, resolve_input
from .models import Project, Voice
from .service import Service
from .voicevox import Voicevox
from . import characters
from .templates import keynote_template


def create_server(root: Path):
    service = Service(root)
    mcp = FastMCP("video-maker", instructions="Edit existing local media using a validated JSON timeline. Author diagrams, animated slides and styled telops with scene.graphics; use source_rect for picture-in-picture recordings. Paths are relative to the workspace. Start with project_schema and inspect_media; save a project, render_preview, poll job_status, and visually inspect frames before render_final. No generative video or external uploads.")

    @mcp.tool()
    def workspace_info() -> dict:
        """Get the persistent workspace and its projects: name, notes (handoff memo), revision, last modified time and latest completed render.

        Every client using this workspace (Claude Cowork, ChatGPT Work, Codex, CLI) sees the same
        projects. Call it first, then read_project the one to continue and follow its notes.
        """
        return {"workspace": str(service.root), "projects": service.projects()}

    @mcp.tool()
    def environment_status() -> dict:
        """Check local editing binaries and VOICEVOX connectivity."""
        status = doctor()
        try:
            status["voicevox_version"] = Voicevox().request("/version").decode()
        except RuntimeError as e:
            status["voicevox_error"] = str(e)
        return status

    @mcp.tool()
    def project_schema() -> dict:
        """Get strict schema for scenes, narration, characters, graphics, animated keyframes and styled telops."""
        return Project.model_json_schema()

    @mcp.tool()
    def presentation_template(style: Literal["minimal", "colorful"] = "minimal",
                              title: str = "アイデアを、動かそう。",
                              subtitle: str = "映像と図解で、もっと伝わる。",
                              source: str | None = None) -> dict:
        """Get editable keynote-style JSON: hero, staggered cards, optional recording/zoom, closing.

        No file is saved. Replace placeholder copy with source-backed claims, then save_project.
        source is an imported workspace-relative recording. minimal is dark; colorful is light.
        """
        if source:
            inside(service.root, source)
        return keynote_template(style, title, subtitle, source)

    @mcp.tool()
    def import_asset(source: str) -> dict:
        """Copy a user-selected absolute local media/PSD/font path into workspace/assets. Never changes the original. Returns the project-relative path. inspect_media accepts the same absolute path, so check a recording before importing it."""
        return service.import_asset(source)

    @mcp.tool()
    def export_render(job_id: str, destination: str,
                      items: list[Literal["video", "captions", "project", "timeline", "credits"]] | None = None,
                      overwrite: bool = False) -> dict:
        """Copy a completed render out of the workspace to a user-chosen folder (or a full file path for a single item). The counterpart of import_asset."""
        return service.export(job_id, destination, tuple(items or ("video", "captions")), overwrite)

    @mcp.tool()
    def list_assets() -> list[str]:
        """List media under workspace/assets. Copy user-authorized source files there first."""
        folder = service.root / "assets"
        return sorted(str(p.relative_to(service.root)) for p in folder.rglob("*") if p.is_file()) if folder.exists() else []

    @mcp.tool()
    def psd_layers(path: str) -> list[dict]:
        """List PSD layer paths, names and visibility to select character expressions."""
        return characters.layers(service.root, path)

    @mcp.tool()
    def export_character(path: str, visibility: dict[str, bool]) -> dict:
        """Export transparent PNG with explicit PSD visibility overrides; source PSD remains intact. Disable sibling mouth layers when selecting a mouth. Export closed/open sprites with the same canvas."""
        return characters.export(service.root, path, visibility)

    @mcp.tool()
    def inspect_media(path: str) -> dict:
        """Inspect duration, codecs, dimensions, frame rate and audio tracks. Accepts a workspace path or an absolute path, so a recording can be checked before import_asset copies it in."""
        return probe(resolve_input(service.root, path))

    @mcp.tool()
    def inspect_frames(path: str, count: int = 6, start: float | None = None,
                       end: float | None = None) -> Image:
        """Return an image contact sheet to visually inspect source media or rendered video. Give start/end to aim at a cut, a telop entrance or one scene instead of sampling the whole file. Accepts an absolute path."""
        result = service.contact_sheet(path, count, start, end)
        return Image(path=result["sheet"])

    @mcp.tool()
    def extract_frame(path: str, time: float, width: int = 1280):
        """Return one frame at an exact timestamp, large enough to read on-screen text and describe what it shows.

        Use this when a moment matters: what a UI displays at 12.4s, whether a telop is
        readable, what a cut lands on. inspect_frames spreads thumbnails over a range;
        this keeps one frame near native size. Accepts an absolute path. The PNG is saved
        in the workspace, so a frame worth keeping can be reused as an image graphic.
        """
        result = service.frame(path, time, width)
        return [Image(path=result["image"]), json.dumps(result, ensure_ascii=False)]

    @mcp.tool()
    def detect_silence(path: str, threshold_db: float = -35, minimum: float = 0.5) -> dict:
        """Find candidate quiet ranges; silence is not proof a screen-recording section is unnecessary."""
        return service.silence(path, threshold_db, minimum)

    @mcp.tool()
    def voicevox_speakers() -> list[dict]:
        """Get installed VOICEVOX characters/styles and their numeric speaker IDs."""
        return Voicevox().speakers()

    @mcp.tool()
    def synthesize_voice(text: str, speaker: int, speed: float = 1, readings: dict[str, str] | None = None,
                         fps: Literal[24, 25, 30, 60] = 30, transition_seconds: float = 0.4) -> dict:
        """Audition narration and get its measured length. Splits into caption-sized phrases exactly as a render does, so duration, per-caption times and the scene_duration a scene would take are exact, not approximations."""
        # Keyed by the request, so repeated auditions reuse one file instead of
        # leaving a new WAV behind on every call.
        key = hashlib.sha256(json.dumps([text, speaker, speed, readings], sort_keys=True,
                                        ensure_ascii=False).encode()).hexdigest()[:32]
        audio = service.root / ".cache" / "auditions" / f"{key}.wav"
        audio.parent.mkdir(parents=True, exist_ok=True)
        _, _, chunks = synthesize_narration(service.root, Voice(text=text, speaker=speaker, speed=speed),
                                            audio, readings)
        length = media_duration(audio)
        return {"audio": str(audio), "duration": length, "chunks": chunks,
                "scene_duration": scene_duration_for(length, fps, transition_seconds)}

    @mcp.tool()
    def read_project(path: str) -> dict:
        """Read a saved editable timeline. Returns project, notes inside it, and revision; pass revision as save_project base_revision."""
        return service.read(path)

    @mcp.tool()
    def save_project(path: str, project: dict, overwrite: bool = False,
                     base_revision: str | None = None) -> dict:
        """Validate and save a JSON project; overwrites retain a revision for undo.

        Pass the revision from read_project as base_revision: if another session (for example
        ChatGPT Work while you edit in Claude Cowork) saved in between, the save is refused
        instead of discarding their edit. Keep project.notes current for the next editor.
        """
        return service.save(path, project, overwrite, base_revision)

    @mcp.tool()
    def export_project(path: str, destination: str, overwrite: bool = False) -> dict:
        """Pack a project JSON and every asset it references into one .videomaker.zip in a user-chosen folder, for another Mac, person or workspace. Renders are not included."""
        return service.export_project(path, destination, overwrite)

    @mcp.tool()
    def import_project(bundle: str, path: str | None = None, overwrite: bool = False,
                       base_revision: str | None = None) -> dict:
        """Unpack a .videomaker.zip from export_project into this workspace. Assets keep their relative paths; identical files are reused and differing ones are never overwritten. Read the returned notes before editing."""
        return service.import_project(bundle, path, overwrite, base_revision)

    @mcp.tool()
    def validate_project(path: str) -> dict:
        """Check schema and assets; exact narration fit is checked during render."""
        return validate(service.root, load(service.root, path))

    @mcp.tool()
    def plan_timeline(path: str) -> dict:
        """Dry run: resolve final scene durations, caption times, graphic times and camera framing without rendering. Use before writing graphics so their start/end are known to fit, and to read each scene's display_rect for camera coordinates. Also warms the narration cache."""
        return service.plan_timeline(path)

    @mcp.tool()
    def render_preview(path: str, scenes: list[str] | None = None, width: int = 640) -> dict:
        """Queue a downscaled preview. Poll job_status using returned job_id. Pass scenes to render only those scene ids, and a larger width (up to the project width) when on-screen text must be legible; times in a partial render restart at zero."""
        return service.start(path, preview=True, scenes=scenes, width=width)

    @mcp.tool()
    def render_final(path: str) -> dict:
        """Queue H.264/AAC MP4 at project resolution, SRT, credits and reproducible timeline."""
        return service.start(path, preview=False)

    @mcp.tool()
    def job_status(job_id: str) -> dict:
        """Get queued/running/complete/failed/interrupted status and output paths."""
        return service.status(job_id)

    return mcp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    create_server(args.workspace).run(transport="stdio")


if __name__ == "__main__":
    main()
