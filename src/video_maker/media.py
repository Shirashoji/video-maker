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


def doctor() -> dict:
    return {"ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe")}
