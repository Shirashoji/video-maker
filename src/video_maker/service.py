import concurrent.futures
import json
import re
import threading
import uuid
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from .engine import load, plan, render, validate
from .media import ffmpeg, inside, probe, resolve_input, run
from .models import Project


class Service:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.jobs = {}
        self.lock = threading.Lock()

    ALLOWED_IMPORTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".png", ".jpg", ".jpeg",
                       ".webp", ".bmp", ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".psd",
                       ".ttf", ".otf", ".ttc"}

    def import_asset(self, source: str):
        """Copy a user-selected local asset without modifying the original."""
        path = Path(source).expanduser().resolve()
        # Say which of the two things is wrong; a missing file and an unsupported
        # extension are different mistakes.
        if path.is_dir():
            raise ValueError(f"{source} is a directory; choose a file")
        if not path.exists():
            raise ValueError(f"File not found: {source}")
        if not path.is_file():
            raise ValueError(f"Not a regular file: {source}")
        if path.suffix.lower() not in self.ALLOWED_IMPORTS:
            raise ValueError(f"Unsupported file type '{path.suffix or path.name}'. "
                             f"Supported: {' '.join(sorted(self.ALLOWED_IMPORTS))}")
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

    def start(self, path: str, preview=True, scenes=None, width=640):
        if not 160 <= width <= 3840:
            raise ValueError("width must be 160..3840")
        # Snapshot now, so queued jobs are not affected by later edits.
        project = load(self.root, path)
        if scenes:
            known = {s.id for s in project.scenes}
            missing = [s for s in scenes if s not in known]
            if missing:
                raise ValueError(f"Unknown scene ids: {' '.join(missing)}")
            selected = [s for s in project.scenes if s.id in set(scenes)]
            # A subset starts at its own zero, so the first scene cannot cross-fade
            # into a scene that is not being rendered.
            selected[0] = selected[0].model_copy(update={"transition": "cut"})
            project = project.model_copy(update={"scenes": selected})
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
                result = render(self.root, str(snapshot), preview, lambda p: update(progress=p), width)
                update(status="complete", result=result)
            except Exception as e:
                update(status="failed", error=str(e))

        self.pool.submit(worker)
        job = {"job_id": job_id, "status": "queued"}
        if scenes:
            job["scenes"] = list(scenes)
            job["note"] = "Partial render; times restart at zero and differ from the full timeline."
        return job

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

    EXPORTABLE = ("video", "captions", "project", "timeline", "credits")

    def export(self, job_id: str, destination: str, items=("video", "captions"), overwrite=False):
        """Copy finished render artifacts out of the workspace: the counterpart of import_asset."""
        job = self.status(job_id)
        if job["status"] != "complete":
            raise ValueError(f"Job {job_id} is {job['status']}; export after it completes")
        unknown = [i for i in items if i not in self.EXPORTABLE]
        if unknown:
            raise ValueError(f"Unknown items: {' '.join(unknown)}. "
                             f"Choose from: {' '.join(self.EXPORTABLE)}")
        target = Path(destination).expanduser().resolve()
        if target.is_dir():
            folder, rename = target, None
        elif len(items) == 1 and target.parent.is_dir():
            folder, rename = target.parent, target.name
        else:
            raise ValueError(f"Destination directory not found: {destination}")
        exported = {}
        for item in items:
            source = Path(job["result"][item])
            copy = folder / (rename or source.name)
            if copy.exists() and not overwrite:
                raise ValueError(f"{copy} exists; set overwrite=true to replace it")
            shutil.copyfile(source, copy)
            exported[item] = str(copy)
        return {"exported": exported}

    def plan_timeline(self, path: str):
        """Resolve scene durations, caption times and camera framing without rendering."""
        project = load(self.root, path)
        build = self.root / ".cache" / "plan" / uuid.uuid4().hex
        build.mkdir(parents=True)
        try:
            resolved, issues = plan(self.root, project, build, strict=False)
        finally:
            shutil.rmtree(build, ignore_errors=True)
        for scene in resolved:
            # The measuring WAVs are gone; their paths would only mislead.
            scene.pop("audio", None)
        total = resolved[-1]["start"] + resolved[-1]["duration"]
        return {"total_duration": total, "fps": project.fps,
                "size": [project.width, project.height], "scenes": resolved, "issues": issues,
                "note": ("Scene durations are final. Write graphics, captions and camera times "
                         "against them, or use \"scene_end-0.5\" style relative times.")}

    def contact_sheet(self, path: str, count=6, start=None, end=None):
        if not 1 <= count <= 24:
            raise ValueError("count must be 1..24")
        source = resolve_input(self.root, path)
        meta = probe(source)
        length = float(meta["format"]["duration"])
        # Sampling a range matters for cuts and telop entrances, which an evenly
        # spread whole-file sheet will usually miss.
        first = 0.0 if start is None else float(start)
        last = length if end is None else float(end)
        if not 0 <= first < length:
            raise ValueError(f"start must be within 0..{length:.2f}s")
        if not first < last <= length + 1e-6:
            raise ValueError(f"end must be after start and within {length:.2f}s")
        span = last - first
        output = self.root / "inspection" / uuid.uuid4().hex
        output.mkdir(parents=True)
        sheet = Image.new("RGB", (960, 205 * ((count + 2)//3)), "#0a1120")
        draw = ImageDraw.Draw(sheet)
        samples = []
        for i in range(count):
            timestamp = first + span * (i + 0.5) / count
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

    def frame(self, path: str, at: float, width: int = 1280):
        """Extract one frame at an exact timestamp, large enough to read and describe.

        contact_sheet answers "what happens across this range"; this answers "what is
        on screen at this moment", so it keeps the frame near its native size instead
        of shrinking it to a thumbnail. The PNG lands in the workspace, so a frame
        worth keeping can be reused as an image graphic.
        """
        if not 160 <= width <= 3840:
            raise ValueError("width must be 160..3840")
        source = resolve_input(self.root, path)
        meta = probe(source)
        length = float(meta["format"]["duration"])
        if not 0 <= at <= length + 1e-6:
            raise ValueError(f"time must be within 0..{length:.2f}s")
        stream = next((s for s in meta["streams"] if s["codec_type"] == "video"), None)
        if not stream:
            raise ValueError(f"{path} has no video stream to take a frame from")
        # Seeking past the last frame decodes nothing, so land on the final frame
        # instead of failing on a timestamp the file technically still covers.
        rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
        top, _, bottom = rate.partition("/")
        fps = float(top) / float(bottom) if float(bottom or 0) and float(top) else 0
        seek = min(at, max(0.0, length - (1 / fps if fps else 0.04)))
        output = self.root / "inspection" / uuid.uuid4().hex
        output.mkdir(parents=True)
        image = output / f"frame-{seek:.3f}s.png"
        # Never upscale; a frame invented by interpolation is not what was recorded.
        scale = [] if int(stream["width"]) <= width else ["-vf", f"scale={width//2*2}:-2"]
        ffmpeg(["-ss", str(seek), "-i", str(source), "-frames:v", "1", *scale, str(image)])
        if not image.is_file():
            raise ValueError(f"No frame decoded at {seek:.3f}s of {path}")
        with Image.open(image) as frame:
            size = frame.size
        return {"image": str(image), "relative_path": str(image.relative_to(self.root)),
                "time": seek, "requested_time": at, "size": list(size),
                "source_size": [int(stream["width"]), int(stream["height"])],
                "source_duration": length}

    def silence(self, path: str, threshold_db=-35.0, minimum=0.5):
        if not -90 <= threshold_db <= 0 or not 0.05 <= minimum <= 30:
            raise ValueError("Invalid silence threshold or duration")
        import subprocess
        p = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(resolve_input(self.root, path)),
                            "-af", f"silencedetect=noise={threshold_db}dB:d={minimum}", "-vn", "-f", "null", "-"],
                           capture_output=True, text=True, timeout=3600)
        if p.returncode:
            raise RuntimeError(p.stderr[-4000:])
        starts = re.findall(r"silence_start: ([\d.]+)", p.stderr)
        ends = re.findall(r"silence_end: ([\d.]+)", p.stderr)
        return {"silences": [{"start": float(a), "end": float(b)} for a, b in zip(starts, ends)],
                "note": "Candidate cuts only. Inspect screen content before removing quiet sections."}
