"""Rendering utilities for HTML, Mermaid, and SVG graphics."""
import io
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from PIL import Image

try:
    import resvg_py
    HAS_RESVG = True
except ImportError:  # pragma: no cover
    resvg_py = None
    HAS_RESVG = False


def find_chrome_executable() -> str | None:
    """Detect Google Chrome, Chromium, or Edge for headless HTML rendering."""
    custom = os.environ.get("CHROME_PATH")
    if custom and Path(custom).is_file():
        return custom

    # Common macOS installation paths
    mac_candidates = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path(os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    ]
    for candidate in mac_candidates:
        if candidate.is_file():
            return str(candidate)

    # Linux / PATH candidates
    for name in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]:
        found = shutil.which(name)
        if found:
            return found

    return None


def find_mmdc_executable() -> str | None:
    """Detect Mermaid CLI (mmdc) binary."""
    custom = os.environ.get("MMDC_PATH")
    if custom and Path(custom).is_file():
        return custom

    found = shutil.which("mmdc")
    if found:
        return found

    # Fallback to homebrew path if not in current PATH
    homebrew_mmdc = Path("/opt/homebrew/bin/mmdc")
    if homebrew_mmdc.is_file():
        return str(homebrew_mmdc)

    return None


def render_html_to_image(
    html_or_path: str,
    width: int = 1920,
    height: int = 1080,
    root: Path | None = None,
    chrome_path: str | None = None,
) -> Image.Image:
    """Render HTML markup or file to a transparent RGBA PIL Image."""
    chrome = chrome_path or find_chrome_executable()
    if not chrome:
        raise RuntimeError(
            "Google Chrome or Chromium is required for HTML rendering. "
            "Please install Chrome or set CHROME_PATH."
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        target_file: Path

        # Check if html_or_path is an existing file
        direct_path = Path(html_or_path)
        if root and not direct_path.is_absolute():
            resolved = root / direct_path
            if resolved.is_file():
                direct_path = resolved

        if direct_path.is_file():
            target_file = direct_path
        else:
            # It's an HTML string
            target_file = tmppath / "slide.html"
            content = html_or_path
            # Wrap simple fragments with HTML boilerplate if needed
            if "<html" not in content.lower():
                content = (
                    "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                    "<style>body { margin: 0; background: transparent; overflow: hidden; "
                    "font-family: -apple-system, BlinkMacSystemFont, 'Hiragino Sans', 'Noto Sans CJK JP', sans-serif; }"
                    "</style></head><body>"
                    f"{content}"
                    "</body></html>"
                )
            target_file.write_text(content, encoding="utf-8")

        out_png = tmppath / "render.png"
        cmd = [
            chrome,
            "--headless",
            "--disable-gpu",
            f"--screenshot={out_png}",
            f"--window-size={width},{height}",
            "--default-background-color=00000000",
            f"file://{target_file.resolve()}",
        ]
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
        if proc.returncode != 0 or not out_png.exists():
            err_msg = proc.stderr.decode(errors="replace")[-2000:]
            raise RuntimeError(f"HTML rendering failed (exit code {proc.returncode}): {err_msg}")

        with Image.open(out_png) as im:
            return im.convert("RGBA")


def render_mermaid_to_image(
    mermaid_or_path: str,
    width: int | None = None,
    height: int | None = None,
    theme: str = "dark",
    root: Path | None = None,
    mmdc_path: str | None = None,
) -> Image.Image:
    """Render Mermaid definition or file to a transparent RGBA PIL Image."""
    mmdc = mmdc_path or find_mmdc_executable()
    if not mmdc:
        raise RuntimeError(
            "Mermaid CLI (mmdc) is required for Mermaid diagram rendering. "
            "Please install it with: npm install -g @mermaid-js/mermaid-cli"
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        input_mmd: Path

        direct_path = Path(mermaid_or_path)
        if root and not direct_path.is_absolute():
            resolved = root / direct_path
            if resolved.is_file():
                direct_path = resolved

        if direct_path.is_file():
            input_mmd = direct_path
        else:
            input_mmd = tmppath / "diagram.mmd"
            input_mmd.write_text(mermaid_or_path, encoding="utf-8")

        out_png = tmppath / "diagram.png"
        cmd = [
            mmdc,
            "-i", str(input_mmd.resolve()),
            "-o", str(out_png.resolve()),
            "-t", theme,
            "-b", "transparent",
        ]

        # Pass Chrome executable to Puppeteer if Chrome exists to avoid missing bundled browser
        chrome = find_chrome_executable()
        cfg_file = None
        if chrome:
            cfg_file = tmppath / "puppeteer-config.json"
            cfg_file.write_text(json.dumps({"executablePath": chrome}), encoding="utf-8")
            cmd.extend(["--puppeteerConfigFile", str(cfg_file.resolve())])

        if width:
            cmd.extend(["-w", str(width)])
        if height:
            cmd.extend(["-H", str(height)])

        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if proc.returncode != 0 or not out_png.exists():
            err_msg = proc.stderr.decode(errors="replace")[-2000:]
            raise RuntimeError(f"Mermaid rendering failed (exit code {proc.returncode}): {err_msg}")

        with Image.open(out_png) as im:
            return im.convert("RGBA")


def render_svg_to_image(
    svg_or_path: str,
    width: int | None = None,
    height: int | None = None,
    root: Path | None = None,
) -> Image.Image:
    """Render SVG XML string or file to a transparent RGBA PIL Image using resvg-py."""
    if not HAS_RESVG:
        raise RuntimeError("resvg-py is required for SVG rendering. Install with: uv add resvg-py")

    direct_path = Path(svg_or_path)
    if root and not direct_path.is_absolute():
        resolved = root / direct_path
        if resolved.is_file():
            direct_path = resolved

    if direct_path.is_file():
        png_bytes = resvg_py.svg_to_bytes(
            svg_path=str(direct_path.resolve()),
            width=width,
            height=height,
        )
    else:
        png_bytes = resvg_py.svg_to_bytes(
            svg_string=svg_or_path,
            width=width,
            height=height,
        )

    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
