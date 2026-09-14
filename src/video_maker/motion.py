"""Deterministic motion graphics from project data; never executes project code."""
import math
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps

from .graphics import wrap
from .models import Graphic
from .media import inside
from .web_render import render_html_to_image, render_mermaid_to_image, render_svg_to_image


def gradient_image(spec, size):
    """Build a small color ramp then resample; no full-resolution Python pixel loop."""
    colors = [ImageColor.getcolor(c, "RGBA") for c in spec.colors]
    side = 256
    ramp = Image.new("RGBA", (side, side))
    pixels = []
    for y in range(side):
        for x in range(side):
            p = {"horizontal": x, "vertical": y, "diagonal": (x+y)/2}[spec.direction] / (side-1)
            v = p * (len(colors)-1)
            index = min(len(colors)-2, int(v))
            f = v - index
            pixels.append(tuple(round(a+(b-a)*f) for a,b in zip(colors[index], colors[index+1])))
    ramp.putdata(pixels)
    return ramp.resize(size, Image.Resampling.BILINEAR)


def camera_filter(keys, fps, width, height):
    """Subpixel affine zoom, after speed/fps conversion, without integer crop jitter.

    zoompan truncates its crop size and aligns origins to chroma sample boundaries.
    Perspective samples fractional coordinates instead. Its `on` counter is one-based.
    Keep color planes full resolution until the final output conversion.
    """
    time = f"((on-1)/{fps})"
    def expression(attr):
        expr = str(getattr(keys[-1], attr))
        for a, b in reversed(list(zip(keys, keys[1:]))):
            p = f"clip(({time}-{a.time})/{b.time-a.time},0,1)"
            if a.easing == "hold":
                p = "0"
            elif a.easing == "ease_in_out":
                p = f"(({p})*({p})*(3-2*({p})))"
            elif a.easing == "ease_out":
                p = f"(1-pow(1-({p}),3))"
            val = f"({getattr(a,attr)}+({getattr(b,attr)-getattr(a,attr)})*({p}))"
            expr = f"if(lt({time},{b.time}),{val},{expr})"
        return expr
    zoom = f"({expression('zoom')})"
    left = f"max(0,min(W-W/{zoom},W*({expression('x')})-W/{zoom}/2))"
    top = f"max(0,min(H-H/{zoom},H*({expression('y')})-H/{zoom}/2))"
    right, bottom = f"({left})+W/{zoom}", f"({top})+H/{zoom}"
    return ("format=yuv444p,perspective="
            f"x0='{left}':y0='{top}':x1='{right}':y1='{top}':"
            f"x2='{left}':y2='{bottom}':x3='{right}':y3='{bottom}':"
            "sense=source:eval=frame:interpolation=cubic,")


def state_at(g: Graphic, time: float, duration: float):
    end = g.end if g.end is not None else duration
    if not g.start <= time < end:
        return None
    local = time - g.start
    x, y, scale, opacity = g.x, g.y, 1.0, g.opacity
    if g.keyframes:
        a = b = g.keyframes[0]
        for key in g.keyframes:
            if key.time <= local:
                a = b = key
            else:
                b = key
                break
        p = max(0, min(1, (local - a.time) / (b.time - a.time))) if b.time != a.time else 0
        if a.easing == "hold":
            p = 0
        elif a.easing == "ease_in_out":
            p = p * p * (3 - 2 * p)
        elif a.easing == "ease_out":
            p = 1 - (1 - p) ** 3
        x, y, scale, alpha = [getattr(a, key) + (getattr(b, key) - getattr(a, key)) * p
                              for key in ("x", "y", "scale", "opacity")]
        opacity *= alpha
    # Short graphics divide the available interval equally between entrance and exit.
    span = min(g.animation_seconds, (end - g.start) / 2)
    for effect, progress in ((g.enter, local / span), (g.exit, (end - time) / span)):
        p = max(0, min(1, progress))
        p = 1 - (1 - p) ** 3
        if effect != "none":
            opacity *= p
        if effect == "slide_left":
            x += 0.12 * (1 - p)
        elif effect == "slide_up":
            y += 0.10 * (1 - p)
        elif effect == "pop":
            scale *= 0.65 + 0.35 * p
    return x, y, scale, opacity


def artwork(g: Graphic, width: int, height: int, font: str, root: Path | None = None):
    """Rasterize each editable element once, with padding for outlines."""
    sw = round(g.stroke_width * height)
    pad = max(2, sw * 2)
    w, h = max(1, round(g.width * width)), max(1, round(g.height * height))
    ox = oy = 0
    if g.kind in ("arrow", "line"):
        dx, dy = (g.x2 - g.x) * width, (g.y2 - g.y) * height
        ox, oy = min(0, dx), min(0, dy)
        w, h = max(1, math.ceil(abs(dx))), max(1, math.ceil(abs(dy)))
        pad = max(pad, round(height * 0.025))
    im = Image.new("RGBA", (w + pad * 2, h + pad * 2))
    draw = ImageDraw.Draw(im)
    box = (pad, pad, pad + w - 1, pad + h - 1)
    if g.kind in ("image", "html", "mermaid", "svg"):
        if g.source and root is None:
            raise ValueError(f"{g.kind.capitalize()} graphics with source require a workspace")
        if g.kind == "html":
            src = inside(root, g.source) if g.source else g.html
            source = render_html_to_image(str(src), width=w, height=h, root=root)
        elif g.kind == "mermaid":
            src = inside(root, g.source) if g.source else g.mermaid
            source = render_mermaid_to_image(str(src), width=w, height=h, theme=g.theme, root=root)
        elif g.kind == "svg":
            src = inside(root, g.source) if g.source else g.svg
            source = render_svg_to_image(str(src), width=w, height=h, root=root)
        else:
            src_path = inside(root, g.source)
            if str(src_path).lower().endswith((".svg", ".svgz")):
                source = render_svg_to_image(str(src_path), width=w, height=h, root=root)
            else:
                with Image.open(src_path) as raw:
                    source = ImageOps.exif_transpose(raw).convert("RGBA")

        if g.fit == "cover":
            source = ImageOps.fit(source, (w, h), method=Image.Resampling.LANCZOS)
        else:
            source = ImageOps.contain(source, (w, h), method=Image.Resampling.LANCZOS)
        tile = Image.new("RGBA", (w, h))
        tile.alpha_composite(source, ((w - source.width) // 2, (h - source.height) // 2))
        mask = Image.new("L", (w, h))
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=min(g.radius * height, w / 2, h / 2), fill=255)
        tile.putalpha(ImageChops.multiply(tile.getchannel("A"), mask))
        im.alpha_composite(tile, (pad, pad))
    elif g.kind in ("rect", "ellipse"):
        if g.kind == "rect":
            draw.rounded_rectangle(box, radius=min(g.radius * height, w / 2, h / 2),
                                   fill=g.fill, outline=g.stroke, width=sw)
        else:
            draw.ellipse(box, fill=g.fill, outline=g.stroke, width=sw)
    elif g.kind in ("arrow", "line"):
        a, b = (pad - ox, pad - oy), (pad + dx - ox, pad + dy - oy)
        draw.line((a, b), fill=g.fill, width=max(1, sw))
        if g.kind == "arrow" and (dx or dy):
            angle = math.atan2(dy, dx)
            tip = max(sw * 3, height * 0.018)
            draw.polygon([b, (b[0] - tip * math.cos(angle - 0.5), b[1] - tip * math.sin(angle - 0.5)),
                          (b[0] - tip * math.cos(angle + 0.5), b[1] - tip * math.sin(angle + 0.5))], fill=g.fill)
    else:
        stroke = max(sw, round(height * 0.004)) if g.style == "impact" else sw
        stroke_fill = "#111827" if g.style == "impact" and g.stroke == "#00000000" else g.stroke
        margin = max(stroke + 2, round(height * 0.014))
        for size in range(max(1, round(g.font_size * height)), 0, -1):
            face = ImageFont.truetype(font, size)
            lines = wrap(g.text, face, max(1, w - 2 * margin))
            line_h = max(1, math.ceil(size * 1.4))
            if len(lines) * line_h <= h - 2 * margin and all(face.getlength(s) <= w - 2 * margin for s in lines):
                break
        else:
            raise ValueError("Text does not fit graphic box; enlarge it or shorten text")
        if g.style == "banner":
            draw.rounded_rectangle(box, radius=min(g.radius * height, w / 2, h / 2), fill=g.panel)
        top = pad + (h - len(lines) * line_h) / 2
        for i, line in enumerate(lines):
            line_w = face.getlength(line)
            left = {"left": margin, "center": (w - line_w) / 2, "right": w - margin - line_w}[g.align]
            draw.text((pad + left, top + i * line_h), line, font=face, anchor="lt",
                      fill=g.fill, stroke_width=stroke, stroke_fill=stroke_fill)
    if g.gradient:
        ramp = gradient_image(g.gradient, im.size)
        ramp.putalpha(ImageChops.multiply(ramp.getchannel("A"), im.getchannel("A")))
        im = ramp
    if g.shadow:
        sh = g.shadow
        blur = sh.blur * height
        dx, dy = round(sh.x * width), round(sh.y * height)
        extra = math.ceil(blur * 3 + max(abs(dx), abs(dy))) + 2
        expanded = Image.new("RGBA", (im.width + 2*extra, im.height + 2*extra))
        mask = Image.new("L", expanded.size)
        mask.paste(im.getchannel("A"), (extra + dx, extra + dy))
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
        color = ImageColor.getcolor(sh.color, "RGBA")
        shadow = Image.new("RGBA", expanded.size, color)
        shadow.putalpha(mask.point([round(i*color[3]/255) for i in range(256)]))
        expanded.alpha_composite(shadow)
        expanded.alpha_composite(im, (extra, extra))
        im = expanded
        ox -= extra
        oy -= extra
    return im, ox - pad, oy - pad


def frame_at(elements, time, duration, width, height):
    canvas = Image.new("RGBA", (width, height))
    for g, (original, ox, oy) in elements:
        state = state_at(g, time, duration)
        if state is None:
            continue
        x, y, scale, opacity = state
        if opacity <= 0:
            continue
        # Clip to the output before allocating a scaled tile, even for offscreen keyframes.
        left = round(x * width + ox - original.width * (scale - 1) / 2)
        top = round(y * height + oy - original.height * (scale - 1) / 2)
        right, bottom = left + original.width * scale, top + original.height * scale
        box = (max(0, left), max(0, top), min(width, math.ceil(right)), min(height, math.ceil(bottom)))
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        tile = original.transform((box[2] - box[0], box[3] - box[1]), Image.Transform.AFFINE,
                                  (1 / scale, 0, (box[0] - left) / scale,
                                   0, 1 / scale, (box[1] - top) / scale), Image.Resampling.BICUBIC)
        if opacity < 1:
            tile.putalpha(tile.getchannel("A").point([round(i * opacity) for i in range(256)]))
        canvas.alpha_composite(tile, (box[0], box[1]))
    return canvas


def render_graphics(graphics, width, height, fps, duration, font, output: Path, root: Path | None = None):
    elements = [(g, artwork(g, width, height, font, root)) for g in graphics]
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
            "-pixel_format", "rgba", "-video_size", f"{width}x{height}", "-framerate", str(fps),
            "-i", "pipe:0", "-an", "-c:v", "qtrle", "-pix_fmt", "argb", str(output)]
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
        try:
            for frame in range(round(duration * fps)):
                process.stdin.write(frame_at(elements, frame / fps, duration, width, height).tobytes())
            process.stdin.close()
            if process.wait(timeout=120):
                log.seek(0)
                raise RuntimeError(f"Graphics encoder failed: {log.read()[-6000:].decode(errors='replace')}")
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            process.stdin.close()
