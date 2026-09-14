import pytest
from pathlib import Path
from PIL import Image

from video_maker.models import Graphic, Project
from video_maker.web_render import (
    find_chrome_executable,
    find_mmdc_executable,
    render_html_to_image,
    render_mermaid_to_image,
    render_svg_to_image,
    HAS_RESVG,
)
from video_maker.media import doctor
from video_maker.service import Service
from video_maker.templates import slide_template, mermaid_template


SAMPLE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <circle cx="50" cy="50" r="40" fill="#38BDF8" />
</svg>"""

SAMPLE_HTML = """<div style="background: rgba(15,23,42,0.8); color: white; padding: 20px; border-radius: 12px;">
  <h1>Hello Test</h1>
</div>"""

SAMPLE_MERMAID = """graph LR
    A[Start] --> B[End]
"""


def test_doctor_includes_web_tools():
    info = doctor()
    assert "ffmpeg" in info
    assert "chrome" in info
    assert "mmdc" in info
    assert "resvg" in info
    assert info["resvg"] is True


def test_graphic_model_web_support():
    # Valid html graphic
    g_html = Graphic(kind="html", html=SAMPLE_HTML, x=0, y=0, width=1, height=1)
    assert g_html.kind == "html"
    assert g_html.html == SAMPLE_HTML

    # Valid mermaid graphic
    g_mmd = Graphic(kind="mermaid", mermaid=SAMPLE_MERMAID, theme="dark")
    assert g_mmd.kind == "mermaid"
    assert g_mmd.theme == "dark"

    # Valid svg graphic
    g_svg = Graphic(kind="svg", svg=SAMPLE_SVG)
    assert g_svg.kind == "svg"

    # Missing source and code
    with pytest.raises(Exception):
        Graphic(kind="html")
    with pytest.raises(Exception):
        Graphic(kind="mermaid")
    with pytest.raises(Exception):
        Graphic(kind="svg")

    # Disallowed source on text
    with pytest.raises(Exception):
        Graphic(kind="text", text="hi", source="something.png")


def test_render_svg():
    if not HAS_RESVG:
        pytest.skip("resvg-py not installed")
    im = render_svg_to_image(SAMPLE_SVG, width=200, height=200)
    assert isinstance(im, Image.Image)
    assert im.size == (200, 200)
    assert im.mode == "RGBA"


def test_render_html():
    chrome = find_chrome_executable()
    if not chrome:
        pytest.skip("Chrome / Chromium not available")
    im = render_html_to_image(SAMPLE_HTML, width=640, height=360)
    assert isinstance(im, Image.Image)
    assert im.size == (640, 360)
    assert im.mode == "RGBA"


def test_render_mermaid():
    mmdc = find_mmdc_executable()
    if not mmdc:
        pytest.skip("mmdc not available")
    im = render_mermaid_to_image(SAMPLE_MERMAID, theme="dark")
    assert isinstance(im, Image.Image)
    assert im.mode == "RGBA"
    assert im.width > 0 and im.height > 0


def test_service_render_asset_and_templates(tmp_path: Path):
    service = Service(tmp_path)

    # Test templates
    tmpl_html = service.asset_template(kind="html", variant="hero")
    assert "KEY POINT" in tmpl_html["content"]

    tmpl_mmd = service.asset_template(kind="mermaid", variant="architecture")
    assert "graph LR" in tmpl_mmd["content"]

    # Test render_asset with SVG
    res = service.render_asset(SAMPLE_SVG, width=150, height=150)
    assert Path(res["image"]).is_file()
    assert res["width"] == 150
    assert res["height"] == 150

    # Test render_asset with file
    svg_file = tmp_path / "test.svg"
    svg_file.write_text(SAMPLE_SVG, encoding="utf-8")
    res_file = service.render_asset(str(svg_file), output="rendered_test.png", width=300, height=300)
    assert Path(res_file["image"]).is_file()
    assert res_file["width"] == 300
