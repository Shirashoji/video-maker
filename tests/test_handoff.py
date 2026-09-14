"""Continuing an edit across AI clients and machines: revisions, notes and bundles."""
import json
import zipfile

import pytest
from PIL import Image

from video_maker.service import Service


def project(**kw):
    return {"name": "Handoff", "width": 320, "height": 240, **kw}


def test_stale_save_is_refused(tmp_path):
    service = Service(tmp_path)
    first = service.save("p.json", project(scenes=[{"id": "a", "duration": 1}]))
    opened = service.read("p.json")
    assert opened["revision"] == first["revision"]
    # Another client saves in between.
    other = service.save("p.json", project(scenes=[{"id": "a", "duration": 2}]), True,
                         opened["revision"])
    with pytest.raises(ValueError, match="Conflict"):
        service.save("p.json", project(scenes=[{"id": "a", "duration": 3}]), True,
                     opened["revision"])
    assert service.read("p.json")["project"]["scenes"][0]["duration"] == 2
    service.save("p.json", project(scenes=[{"id": "a", "duration": 3}]), True, other["revision"])
    assert len(list((tmp_path / "revisions" / "p").glob("*.json"))) == 2


def test_projects_summarize_notes_and_latest_render(tmp_path):
    service = Service(tmp_path)
    service.save("p.json", project(notes="残り: BGMの音量調整", scenes=[{"id": "a", "duration": 1}]))
    (tmp_path / "broken.json").write_text("{}")
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    (jobs / f"{'a' * 32}.status.json").write_text(json.dumps(
        {"id": "a" * 32, "status": "complete", "project": "p.json", "preview": True,
         "result": {"video": "renders/x/video.mp4"}}))
    summary = {p["path"]: p for p in service.projects()}
    assert summary["p.json"]["notes"] == "残り: BGMの音量調整"
    assert summary["p.json"]["latest_render"]["job_id"] == "a" * 32
    assert "error" in summary["broken.json"]


def test_bundle_round_trip_between_workspaces(tmp_path):
    source, target, outbox = tmp_path / "claude", tmp_path / "chatgpt", tmp_path / "outbox"
    outbox.mkdir()
    (source / "assets").mkdir(parents=True)
    Image.new("RGB", (320, 240), "#204060").save(source / "assets" / "still.png")
    Image.new("RGBA", (100, 200), (255, 0, 0, 255)).save(source / "assets" / "chara.png")
    first = Service(source)
    saved = first.save("p.json", project(notes="step-2 の字幕を確認中", scenes=[
        {"id": "a", "duration": 1, "source": "assets/still.png",
         "character": {"image": "assets/chara.png"},
         "graphics": [{"kind": "image", "source": "assets/still.png"}]}]))
    exported = first.export_project("p.json", str(outbox))
    assert exported["assets"] == 2
    bundle = exported["bundle"]

    second = Service(target)
    imported = second.import_project(bundle)
    assert imported["revision"] == saved["revision"]
    assert imported["notes"] == "step-2 の字幕を確認中"
    assert sorted(imported["assets_added"]) == ["assets/chara.png", "assets/still.png"]
    assert (target / "assets" / "still.png").read_bytes() == (source / "assets" / "still.png").read_bytes()

    with pytest.raises(ValueError, match="exists"):
        second.import_project(bundle)
    again = second.import_project(bundle, overwrite=True)
    assert again["assets_added"] == [] and again["assets_unchanged"] == 2

    Image.new("RGB", (320, 240), "#ffffff").save(target / "assets" / "still.png")
    with pytest.raises(ValueError, match="different files"):
        second.import_project(bundle, overwrite=True)


def test_bundle_cannot_escape_workspace(tmp_path):
    bundle = tmp_path / "evil.videomaker.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", json.dumps({
            "format": "video-maker-bundle", "version": 1, "project": "p.json",
            "assets": [{"path": "../escape.png", "sha256": "0", "bytes": 1}]}))
        archive.writestr("p.json", json.dumps(project(scenes=[{"id": "a", "duration": 1}])))
        archive.writestr("../escape.png", b"x")
    workspace = tmp_path / "ws"
    with pytest.raises(ValueError, match="inside workspace"):
        Service(workspace).import_project(str(bundle))
    assert not (tmp_path / "escape.png").exists()
