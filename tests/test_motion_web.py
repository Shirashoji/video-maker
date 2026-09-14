import pytest
from pathlib import Path
from PIL import Image

from video_maker.models import Graphic
from video_maker.motion import artwork, frame_at, render_graphics
from video_maker.graphics import font_path


SAMPLE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
  <rect x="20" y="20" width="160" height="160" rx="20" fill="#38BDF8" />
</svg>"""

SAMPLE_HTML = """<div style="background: rgba(30, 41, 59, 0.9); color: white; padding: 24px; border-radius: 16px;">
  <h2 style="font-size: 32px; margin: 0 0 8px 0;">HTML Card</h2>
  <p style="font-size: 18px; margin: 0; color: #94a3b8;">Rendered with headless chrome</p>
</div>"""

SAMPLE_MERMAID = """graph TD
  A[Node A] --> B[Node B]
"""


def test_motion_with_svg(tmp_path: Path):
    g = Graphic(
        kind="svg",
        svg=SAMPLE_SVG,
        x=0.1,
        y=0.1,
        width=0.4,
        height=0.4,
        enter="pop",
        exit="fade",
        animation_seconds=0.2,
    )
    font = font_path()
    w, h = 640, 360
    art = artwork(g, w, h, font, root=tmp_path)
    assert isinstance(art[0], Image.Image)

    elements = [(g, art)]
    # Check frame at t=0.1 (during enter pop)
    frame = frame_at(elements, 0.1, 2.0, w, h)
    assert isinstance(frame, Image.Image)
    assert frame.size == (w, h)
    assert frame.mode == "RGBA"

    # Test rendering to mov
    out_mov = tmp_path / "graphics.mov"
    render_graphics([g], w, h, fps=24, duration=0.5, font=font, output=out_mov, root=tmp_path)
    assert out_mov.is_file()
    assert out_mov.stat().st_size > 0


def test_motion_with_html(tmp_path: Path):
    g = Graphic(
        kind="html",
        html=SAMPLE_HTML,
        x=0.05,
        y=0.05,
        width=0.5,
        height=0.4,
        enter="fade",
    )
    font = font_path()
    w, h = 640, 360
    art = artwork(g, w, h, font, root=tmp_path)
    assert isinstance(art[0], Image.Image)

    elements = [(g, art)]
    frame = frame_at(elements, 0.2, 1.0, w, h)
    assert isinstance(frame, Image.Image)
    assert frame.size == (w, h)


def test_motion_with_mermaid(tmp_path: Path):
    g = Graphic(
        kind="mermaid",
        mermaid=SAMPLE_MERMAID,
        theme="dark",
        x=0.2,
        y=0.2,
        width=0.6,
        height=0.6,
        enter="slide_left",
    )
    font = font_path()
    w, h = 640, 360
    art = artwork(g, w, h, font, root=tmp_path)
    assert isinstance(art[0], Image.Image)

    elements = [(g, art)]
    frame = frame_at(elements, 0.3, 1.0, w, h)
    assert isinstance(frame, Image.Image)
    assert frame.size == (w, h)
