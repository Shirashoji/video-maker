import json
import shutil
import subprocess
from pathlib import Path


def run(args: list[str], timeout: int = 3600) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed: {result.stderr[-6000:]}")
    return result.stdout


def probe(path: Path) -> dict:
    return json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                           "-of", "json", str(path)], timeout=30))


def duration(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def ffmpeg(args: list[str]) -> None:
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
         "-filter_complex_threads", "1", *args])


def inside(root: Path, value: str, exists: bool = True) -> Path:
    p = (root / value).resolve()
    if not p.is_relative_to(root.resolve()):
        raise ValueError(f"Path must be inside workspace: {value}")
    if exists and not p.is_file():
        raise ValueError(f"File not found: {value}")
    return p


def resolve_input(root: Path, value: str) -> Path:
    """Resolve a read-only inspection path.

    Accepts a workspace-relative path or an existing absolute path, so a recording
    can be examined before import_asset copies it in. Assets referenced by a project
    still go through inside(), keeping saved projects portable and workspace-bound.
    """
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
        if resolved.is_dir():
            raise ValueError(f"{value} is a directory; choose a file")
        raise ValueError(f"File not found: {value}")
    return inside(root, value)


def doctor() -> dict:
    from .web_render import find_chrome_executable, find_mmdc_executable, HAS_RESVG
    return {
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "chrome": find_chrome_executable(),
        "mmdc": find_mmdc_executable(),
        "resvg": HAS_RESVG,
    }
