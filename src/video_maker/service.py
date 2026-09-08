import concurrent.futures
import json
import re
import threading
import uuid
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from .engine import load, render, validate
from .media import ffmpeg, inside, probe, run
from .models import Project


class Service:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.jobs = {}
        self.lock = threading.Lock()

    def import_asset(self, source: str):
        """Copy a user-selected local asset without modifying the original."""
        path = Path(source).expanduser().resolve()
        allowed = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".png", ".jpg", ".jpeg",
                   ".webp", ".bmp", ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".psd", ".ttf", ".otf", ".ttc"}
        if not path.is_file() or path.suffix.lower() not in allowed:
            raise ValueError("Choose a supported local media, PSD or font file")
        folder = self.root / "assets" / "imports" / uuid.uuid4().hex
        folder.mkdir(parents=True)
        destination = folder / path.name
        shutil.copyfile(path, destination)
        return {"path": str(destination.relative_to(self.root)), "original": str(path)}

    def save(self, path: str, project: dict, overwrite=False):
        target = inside(self.root, path, exists=False)
        if target.suffix != ".json":
            raise ValueError("project path must end in .json")
        value = Project.model_validate(project)
        validate(self.root, value)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not overwrite:
                raise ValueError("Project exists; set overwrite=true to revise it")
            # Revisions remain available for undo/review.
            old = target.read_bytes()
            backup = self.root / "revisions" / f"{uuid.uuid4().hex}.json"
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(old)
        target.write_text(value.model_dump_json(indent=2), encoding="utf-8")
        return {"project": str(target), "valid": True}

    def start(self, path: str, preview=True):
        # Snapshot now, so queued jobs are not affected by later edits.
        project = load(self.root, path)
        validate(self.root, project)
        job_id = uuid.uuid4().hex
        snapshot = self.root / "jobs" / f"{job_id}.json"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(project.model_dump_json(indent=2))
        self.jobs[job_id] = {"id": job_id, "status": "queued", "progress": "Queued"}

        def update(**values):
            with self.lock:
                self.jobs[job_id].update(values)
                (snapshot.parent / f"{job_id}.status.json").write_text(json.dumps(self.jobs[job_id], ensure_ascii=False))

        def worker():
            update(status="running")
            try:
                result = render(self.root, str(snapshot), preview, lambda p: update(progress=p))
                update(status="complete", result=result)
            except Exception as e:
                update(status="failed", error=str(e))

        self.pool.submit(worker)
        return {"job_id": job_id, "status": "queued"}

    def status(self, job_id):
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise ValueError("Invalid job id")
        with self.lock:
            if job_id in self.jobs:
                return dict(self.jobs[job_id])
        path = inside(self.root, f"jobs/{job_id}.status.json")
        result = json.loads(path.read_text())
        if result["status"] in ("running", "queued"):
            result.update(status="interrupted", error="Server restarted; submit render again")
        return result

    def contact_sheet(self, path: str, count=6):
        if not 1 <= count <= 24:
            raise ValueError("count must be 1..24")
        source = inside(self.root, path)
        meta = probe(source)
        length = float(meta["format"]["duration"])
        output = self.root / "inspection" / uuid.uuid4().hex
        output.mkdir(parents=True)
        sheet = Image.new("RGB", (960, 205 * ((count + 2)//3)), "#0a1120")
        draw = ImageDraw.Draw(sheet)
        samples = []
        for i in range(count):
            timestamp = length * (i + 0.5) / count
            image = output / f"frame-{i}.png"
            ffmpeg(["-ss", str(timestamp), "-i", str(source), "-frames:v", "1",
                    "-vf", "scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2", str(image)])
            with Image.open(image) as frame:
                sheet.paste(frame, (i % 3 * 320, i // 3 * 205))
            draw.text((i % 3 * 320 + 8, i // 3 * 205 + 184), f"{timestamp:.2f}s", fill="white")
            samples.append({"time": timestamp, "image": str(image)})
        path = output / "contact-sheet.jpg"
        sheet.save(path, quality=90)
        return {"sheet": str(path), "frames": samples}

    def silence(self, path: str, threshold_db=-35.0, minimum=0.5):
        if not -90 <= threshold_db <= 0 or not 0.05 <= minimum <= 30:
            raise ValueError("Invalid silence threshold or duration")
        import subprocess
        p = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(inside(self.root, path)),
                            "-af", f"silencedetect=noise={threshold_db}dB:d={minimum}", "-vn", "-f", "null", "-"],
                           capture_output=True, text=True, timeout=3600)
        if p.returncode:
            raise RuntimeError(p.stderr[-4000:])
        starts = re.findall(r"silence_start: ([\d.]+)", p.stderr)
        ends = re.findall(r"silence_end: ([\d.]+)", p.stderr)
        return {"silences": [{"start": float(a), "end": float(b)} for a, b in zip(starts, ends)],
                "note": "Candidate cuts only. Inspect screen content before removing quiet sections."}
