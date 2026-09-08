import array
import math
import re
import sys
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font_path(custom: Path | None = None) -> str:
    candidates = [custom, Path("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"),
                  Path("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"),
                  Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
                  Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")]
    for p in candidates:
        if p and p.is_file():
            return str(p)
    raise ValueError("Japanese font not found. Set project.font to a TTF/OTF/TTC in workspace.")


def wrap(text, font, width):
    lines, current = [], ""
    for char in text:
        if char == "\n":
            lines.append(current)
            current = ""
        elif font.getlength(current + char) > width:
            lines.append(current)
            current = char
        else:
            current += char
    lines.append(current)
    return lines


def text_panel(text: str, width: int, height: int, font: str, output: Path, title=False):
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    size = max(16, int(height * (0.047 if title else 0.052)))
    max_height = height * (0.21 if title else 0.27)
    while True:
        face = ImageFont.truetype(font, size)
        lines = wrap(text, face, width * 0.84)
        line_height = int(size * 1.55)
        box_height = len(lines) * line_height + size
        if box_height <= max_height or size <= 12:
            break
        size -= 1
    if box_height > max_height:
        raise ValueError("Caption is too long; split it into multiple timed captions.")
    y = int(height * 0.045) if title else int(height * 0.95 - box_height)
    draw.rounded_rectangle((width * 0.055, y, width * 0.945, y + box_height),
                           radius=max(8, size // 2), fill=(10, 17, 32, 235))
    draw.rounded_rectangle((width * 0.055, y, width * 0.061, y + box_height),
                           radius=3, fill=(73, 215, 185, 255))
    for i, line in enumerate(lines):
        x = (width - face.getlength(line)) / 2
        draw.text((x, y + size * 0.4 + i * line_height), line, font=face,
                  fill="white", stroke_width=1, stroke_fill=(10, 17, 32, 255))
    canvas.save(output)


def character_panel(source: Path, width: int, height: int, fraction: float, side: str, output: Path):
    canvas = Image.new("RGBA", (width, height))
    with Image.open(source) as raw:
        im = raw.convert("RGBA")
        im.thumbnail((int(width * 0.42), int(height * fraction)), Image.Resampling.LANCZOS)
        x = width - im.width - int(width * 0.035) if side == "right" else int(width * 0.035)
        canvas.alpha_composite(im, (x, int(height * 0.88) - im.height))
    canvas.save(output)


def speech_windows(wav: Path, offset: float, step=0.08):
    with wave.open(str(wav)) as f:
        if f.getsampwidth() != 2:
            raise ValueError("Lip sync requires PCM 16-bit WAV")
        channels, rate = f.getnchannels(), f.getframerate()
        samples = array.array("h", f.readframes(f.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    chunk = max(1, int(rate * channels * step))
    energy = [math.sqrt(sum(v * v for v in samples[i:i + chunk]) / len(samples[i:i + chunk]))
              for i in range(0, len(samples), chunk)]
    threshold = max(220, max(energy, default=0) * 0.11)
    windows = []
    for i, value in enumerate(energy):
        if value <= threshold:
            continue
        start, end = offset + i * step, offset + (i + 1) * step
        if windows and abs(windows[-1][1] - start) < 0.001:
            windows[-1][1] = end
        else:
            windows.append([start, end])
    return windows


def subtitle_chunks(text: str, start: float, length: float):
    pieces = []
    for part in re.findall(r"[^。！？!?\n]+[。！？!?]?", text):
        pieces.extend(part[i:i + 44] for i in range(0, len(part), 44))
    total = sum(len(p) for p in pieces)
    cursor = start
    result = []
    for piece in pieces:
        end = cursor + length * len(piece) / max(1, total)
        result.append({"text": piece, "start": cursor, "end": end})
        cursor = end
    return result
