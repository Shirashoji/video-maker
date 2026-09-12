"""Behaviour reported as missing while editing a real video with the plugin."""
import io
import json
import time
import wave
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from video_maker.engine import (apply_readings, camera_focus, plan, prepare, resolve_time,
                                resolved_graphics, scene_duration_for, scene_layout)
from video_maker.media import ffmpeg, resolve_input
from video_maker.models import CameraKeyframe, Project
from video_maker.service import Service


def project(**kw):
    return Project(name="Test", width=320, height=240, fps=30, **kw)


def finish(service, job_id, timeout=60):
    deadline = time.monotonic() + timeout
    while service.status(job_id)["status"] in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(0.05)
    state = service.status(job_id)
    assert state["status"] == "complete", state
    return state


def still(path: Path, size=(300, 300)):
    Image.new("RGB", size, "#204060").save(path)
    return path


# --- inspecting before importing -------------------------------------------------

def test_inspect_accepts_absolute_path_but_projects_stay_confined(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.png"
    still(outside)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    assert resolve_input(workspace, str(outside)) == outside.resolve()
    with pytest.raises(ValueError, match="Path must be inside workspace"):
        resolve_input(workspace, "../escape.png")
    with pytest.raises(ValueError, match="File not found"):
        resolve_input(workspace, str(tmp_path / "missing.png"))
    with pytest.raises(ValueError, match="is a directory"):
        resolve_input(workspace, str(tmp_path))


def test_import_asset_distinguishes_missing_from_unsupported(tmp_path):
    service = Service(tmp_path)
    with pytest.raises(ValueError, match="File not found"):
        service.import_asset(str(tmp_path / "nope.mp4"))
    with pytest.raises(ValueError, match="is a directory"):
        service.import_asset(str(tmp_path))
    note = tmp_path / "note.txt"
    note.write_text("x")
    with pytest.raises(ValueError, match="Unsupported file type '.txt'"):
        service.import_asset(str(note))
    imported = service.import_asset(str(still(tmp_path / "frame.png")))
    assert (tmp_path / imported["path"]).is_file()


# --- getting finished renders out ------------------------------------------------

def test_export_render_rejects_unfinished_and_protects_existing(tmp_path):
    service = Service(tmp_path)
    service.jobs["a" * 32] = {"id": "a" * 32, "status": "running"}
    with pytest.raises(ValueError, match="is running; export after it completes"):
        service.export("a" * 32, str(tmp_path))

    service.save("p.json", project(scenes=[{"id": "a", "duration": 0.8}]).model_dump())
    job = service.start("p.json")["job_id"]
    finish(service, job)
    destination = tmp_path.parent / f"{tmp_path.name}-out"
    destination.mkdir()
    exported = service.export(job, str(destination))
    assert set(exported["exported"]) == {"video", "captions"}
    assert Path(exported["exported"]["video"]).is_file()
    with pytest.raises(ValueError, match="exists; set overwrite=true"):
        service.export(job, str(destination))
    assert service.export(job, str(destination), overwrite=True)
    renamed = service.export(job, str(destination / "final.mp4"), items=("video",), overwrite=True)
    assert Path(renamed["exported"]["video"]).name == "final.mp4"
    with pytest.raises(ValueError, match="Unknown items"):
        service.export(job, str(destination), items=("source",))
    with pytest.raises(ValueError, match="Destination directory not found"):
        service.export(job, str(tmp_path / "missing" / "deep"))


# --- knowing the duration before writing graphics --------------------------------

def test_relative_times_resolve_against_the_final_scene_length():
    assert resolve_time("scene_end", 4.0) == 4.0
    assert resolve_time("scene_end-0.5", 4.0) == pytest.approx(3.5)
    assert resolve_time(1.25, 4.0) == 1.25
    assert resolve_time(None, 4.0, default=4.0) == 4.0
    with pytest.raises(ValidationError):
        Project(name="x", scenes=[{"id": "s", "duration": 1,
                                   "graphics": [{"kind": "rect", "end": "scene_start"}]}])


def test_relative_graphic_and_caption_times_survive_a_render(tmp_path):
    p = project(scenes=[{"id": "a", "duration": 2,
                         "captions": [{"text": "終わり際", "start": "scene_end-0.8", "end": "scene_end"}],
                         "graphics": [{"kind": "rect", "start": 0.2, "end": "scene_end-0.5"},
                                      {"kind": "text", "text": "締め", "start": "scene_end-1"}]}])
    (tmp_path / "p.json").write_text(p.model_dump_json())
    resolved, issues = plan(tmp_path, p, tmp_path, strict=False)
    assert issues == []
    assert [(g["start"], g["end"]) for g in resolved[0]["graphics"]] == [(0.2, 1.5), (1.0, 2.0)]
    assert resolved[0]["captions"][0] == {"text": "終わり際", "start": 1.2, "end": 2.0}
    assert [(g.start, g.end) for g in resolved_graphics(p.scenes[0], 2.0)] == [(0.2, 1.5), (1.0, 2.0)]


def test_relative_time_past_the_scene_start_is_rejected(tmp_path):
    p = project(scenes=[{"id": "a", "duration": 1,
                         "graphics": [{"kind": "rect", "start": 0.9, "end": "scene_end-0.5"}]}])
    with pytest.raises(ValueError, match="graphic end must be after start"):
        prepare(tmp_path, p, tmp_path)


def test_plan_reports_every_problem_while_prepare_still_raises(tmp_path):
    wav = tmp_path / "audio.wav"
    ffmpeg(["-f", "lavfi", "-i", "sine=duration=2", "-c:a", "pcm_s16le", str(wav)])
    p = project(scenes=[{"id": "s", "audio": "audio.wav", "duration": 1,
                         "graphics": [{"kind": "rect", "start": 0.1, "end": 5}]}])
    build = tmp_path / "build"
    build.mkdir()
    resolved, issues = plan(tmp_path, p, build, strict=False)
    assert any("too short" in i for i in issues)
    assert any("extends past scene end" in i for i in issues)
    assert resolved[0]["required_duration"] > resolved[0]["duration"]
    assert resolved[0]["issues"] == issues
    with pytest.raises(ValueError, match="too short"):
        prepare(tmp_path, p, build)


def test_plan_timeline_cleans_up_and_reports_totals(tmp_path):
    service = Service(tmp_path)
    service.save("p.json", project(scenes=[{"id": "a", "duration": 1.5},
                                           {"id": "b", "duration": 2}]).model_dump())
    result = service.plan_timeline("p.json")
    assert result["total_duration"] == pytest.approx(3.5)
    assert [s["duration"] for s in result["scenes"]] == [1.5, 2.0]
    assert result["issues"] == []
    # The dry run measures narration in a scratch dir and leaves nothing behind.
    assert list((tmp_path / ".cache" / "plan").glob("*")) == []


def test_scene_duration_matches_what_prepare_chooses(tmp_path):
    wav = tmp_path / "audio.wav"
    ffmpeg(["-f", "lavfi", "-i", "sine=duration=1.5", "-ar", "48000", "-ac", "1",
            "-c:a", "pcm_s16le", str(wav)])
    p = project(transition_seconds=0.4, scenes=[{"id": "s", "audio": "audio.wav"}])
    build = tmp_path / "build"
    build.mkdir()
    resolved = prepare(tmp_path, p, build)
    predicted = scene_duration_for(resolved[0]["audio_duration"], p.fps, p.transition_seconds)
    assert predicted == pytest.approx(resolved[0]["duration"])


# --- camera vs graphics coordinates ----------------------------------------------

def test_scene_layout_reports_the_pillarboxed_picture(tmp_path):
    still(tmp_path / "shot.png", (300, 300))
    p = project(scenes=[{"id": "s", "source": "shot.png", "duration": 1}])
    layout = scene_layout(tmp_path, p, p.scenes[0])
    assert layout["source_size"] == [300, 300]
    # A square source in a 320x240 frame fits by height, leaving 40px bars each side.
    assert layout["content_rect_in_camera"] == pytest.approx([40 / 320, 0, 240 / 320, 1])
    assert layout["content_rect"] == pytest.approx([40 / 320, 0, 240 / 320, 1])


def test_scene_layout_follows_crop_and_source_rect(tmp_path):
    still(tmp_path / "shot.png", (300, 300))
    p = project(scenes=[{"id": "s", "source": "shot.png", "duration": 1,
                         "crop": [0, 0, 0.5, 1], "source_rect": [0.5, 0, 0.5, 1]}])
    layout = scene_layout(tmp_path, p, p.scenes[0])
    assert layout["cropped_size"] == [150, 300]
    assert layout["display_rect"] == pytest.approx([0.5, 0, 160 / 320, 1])
    # 150x300 into the 160x240 window fits by height: 120x240, centred in the window.
    assert layout["content_rect"] == pytest.approx([0.5 + 20 / 320, 0, 120 / 320, 1])


def test_camera_focus_shows_the_clamped_target():
    keys = [CameraKeyframe(time=0, zoom=1, x=0.85, y=0.5),
            CameraKeyframe(time=1, zoom=2, x=0.85, y=0.5)]
    focus = camera_focus(keys)
    assert focus[0]["effective_x"] == pytest.approx(0.5)
    assert focus[1]["effective_x"] == pytest.approx(0.75)
    assert focus[1]["visible_rect_in_camera"] == pytest.approx([0.5, 0.25, 0.5, 0.5])


# --- cheaper inspection loop ------------------------------------------------------

def test_contact_sheet_can_target_a_time_range(tmp_path):
    source = tmp_path / "clip.mp4"
    ffmpeg(["-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=2",
            "-c:v", "libx264", str(source)])
    result = Service(tmp_path).contact_sheet("clip.mp4", 3, start=1.0, end=2.0)
    assert all(1.0 <= f["time"] <= 2.0 for f in result["frames"])
    with pytest.raises(ValueError, match="end must be after start"):
        Service(tmp_path).contact_sheet("clip.mp4", 3, start=1.5, end=1.0)
    with pytest.raises(ValueError, match="start must be within"):
        Service(tmp_path).contact_sheet("clip.mp4", 3, start=9)


def test_preview_renders_selected_scenes_at_the_requested_width(tmp_path):
    service = Service(tmp_path)
    service.save("p.json", project(scenes=[{"id": "a", "duration": 1},
                                           {"id": "b", "duration": 1.5, "transition": "fade"}]).model_dump())
    with pytest.raises(ValueError, match="Unknown scene ids: zzz"):
        service.start("p.json", scenes=["zzz"])
    with pytest.raises(ValueError, match="width must be 160..3840"):
        service.start("p.json", width=0)
    job = service.start("p.json", scenes=["b"], width=320)
    assert job["scenes"] == ["b"]
    snapshot = json.loads((tmp_path / "jobs" / f"{job['job_id']}.json").read_text())
    assert [s["id"] for s in snapshot["scenes"]] == ["b"]
    assert snapshot["scenes"][0]["transition"] == "cut"
    result = finish(service, job["job_id"])["result"]
    assert abs(result["duration"] - 1.5) < 0.1
    assert result["width"] == 320


# --- reading vs caption text ------------------------------------------------------

def test_apply_readings_prefers_the_longer_term():
    readings = {"Agent": "エージェント", "GraphVisAgent": "グラフビズエージェント"}
    assert apply_readings("GraphVisAgent を使う", readings) == "グラフビズエージェント を使う"
    assert apply_readings("何もしない", {}) == "何もしない"
    assert apply_readings("何もしない", None) == "何もしない"


def test_readings_change_speech_but_not_captions(tmp_path, monkeypatch):
    from video_maker.voicevox import Voicevox
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(48000)
        f.writeframes(b"\0\0" * 24000)
    spoken = []

    def request(self, endpoint, params=None, body=None, method="GET"):
        if endpoint == "/version":
            return b'"test"'
        if endpoint == "/audio_query":
            spoken.append(params["text"])
            return b"{}"
        return buffer.getvalue()

    monkeypatch.setattr(Voicevox, "request", request)
    p = project(readings={"GraphVisAgent": "グラフビズエージェント"},
                scenes=[{"id": "s", "voice": {"text": "GraphVisAgentを紹介します。"}}])
    build = tmp_path / "build"
    build.mkdir()
    resolved = prepare(tmp_path, p, build)
    assert spoken == ["グラフビズエージェントを紹介します。"]
    assert resolved[0]["captions"][0]["text"] == "GraphVisAgentを紹介します。"
