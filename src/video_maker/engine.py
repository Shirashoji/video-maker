import json
import math
import shutil
import uuid
import wave
from pathlib import Path

from .graphics import character_panel, font_path, speech_windows, subtitle_chunks, text_panel
from .media import duration, ffmpeg, inside, probe
from .models import Project
from .motion import camera_filter, gradient_image, render_graphics
from .voicevox import Voicevox


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def apply_readings(text: str, readings: dict | None) -> str:
    """Replace terms for synthesis only; captions and SRT keep the original spelling.

    Longer terms are substituted first so a short entry cannot consume part of a
    longer one.
    """
    for term in sorted(readings or {}, key=len, reverse=True):
        text = text.replace(term, readings[term])
    return text


def resolve_time(value, length: float, default=None):
    """Turn a scene-relative time into seconds from the scene start."""
    if value is None:
        return default
    if isinstance(value, str):
        offset = value[len("scene_end"):]
        return length - float(offset[1:]) if offset else length
    return float(value)


def resolved_graphics(scene, length: float) -> list:
    """Graphics with scene-relative start/end replaced by seconds."""
    return [g.model_copy(update={"start": resolve_time(g.start, length),
                                 "end": resolve_time(g.end, length, length)})
            for g in scene.graphics]


# Source seconds elapsed at the frame setpts is looking at, written defensively so a
# non-zero container start time cannot shift the retiming.
SOURCE_SECONDS = "(PTS-STARTPTS)*TB"


def speed_segments(scene) -> list[tuple[float, float | None, float]]:
    """(start, end, speed) spans in source seconds from source_in, covering the source.

    scene.speed plays everywhere a ramp does not; the final span is open-ended because
    how much source a scene consumes is only known once its duration is resolved.
    """
    segments, cursor = [], 0.0
    for ramp in scene.speed_ramps:
        if ramp.start > cursor:
            segments.append((cursor, ramp.start, scene.speed))
        segments.append((ramp.start, ramp.end, ramp.speed))
        cursor = ramp.end
    segments.append((cursor, None, scene.speed))
    return segments


def retime_filter(scene) -> str:
    """setpts mapping source seconds to output seconds across the scene's speed spans.

    The map is a sum of clamped ramps rather than nested conditionals: each frame is
    remapped on its own, so FFmpeg keeps streaming instead of buffering the whole
    source the way a split/trim/concat graph would.
    """
    if not scene.speed_ramps:
        return f"setpts=(PTS-STARTPTS)/{scene.speed}"
    terms = []
    for start, end, speed in speed_segments(scene):
        # An open-ended final span still needs a finite clamp; no source runs this long.
        span = 1e7 if end is None else end - start
        terms.append(f"{1/speed:.12g}*clip({SOURCE_SECONDS}-{start:.6f},0,{span:.6f})")
    # Quoted: the clamp terms contain commas, which otherwise end the filter argument.
    return f"setpts='({'+'.join(terms)})/TB'"


def atempo_chain(speed: float) -> list[str]:
    """atempo stages for one playback rate; a single stage only spans 0.5x..2x."""
    stages, remaining = [], speed
    while remaining < 0.5:
        stages.append("atempo=0.5")
        remaining /= 0.5
    while remaining > 2:
        stages.append("atempo=2")
        remaining /= 2
    stages.append(f"atempo={remaining}")
    return stages


def source_span(scene, length: float) -> float:
    """Source seconds a scene of this output length consumes, speed ramps included."""
    remaining = length
    for start, end, speed in speed_segments(scene):
        if end is None:
            return start + remaining * speed
        output_length = (end - start) / speed
        if output_length >= remaining:
            return start + remaining * speed
        remaining -= output_length
    raise AssertionError("speed_segments always ends open-ended")


def retiming(scene, length: float) -> dict:
    """Where each speed span lands in the finished scene, so telops can be timed to it."""
    spans, cursor, consumed = [], 0.0, source_span(scene, length)
    for start, end, speed in speed_segments(scene):
        if start >= consumed:
            break
        stop = consumed if end is None else min(end, consumed)
        spans.append({"source_start": start, "source_end": stop, "speed": speed,
                      "output_start": cursor, "output_end": cursor + (stop - start) / speed})
        cursor += (stop - start) / speed
    return {"source_in": scene.source_in, "source_consumed": consumed, "spans": spans,
            "note": ("source_start/source_end are seconds after source_in; output_start/"
                     "output_end are scene seconds. Captions, graphics and camera use "
                     "output seconds.")}


def retime_audio(source: Path, scene, length: float, output: Path) -> Path:
    """Render the scene's source audio once per speed span, then join the spans.

    One short pass per span keeps memory flat; an asplit/atrim/concat graph would have
    to hold the whole track in memory while its first branch drains.
    """
    consumed = source_span(scene, length)
    parts = []
    for index, (start, end, speed) in enumerate(speed_segments(scene)):
        if start >= consumed:
            break
        stop = consumed if end is None else min(end, consumed)
        part = output.with_name(f"{output.stem}-{index}.wav")
        ffmpeg(["-ss", str(scene.source_in + start), "-t", str(stop - start), "-i", str(source),
                "-vn", "-af", ",".join(atempo_chain(speed)), "-ar", "48000", "-ac", "1",
                "-c:a", "pcm_s16le", str(part)])
        parts.append(part)
    with wave.open(str(output), "wb") as combined:
        combined.setnchannels(1)
        combined.setsampwidth(2)
        combined.setframerate(48000)
        for part in parts:
            with wave.open(str(part)) as span:
                combined.writeframes(span.readframes(span.getnframes()))
    return output


def synthesize_narration(root: Path, voice, output: Path, readings: dict | None = None):
    """Synthesize one caption-sized phrase at a time and concatenate them.

    Caption boundaries follow measured WAV lengths. prepare() and the synthesize_voice
    tool share this, so auditioned timings match what the render produces.
    """
    elapsed, chunks = 0.0, []
    with wave.open(str(output), "wb") as combined:
        combined.setnchannels(1)
        combined.setsampwidth(2)
        combined.setframerate(48000)
        for part in subtitle_chunks(voice.text, 0, 1):
            spoken = apply_readings(part["text"], readings)
            fragment = Voicevox().synthesize(voice.model_copy(update={"text": spoken}),
                                             root / ".cache" / "voicevox")
            with wave.open(str(fragment)) as source:
                if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 48000):
                    raise ValueError("VOICEVOX must return mono 16-bit 48 kHz WAV")
                part_length = source.getnframes() / source.getframerate()
                combined.writeframes(source.readframes(source.getnframes()))
            chunks.append({"text": part["text"], "spoken": spoken,
                           "start": elapsed, "end": elapsed + part_length})
            elapsed += part_length
    return output, elapsed, chunks


def scene_duration_for(audio_length: float, fps: int, transition_seconds: float) -> float:
    """Scene length prepare() would choose for narration of this length."""
    overlap = round(transition_seconds * fps) / fps
    return math.ceil((overlap + 0.1 + audio_length + overlap + 0.1) * fps) / fps


def scene_layout(root: Path, project: Project, scene) -> dict | None:
    """Where the recording actually lands, so camera coordinates need no mental math.

    graphics use output-canvas fractions; camera x,y are fractions of the recording's
    display area (the source_rect box, letterbox bars included). content_rect_in_camera
    is that display area minus the bars, i.e. where the picture itself is in camera space.
    """
    if not scene.source:
        return None
    w, h = project.width, project.height
    meta = probe(inside(root, scene.source))
    stream = next((s for s in meta["streams"] if s["codec_type"] == "video"), None)
    if not stream:
        return None
    sw, sh = float(stream["width"]), float(stream["height"])
    if scene.crop:
        sw, sh = sw * scene.crop[2], sh * scene.crop[3]
    rx, ry, rw, rh = scene.source_rect or (0, 0, 1, 1)
    vw, vh = max(2, int(w * rw) // 2 * 2), max(2, int(h * rh) // 2 * 2)
    fit = min(vw / sw, vh / sh)
    cw, ch = sw * fit, sh * fit
    ox, oy = (vw - cw) / 2, (vh - ch) / 2
    return {
        "source_size": [float(stream["width"]), float(stream["height"])],
        "cropped_size": [sw, sh],
        "display_rect": [rx, ry, vw / w, vh / h],
        "content_rect": [rx + ox / w, ry + oy / h, cw / w, ch / h],
        "content_rect_in_camera": [ox / vw, oy / vh, cw / vw, ch / vh],
        "note": ("graphics x,y are output-canvas fractions; camera x,y are fractions of "
                 "display_rect. camera_x = (output_x - display_rect[0]) / display_rect[2]."),
    }


def camera_focus(keys) -> list[dict]:
    """Effective focus after edge clamping, so a requested x,y is not guesswork."""
    result = []
    for key in keys:
        span = 1 / key.zoom
        left = max(0.0, min(1 - span, key.x - span / 2))
        top = max(0.0, min(1 - span, key.y - span / 2))
        result.append({"time": key.time, "zoom": key.zoom, "x": key.x, "y": key.y,
                       "easing": key.easing,
                       "effective_x": left + span / 2, "effective_y": top + span / 2,
                       "visible_rect_in_camera": [left, top, span, span]})
    return result


def load(root: Path, project: str) -> Project:
    return Project.model_validate_json(inside(root, project).read_text())


def validate(root: Path, project: Project) -> dict:
    warnings = []
    for scene in project.scenes:
        for value in [scene.source, scene.audio,
                      scene.character.image if scene.character else None,
                      scene.character.mouth_open if scene.character else None]:
            if value:
                inside(root, value)
        for graphic in scene.graphics:
            if graphic.source:
                path = inside(root, graphic.source)
                if path.suffix.lower() not in IMAGE_EXT:
                    raise ValueError(f"{scene.id}: image graphic requires a supported still image")
        for effect in scene.sound_effects:
            meta = probe(inside(root, effect.source))
            if not any(s["codec_type"] == "audio" for s in meta["streams"]):
                raise ValueError(f"{scene.id}: sound effect requires audio")
            if effect.source_in + effect.duration > float(meta["format"]["duration"]) + 0.02:
                raise ValueError(f"{scene.id}: sound effect exceeds source duration")
        if scene.source and Path(scene.source).suffix.lower() not in IMAGE_EXT:
            meta = probe(inside(root, scene.source))
            if not any(s["codec_type"] == "video" for s in meta["streams"]):
                raise ValueError(f"{scene.id}: source must contain video")
            length = float(meta["format"]["duration"])
            if scene.source_in >= length:
                raise ValueError(f"{scene.id}: source_in exceeds source duration")
            available = length - scene.source_in
            for ramp in scene.speed_ramps:
                if ramp.start >= available:
                    raise ValueError(f"{scene.id}: speed ramp starts {ramp.start}s after source_in, "
                                     f"past the {available:.2f}s of source that remains")
                if ramp.end > available:
                    warnings.append(f"{scene.id}: speed ramp ends past the source; the last frame "
                                    "holds there instead of playing at that speed.")
        elif scene.speed_ramps:
            raise ValueError(f"{scene.id}: speed_ramps needs a video source; a still has no motion to re-time")
        if scene.voice and not project.credits:
            warnings.append("Add the selected VOICEVOX character credit to project.credits before publishing.")
    if project.music:
        inside(root, project.music.source)
    font_path(inside(root, project.font) if project.font else None)
    return {"valid": True, "scenes": len(project.scenes), "warnings": sorted(set(warnings))}


def plan(root: Path, project: Project, build: Path, strict: bool = True):
    """Resolve actual audio durations before choosing frame-exact scene lengths.

    With strict=False problems are collected instead of raised, so a dry run can
    report every issue at once together with the durations graphics must fit inside.
    """
    validate(root, project)
    resolved, issues, cursor = [], [], 0.0
    fps = project.fps
    overlap = round(project.transition_seconds * fps) / fps
    for index, scene in enumerate(project.scenes):
        problems = []

        def fail(message):
            if strict:
                raise ValueError(message)
            problems.append(message)

        audio = None
        voice_captions = []
        if scene.voice:
            audio = build / f"{scene.id}-speech.wav"
            _, _, voice_captions = synthesize_narration(root, scene.voice, audio, project.readings)
        elif scene.audio:
            audio = inside(root, scene.audio)
        head = overlap + 0.1
        audio_length = 0.0
        if audio:
            converted = build / f"{scene.id}-narration.wav"
            ffmpeg(["-i", str(audio), "-vn", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(converted)])
            audio = converted
            audio_length = duration(audio)
        required = head + audio_length + overlap + 0.1 if audio else 0.5
        length = math.ceil((scene.duration if scene.duration is not None else required) * fps) / fps
        if length + 1e-6 < required:
            fail(f"{scene.id}: duration {length:.2f}s is too short; narration needs {required:.2f}s")
        if scene.transition != "cut" and min(length, resolved[-1]["duration"]) <= 2 * overlap:
            fail(f"{scene.id}: scenes must be longer than twice the transition duration")
        if scene.transition != "cut":
            cursor -= overlap
        captions = []
        for caption in scene.captions:
            entry = caption.model_dump()
            entry["start"] = resolve_time(caption.start, length)
            entry["end"] = resolve_time(caption.end, length)
            if entry["end"] <= entry["start"]:
                fail(f"{scene.id}: caption end must be after start")
            captions.append(entry)
        if not captions and audio:
            if scene.voice:
                captions = [{"text": c["text"], "start": c["start"] + head, "end": c["end"] + head}
                            for c in voice_captions]
            elif scene.audio_text:
                captions = subtitle_chunks(scene.audio_text, head, audio_length)
        for caption in captions:
            if caption["end"] > length:
                fail(f"{scene.id}: caption extends past scene end")
        graphics = []
        for position, graphic in enumerate(resolved_graphics(scene, length)):
            if graphic.end <= graphic.start:
                fail(f"{scene.id}: graphic end must be after start")
            elif graphic.start >= length or graphic.end > length or (graphic.keyframes and
                    graphic.keyframes[-1].time > graphic.end - graphic.start):
                fail(f"{scene.id}: graphic or keyframe extends past scene end")
            graphics.append({"index": position, "kind": graphic.kind,
                             "start": graphic.start, "end": graphic.end})
        # A still has no timeline to re-time, so speed never applies to one.
        retimed_source = (bool(scene.source) and Path(scene.source).suffix.lower() not in IMAGE_EXT
                          and (scene.speed != 1 or bool(scene.speed_ramps)))
        if scene.camera and scene.camera[-1].time > length:
            fail(f"{scene.id}: camera extends past scene end")
        for effect in scene.sound_effects:
            if effect.start + effect.duration > length + 1e-6:
                fail(f"{scene.id}: sound effect extends past scene end")
        if scene.caption_mode == "off":
            captions = []
        resolved.append({"id": scene.id, "start": cursor, "duration": length,
                         "audio": str(audio) if audio else None, "audio_start": head,
                         "audio_duration": audio_length, "captions": captions,
                         "required_duration": required, "graphics": graphics,
                         "camera": camera_focus(scene.camera),
                         "retiming": retiming(scene, length) if retimed_source else None,
                         "layout": scene_layout(root, project, scene), "issues": problems})
        issues.extend(problems)
        cursor += length
    return resolved, issues


def prepare(root: Path, project: Project, build: Path) -> list[dict]:
    """Resolve actual audio durations before choosing frame-exact scene lengths."""
    return plan(root, project, build, strict=True)[0]


def render_scene(root, project, scene, info, build, font):
    w, h, fps, length = project.width, project.height, project.fps, info["duration"]
    args, filters = [], []
    backdrop = None
    if scene.background_gradient:
        backdrop = build / f"{scene.id}-background.png"
        gradient_image(scene.background_gradient, (w, h)).save(backdrop)
    if scene.source:
        source = inside(root, scene.source)
        if source.suffix.lower() in IMAGE_EXT:
            args += ["-loop", "1", "-framerate", str(fps), "-i", str(source)]
        else:
            args += ["-ss", str(scene.source_in), "-i", str(source)]
    elif backdrop:
        args += ["-loop", "1", "-framerate", str(fps), "-i", str(backdrop)]
    else:
        args += ["-f", "lavfi", "-i", f"color=c={scene.background}:s={w}x{h}:r={fps}:d={length}"]
    base = f"[0:v]{retime_filter(scene)},"
    if scene.crop:
        x, y, cw, ch = scene.crop
        base += f"crop=iw*{cw}:ih*{ch}:iw*{x}:ih*{y},"
    rx, ry, rw, rh = scene.source_rect or (0, 0, 1, 1)
    vw, vh = max(2, int(w * rw) // 2 * 2), max(2, int(h * rh) // 2 * 2)
    base += (f"scale={vw}:{vh}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
             f"pad={vw}:{vh}:(ow-iw)/2:(oh-ih)/2:color={scene.background},"
             f"fps={fps},tpad=stop_mode=clone:stop_duration={length},trim=duration={length},"
             "setsar=1,")
    if scene.camera:
        base += camera_filter(scene.camera, fps, vw, vh)
    idx, current, count = 1, "v0", 0
    if backdrop and scene.source:
        args += ["-loop", "1", "-framerate", str(fps), "-i", str(backdrop)]
        filters.append(base + "settb=AVTB,format=yuv420p[footage]")
        filters.append(f"[1:v][footage]overlay={int(rx*w)//2*2}:{int(ry*h)//2*2}:shortest=1[v0]")
        idx += 1
    else:
        filters.append(base + f"pad={w}:{h}:{int(rx*w)//2*2}:{int(ry*h)//2*2}:color={scene.background},"
                       "settb=AVTB,format=yuv420p[v0]")

    def overlay(path, enable=None):
        nonlocal idx, current, count
        args.extend(["-loop", "1", "-framerate", str(fps), "-i", str(path)])
        count += 1
        target = f"v{count}"
        expr = f":enable='{enable}'" if enable else ""
        filters.append(f"[{current}][{idx}:v]overlay=0:0:shortest=1{expr}[{target}]")
        idx += 1
        current = target

    if scene.graphics:
        motion = build / f"{scene.id}-graphics.mov"
        render_graphics(resolved_graphics(scene, length), w, h, fps, length, font, motion, root)
        args.extend(["-i", str(motion)])
        count += 1
        target = f"v{count}"
        filters.append(f"[{current}][{idx}:v]overlay=0:0:shortest=1[{target}]")
        idx += 1
        current = target

    if scene.character:
        ch = scene.character
        closed = build / f"{scene.id}-closed.png"
        character_panel(inside(root, ch.image), w, h, ch.height, ch.side, closed)
        expression = None
        if ch.mouth_open and info["audio"]:
            opened = build / f"{scene.id}-open.png"
            character_panel(inside(root, ch.mouth_open), w, h, ch.height, ch.side, opened)
            windows = speech_windows(Path(info["audio"]), info["audio_start"])
            if windows:
                expression = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in windows)
        overlay(closed, f"not({expression})" if expression else None)
        if expression:
            overlay(opened, expression)
    if scene.title:
        title = build / f"{scene.id}-title.png"
        text_panel(scene.title, w, h, font, title, title=True)
        overlay(title)
    for i, caption in enumerate(info["captions"] if scene.caption_mode == "burn" else []):
        path = build / f"{scene.id}-caption-{i}.png"
        text_panel(caption["text"], w, h, font, path)
        overlay(path, f"gte(t,{caption['start']})*lt(t,{caption['end']})")

    # Keep narration as its own stem so music ducks only while the narrator speaks.
    if info["audio"]:
        args += ["-i", info["audio"]]
        delay = round(info["audio_start"] * 1000)
        filters.append(f"[{idx}:a]adelay={delay}:all=1,apad,atrim=duration={length},"
                       "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[narr]")
    else:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        filters.append(f"[{idx}:a]atrim=duration={length}[narr]")
    idx += 1
    source_has_audio = (scene.source and Path(scene.source).suffix.lower() not in IMAGE_EXT
                        and any(s["codec_type"] == "audio" for s in probe(inside(root, scene.source))["streams"]))
    if source_has_audio and scene.source_volume:
        if scene.speed_ramps:
            # Each span is resampled in its own pass; feed the joined result back in.
            retimed = retime_audio(inside(root, scene.source), scene, length,
                                   build / f"{scene.id}-retimed.wav")
            args += ["-i", str(retimed)]
            filters.append(f"[{idx}:a]asetpts=PTS-STARTPTS,volume={scene.source_volume},"
                           f"apad,atrim=duration={length},aresample=48000[srcaudio]")
            idx += 1
        else:
            filters.append(f"[0:a]asetpts=PTS-STARTPTS,{','.join(atempo_chain(scene.speed))},"
                           f"volume={scene.source_volume},apad,atrim=duration={length},"
                           "aresample=48000[srcaudio]")
        filters.append("[narr]asplit=2[narrout][narrmix]")
        filters.append("[srcaudio][narrmix]amix=inputs=2:normalize=0:duration=longest,alimiter=limit=0.95:latency=1[mix]")
    else:
        filters.append("[narr]asplit=2[narrout][mix]")
    mix = "mix"
    if scene.sound_effects:
        inputs = "[mix]"
        for i, effect in enumerate(scene.sound_effects):
            args += ["-ss", str(effect.source_in), "-i", str(inside(root, effect.source))]
            filters.append(f"[{idx}:a]atrim=duration={effect.duration},asetpts=PTS-STARTPTS,"
                           f"volume={effect.volume},afade=t=in:d={effect.fade_in},"
                           f"afade=t=out:st={effect.duration-effect.fade_out}:d={effect.fade_out},"
                           f"adelay={round(effect.start*1000)}:all=1,apad,atrim=duration={length},"
                           f"aformat=sample_rates=48000:channel_layouts=stereo[sfx{i}]")
            inputs += f"[sfx{i}]"
            idx += 1
        filters.append(f"{inputs}amix=inputs={len(scene.sound_effects)+1}:normalize=0:duration=first,"
                       "alimiter=limit=0.95:latency=1[finalmix]")
        mix = "finalmix"
    out = build / f"{scene.id}.mp4"
    stem = build / f"{scene.id}-stem.wav"
    args += ["-filter_complex", ";".join(filters), "-map", f"[{current}]", "-map", f"[{mix}]",
             "-t", str(length), "-c:v", "libx264", "-preset", "fast", "-crf", "20",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2",
             "-movflags", "+faststart", str(out), "-map", "[narrout]", "-t", str(length),
             "-c:a", "pcm_s16le", str(stem)]
    ffmpeg(args)
    return out, stem


def join(project, resolved, clips, stems, build):
    if len(clips) == 1:
        return clips[0], stems[0]
    args, filters = [], []
    for clip, stem in zip(clips, stems):
        args += ["-i", str(clip), "-i", str(stem)]
    for i in range(len(clips)):
        filters += [f"[{2*i}:v]settb=AVTB,setpts=PTS-STARTPTS[v{i}]",
                    f"[{2*i}:a]aresample=48000,asetpts=PTS-STARTPTS,atrim=duration={resolved[i]['duration']}[a{i}]",
                    f"[{2*i+1}:a]asetpts=PTS-STARTPTS[n{i}]"]
    v, a, n = "v0", "a0", "n0"
    length = resolved[0]["duration"]
    overlap = round(project.transition_seconds * project.fps) / project.fps
    for i in range(1, len(clips)):
        nv, na, nn = f"jv{i}", f"ja{i}", f"jn{i}"
        transition = project.scenes[i].transition
        if transition == "cut":
            filters.append(f"[{v}][{a}][v{i}][a{i}]concat=n=2:v=1:a=1[{nv}][{na}]")
            filters.append(f"[{n}][n{i}]concat=n=2:v=0:a=1[{nn}]")
            length += resolved[i]["duration"]
        else:
            filters.append(f"[{v}][v{i}]xfade=transition={transition}:duration={overlap}:offset={length-overlap}[{nv}]")
            filters.append(f"[{a}][a{i}]acrossfade=d={overlap}:c1=tri:c2=tri[{na}]")
            filters.append(f"[{n}][n{i}]acrossfade=d={overlap}:c1=tri:c2=tri[{nn}]")
            length += resolved[i]["duration"] - overlap
        v, a, n = nv, na, nn
    out, stem = build / "joined.mp4", build / "narration.wav"
    ffmpeg(args + ["-filter_complex", ";".join(filters), "-map", f"[{v}]", "-map", f"[{a}]",
                    "-t", str(length), "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(out), "-map", f"[{n}]",
                    "-t", str(length), "-c:a", "pcm_s16le", str(stem)])
    return out, stem


def srt_time(value):
    ms = round(value * 1000)
    return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"


def render(root: Path, project_path: str, preview=False, progress=lambda _: None,
           preview_width: int = 640) -> dict:
    root = root.resolve()
    project = load(root, project_path)
    original = project.model_dump(mode="json")
    if preview:
        # Never upscale; a larger preview_width is how a single scene gets checked
        # at a resolution where on-screen text is actually legible.
        ratio = min(1, preview_width / project.width)
        project.width = int(project.width * ratio) // 2 * 2
        project.height = int(project.height * ratio) // 2 * 2
    build = root / "renders" / uuid.uuid4().hex
    build.mkdir(parents=True)
    (build / "project.json").write_text(json.dumps(original, ensure_ascii=False, indent=2))
    try:
        progress("Preparing narration and timeline")
        resolved = prepare(root, project, build)
        (build / "timeline.json").write_text(json.dumps(resolved, ensure_ascii=False, indent=2))
        font = font_path(inside(root, project.font) if project.font else None)
        clips, stems = [], []
        for i, (scene, info) in enumerate(zip(project.scenes, resolved)):
            progress(f"Rendering scene {i+1}/{len(resolved)}: {scene.id}")
            clip, stem = render_scene(root, project, scene, info, build, font)
            clips.append(clip)
            stems.append(stem)
        progress("Joining scenes and mixing audio")
        movie, narration = join(project, resolved, clips, stems, build)
        output = build / "video.mp4"
        if project.music:
            length = resolved[-1]["start"] + resolved[-1]["duration"]
            fade = min(1, length / 3)
            filters = [f"[1:a]volume={project.music.volume},atrim=duration={length},"
                       f"afade=t=in:d={fade},afade=t=out:st={length-fade}:d={fade}[bg]"]
            if project.music.duck:
                filters += ["[bg][2:a]sidechaincompress=threshold=0.025:ratio=8:attack=20:release=350[duck]"]
                bg = "duck"
            else:
                bg = "bg"
            filters.append(f"[0:a][{bg}]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:latency=1[out]")
            ffmpeg(["-i", str(movie), "-stream_loop", "-1", "-i", str(inside(root, project.music.source)),
                    "-i", str(narration), "-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[out]",
                    "-t", str(length), "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(output)])
        else:
            ffmpeg(["-i", str(movie), "-c", "copy", "-movflags", "+faststart", str(output)])
        entries = sorted(({**c, "start": c["start"] + s["start"], "end": c["end"] + s["start"]}
                          for s in resolved for c in s["captions"]), key=lambda c: c["start"])
        (build / "captions.srt").write_text("\n\n".join(
            f"{i+1}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}" for i, c in enumerate(entries)), encoding="utf-8")
        (build / "credits.txt").write_text("\n".join(project.credits), encoding="utf-8")
        expected = resolved[-1]["start"] + resolved[-1]["duration"]
        actual = duration(output)
        if abs(expected - actual) > max(0.15, 2 / project.fps):
            raise RuntimeError(f"Duration mismatch: expected {expected}, got {actual}")
        result = {"video": str(output), "duration": actual, "preview": preview,
                  "width": project.width, "height": project.height,
                  "project": str(build / "project.json"), "timeline": str(build / "timeline.json"),
                  "captions": str(build / "captions.srt"), "credits": str(build / "credits.txt")}
        (build / "result.json").write_text(json.dumps(result, indent=2))
        progress("Complete")
        return result
    except Exception as error:
        (build / "error.txt").write_text(str(error))
        raise
