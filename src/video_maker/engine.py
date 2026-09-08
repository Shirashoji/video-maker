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
            if scene.source_in >= float(meta["format"]["duration"]):
                raise ValueError(f"{scene.id}: source_in exceeds source duration")
        if scene.voice and not project.credits:
            warnings.append("Add the selected VOICEVOX character credit to project.credits before publishing.")
    if project.music:
        inside(root, project.music.source)
    font_path(inside(root, project.font) if project.font else None)
    return {"valid": True, "scenes": len(project.scenes), "warnings": sorted(set(warnings))}


def prepare(root: Path, project: Project, build: Path) -> list[dict]:
    """Resolve actual audio durations before choosing frame-exact scene lengths."""
    validate(root, project)
    resolved, cursor = [], 0.0
    fps = project.fps
    overlap = round(project.transition_seconds * fps) / fps
    for index, scene in enumerate(project.scenes):
        audio = None
        voice_captions = []
        if scene.voice:
            audio = build / f"{scene.id}-speech.wav"
            elapsed = 0.0
            with wave.open(str(audio), "wb") as combined:
                combined.setnchannels(1)
                combined.setsampwidth(2)
                combined.setframerate(48000)
                for part in subtitle_chunks(scene.voice.text, 0, 1):
                    fragment = Voicevox().synthesize(scene.voice.model_copy(update={"text": part["text"]}),
                                                    root / ".cache" / "voicevox")
                    with wave.open(str(fragment)) as source:
                        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 48000):
                            raise ValueError("VOICEVOX must return mono 16-bit 48 kHz WAV")
                        part_length = source.getnframes() / source.getframerate()
                        combined.writeframes(source.readframes(source.getnframes()))
                    voice_captions.append({"text": part["text"], "start": elapsed, "end": elapsed + part_length})
                    elapsed += part_length
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
            raise ValueError(f"{scene.id}: duration {length:.2f}s is too short; narration needs {required:.2f}s")
        if scene.transition != "cut" and min(length, resolved[-1]["duration"]) <= 2 * overlap:
            raise ValueError(f"{scene.id}: scenes must be longer than twice the transition duration")
        if scene.transition != "cut":
            cursor -= overlap
        captions = [c.model_dump() for c in scene.captions]
        if not captions and audio:
            if scene.voice:
                captions = [{**c, "start": c["start"] + head, "end": c["end"] + head} for c in voice_captions]
            elif scene.audio_text:
                captions = subtitle_chunks(scene.audio_text, head, audio_length)
        for caption in captions:
            if caption["end"] > length:
                raise ValueError(f"{scene.id}: caption extends past scene end")
        for graphic in scene.graphics:
            end = graphic.end if graphic.end is not None else length
            if graphic.start >= length or end > length or (graphic.keyframes and
                    graphic.keyframes[-1].time > end - graphic.start):
                raise ValueError(f"{scene.id}: graphic or keyframe extends past scene end")
        if scene.camera and scene.camera[-1].time > length:
            raise ValueError(f"{scene.id}: camera extends past scene end")
        for effect in scene.sound_effects:
            if effect.start + effect.duration > length + 1e-6:
                raise ValueError(f"{scene.id}: sound effect extends past scene end")
        if scene.caption_mode == "off":
            captions = []
        resolved.append({"id": scene.id, "start": cursor, "duration": length,
                         "audio": str(audio) if audio else None, "audio_start": head,
                         "audio_duration": audio_length, "captions": captions})
        cursor += length
    return resolved


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
    base = f"[0:v]setpts=(PTS-STARTPTS)/{scene.speed},"
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
        render_graphics(scene.graphics, w, h, fps, length, font, motion, root)
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
        speed = scene.speed
        tempos = []
        while speed < 0.5:
            tempos.append("atempo=0.5")
            speed /= 0.5
        while speed > 2:
            tempos.append("atempo=2")
            speed /= 2
        tempos.append(f"atempo={speed}")
        filters.append(f"[0:a]asetpts=PTS-STARTPTS,{','.join(tempos)},volume={scene.source_volume},"
                       f"apad,atrim=duration={length},aresample=48000[srcaudio]")
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


def render(root: Path, project_path: str, preview=False, progress=lambda _: None) -> dict:
    root = root.resolve()
    project = load(root, project_path)
    original = project.model_dump(mode="json")
    if preview:
        ratio = min(1, 640 / project.width)
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
                  "project": str(build / "project.json"), "timeline": str(build / "timeline.json"),
                  "captions": str(build / "captions.srt"), "credits": str(build / "credits.txt")}
        (build / "result.json").write_text(json.dumps(result, indent=2))
        progress("Complete")
        return result
    except Exception as error:
        (build / "error.txt").write_text(str(error))
        raise
