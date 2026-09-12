"""Fast-forward / slow-motion spans and single-frame inspection."""
import asyncio
import math
import os
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat
from pydantic import ValidationError

from video_maker.engine import (atempo_chain, render, retime_filter, retiming, source_span,
                                speed_segments, validate)
from video_maker.media import ffmpeg
from video_maker.models import Project, Scene
from video_maker.service import Service


def project(**kw):
    return Project(name="Test", width=320, height=240, fps=30, **kw)


def scene(**kw):
    return Scene(id="s", source="source.mp4", duration=2, **kw)


def source(tmp_path, seconds=12, audio=True):
    path = tmp_path / "source.mp4"
    args = ["-f", "lavfi", "-i", f"testsrc2=size=320x240:rate=30:duration={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    ffmpeg([*args, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)])
    return path


def test_ramps_split_the_source_into_ordered_spans():
    spans = speed_segments(scene(speed=2, speed_ramps=[{"start": 3, "end": 9, "speed": 4}]))
    assert spans == [(0.0, 3.0, 2.0), (3.0, 9.0, 4.0), (9.0, None, 2.0)]
    # A ramp starting at zero leaves no base-speed span in front of it.
    assert speed_segments(scene(speed_ramps=[{"start": 0, "end": 4, "speed": 0.5}])) == [
        (0.0, 4.0, 0.5), (4.0, None, 1.0)]


def test_atempo_stages_cover_the_whole_speed_range():
    # A single atempo only spans 0.5x..2x, so every rate has to be staged.
    for speed in [0.1, 0.25, 0.5, 1, 2, 6, 20]:
        rates = [float(stage.split("=")[1]) for stage in atempo_chain(speed)]
        assert math.prod(rates) == pytest.approx(speed)
        assert all(0.5 <= rate <= 2 for rate in rates)


def test_source_span_accounts_for_each_ramp():
    s = scene(speed_ramps=[{"start": 3, "end": 9, "speed": 4}])
    assert source_span(s, 2) == pytest.approx(2)           # still inside the 1x head
    assert source_span(s, 4.0) == pytest.approx(7.0)       # 3s at 1x, then 1s at 4x
    assert source_span(s, 6.0) == pytest.approx(10.5)      # past the ramp, back to 1x
    # Without ramps the plain multiple still holds.
    assert source_span(scene(speed=4), 3) == pytest.approx(12)


def test_retiming_reports_where_each_span_lands():
    spans = retiming(scene(speed_ramps=[{"start": 3, "end": 9, "speed": 4}]), 6.0)["spans"]
    assert [s["speed"] for s in spans] == [1.0, 4.0, 1.0]
    assert spans[1]["output_start"] == pytest.approx(3.0)
    assert spans[1]["output_end"] == pytest.approx(4.5)
    assert spans[2]["source_end"] == pytest.approx(10.5)


def test_constant_speed_keeps_its_simple_filter():
    assert retime_filter(scene(speed=2)) == "setpts=(PTS-STARTPTS)/2.0"
    assert "clip(" in retime_filter(scene(speed_ramps=[{"start": 1, "end": 2, "speed": 4}]))


def test_schema_rejects_overlapping_or_sourceless_ramps():
    for kw in [{"speed_ramps": [{"start": 3, "end": 9, "speed": 4},
                                {"start": 8, "end": 10, "speed": 1}]},
               {"speed_ramps": [{"start": 5, "end": 5, "speed": 2}]},
               {"speed_ramps": [{"start": 0, "end": 1, "speed": 25}]}]:
        with pytest.raises(ValidationError):
            scene(**kw)
    with pytest.raises(ValidationError):
        Scene(id="s", duration=2, speed_ramps=[{"start": 0, "end": 1, "speed": 2}])


def test_still_image_source_rejects_ramps(tmp_path):
    Image.new("RGB", (320, 240), "#334455").save(tmp_path / "still.png")
    p = project(scenes=[{"id": "s", "source": "still.png", "duration": 1,
                         "speed_ramps": [{"start": 0, "end": 1, "speed": 4}]}])
    (tmp_path / "p.json").write_text(p.model_dump_json())
    with pytest.raises(ValueError, match="video source"):
        render(tmp_path, "p.json")


def test_ramp_past_the_end_of_the_source_is_reported(tmp_path):
    source(tmp_path, seconds=2)
    p = project(scenes=[{"id": "s", "source": "source.mp4", "duration": 1,
                         "speed_ramps": [{"start": 1, "end": 9, "speed": 4}]}])
    assert validate(tmp_path, p)["warnings"]
    bad = project(scenes=[{"id": "s", "source": "source.mp4", "duration": 1,
                           "speed_ramps": [{"start": 5, "end": 9, "speed": 4}]}])
    with pytest.raises(ValueError, match="past the"):
        validate(tmp_path, bad)


def closest_source_time(rendered, original, output_time, candidates):
    """Which source moment the rendered frame actually shows."""
    def grab(path, at, name):
        out = rendered.parent / name
        ffmpeg(["-ss", str(at), "-i", str(path), "-frames:v", "1", str(out)])
        return Image.open(out).convert("L")

    frame = grab(rendered, output_time, "a.png")
    scores = {c: ImageStat.Stat(ImageChops.difference(frame, grab(original, c, "b.png"))).mean[0]
              for c in candidates}
    return min(scores, key=scores.get)


def test_fast_forward_and_slow_motion_land_on_the_right_source_frames(tmp_path):
    original = source(tmp_path, seconds=12, audio=False)
    p = project(scenes=[{"id": "s", "source": "source.mp4", "duration": 6,
                         "speed_ramps": [{"start": 3, "end": 9, "speed": 4}]}])
    (tmp_path / "p.json").write_text(p.model_dump_json())
    result = render(tmp_path, "p.json")
    assert result["duration"] == pytest.approx(6, abs=0.1)
    video = Path(result["video"])
    # Before the ramp the scene runs at 1x; inside it, four source seconds per second.
    assert closest_source_time(video, original, 1.0, [0.5, 1.0, 2.0, 4.0]) == 1.0
    assert closest_source_time(video, original, 4.0, [3.5, 5.0, 7.0, 9.0]) == 7.0
    assert closest_source_time(video, original, 5.0, [7.0, 9.5, 10.5, 11.5]) == 9.5


def test_slow_motion_stretches_source_audio(tmp_path):
    source(tmp_path, seconds=4)
    p = project(scenes=[{"id": "s", "source": "source.mp4", "duration": 3, "source_volume": 1,
                         "speed_ramps": [{"start": 0, "end": 1, "speed": 0.5}]}])
    (tmp_path / "p.json").write_text(p.model_dump_json())
    result = render(tmp_path, "p.json")
    assert result["duration"] == pytest.approx(3, abs=0.1)
    # 1s of source stretched to 2s, then 1s at normal rate: 2s of source in a 3s scene.
    assert source_span(p.scenes[0], 3) == pytest.approx(2.0)


def test_extract_frame_keeps_detail_and_stays_in_the_workspace(tmp_path):
    source(tmp_path, seconds=4, audio=False)
    service = Service(tmp_path)
    result = service.frame("source.mp4", 1.5)
    assert result["time"] == 1.5 and result["size"] == [320, 240]  # never upscaled
    assert Path(result["image"]).is_file()
    assert not result["relative_path"].startswith("/")
    small = service.frame("source.mp4", 1.5, width=160)
    assert small["size"] == [160, 120]
    # The end of a file has no frame exactly on it; land on the last one instead.
    last = service.frame("source.mp4", 4.0)
    assert last["requested_time"] == 4.0 and last["time"] == pytest.approx(4 - 1/30, abs=0.01)
    for bad in [(-1, 1280), (99, 1280), (1.5, 10)]:
        with pytest.raises(ValueError):
            service.frame("source.mp4", bad[0], bad[1])


def test_extract_frame_needs_a_video_stream(tmp_path):
    ffmpeg(["-f", "lavfi", "-i", "sine=duration=2", "-c:a", "pcm_s16le", str(tmp_path / "a.wav")])
    with pytest.raises(ValueError, match="no video stream"):
        Service(tmp_path).frame("a.wav", 1.0)


def test_extract_frame_over_mcp_returns_image_and_metadata(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    source(tmp_path, seconds=3, audio=False)

    async def check():
        params = StdioServerParameters(command=sys.executable,
                                       args=["-m", "video_maker.server", "--workspace", str(tmp_path)],
                                       env={**os.environ, "PYTHONPATH": str(Path("src").resolve())})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                names = {t.name for t in (await client.list_tools()).tools}
                assert "extract_frame" in names
                result = await client.call_tool("extract_frame", {"path": "source.mp4", "time": 1.0})
                assert not result.isError
                kinds = [c.type for c in result.content]
                assert "image" in kinds and "text" in kinds
                bad = await client.call_tool("extract_frame", {"path": "source.mp4", "time": 99})
                assert bad.isError
    asyncio.run(check())
