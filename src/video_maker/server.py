import argparse
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image

from .engine import load, validate
from .media import doctor, inside, probe
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
        """Get the persistent workspace and available top-level project JSON files."""
        return {"workspace": str(service.root), "projects": sorted(p.name for p in service.root.glob("*.json") if p.is_file())}

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
        """Copy a user-selected absolute local media/PSD/font path into workspace/assets. Never changes the original. Returns the project-relative path."""
        return service.import_asset(source)

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
        """Inspect duration, codecs, dimensions, frame rate and audio tracks."""
        return probe(inside(service.root, path))

    @mcp.tool()
    def inspect_frames(path: str, count: int = 6) -> Image:
        """Return an image contact sheet to visually inspect source media or rendered video."""
        result = service.contact_sheet(path, count)
        return Image(path=result["sheet"])

    @mcp.tool()
    def detect_silence(path: str, threshold_db: float = -35, minimum: float = 0.5) -> dict:
        """Find candidate quiet ranges; silence is not proof a screen-recording section is unnecessary."""
        return service.silence(path, threshold_db, minimum)

    @mcp.tool()
    def voicevox_speakers() -> list[dict]:
        """Get installed VOICEVOX characters/styles and their numeric speaker IDs."""
        return Voicevox().speakers()

    @mcp.tool()
    def synthesize_voice(text: str, speaker: int, speed: float = 1) -> dict:
        """Generate a local cached WAV to audition narration."""
        path = Voicevox().synthesize(Voice(text=text, speaker=speaker, speed=speed), service.root / ".cache" / "voicevox")
        return {"audio": str(path)}

    @mcp.tool()
    def read_project(path: str) -> dict:
        """Read a saved editable timeline."""
        return load(service.root, path).model_dump(mode="json")

    @mcp.tool()
    def save_project(path: str, project: dict, overwrite: bool = False) -> dict:
        """Validate and save a JSON project; overwrites retain a revision for undo."""
        return service.save(path, project, overwrite)

    @mcp.tool()
    def validate_project(path: str) -> dict:
        """Check schema and assets; exact narration fit is checked during render."""
        return validate(service.root, load(service.root, path))

    @mcp.tool()
    def render_preview(path: str) -> dict:
        """Queue a low-resolution full-timeline preview. Poll job_status using returned job_id."""
        return service.start(path, preview=True)

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
