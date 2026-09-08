from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Voice(Model):
    text: str = Field(min_length=1, max_length=2000)
    speaker: int = Field(default=3, ge=0)
    speed: float = Field(default=1, ge=0.5, le=2)
    pitch: float = Field(default=0, ge=-0.15, le=0.15)
    volume: float = Field(default=1, ge=0, le=2)


class Character(Model):
    image: str
    mouth_open: str | None = None
    side: Literal["left", "right"] = "right"
    height: float = Field(default=0.62, ge=0.1, le=0.9)


class Caption(Model):
    text: str = Field(min_length=1, max_length=500)
    start: float = Field(default=0, ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("caption end must be after start")
        return self


Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")]
Easing = Literal["linear", "ease_in_out", "ease_out", "hold"]


class Gradient(Model):
    colors: list[Color] = Field(min_length=2, max_length=8)
    direction: Literal["horizontal", "vertical", "diagonal"] = "horizontal"


class Shadow(Model):
    color: Color = "#00000055"
    blur: float = Field(default=0.025, ge=0, le=0.15)
    x: float = Field(default=0, ge=-0.2, le=0.2)
    y: float = Field(default=0.012, ge=-0.2, le=0.2)


class CameraKeyframe(Model):
    time: float = Field(ge=0)
    zoom: float = Field(default=1, ge=1, le=6)
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.5, ge=0, le=1)
    easing: Easing = "ease_in_out"


class SoundEffect(Model):
    source: str
    start: float = Field(default=0, ge=0)
    source_in: float = Field(default=0, ge=0)
    duration: float = Field(gt=0, le=60)
    volume: float = Field(default=0.3, ge=0, le=2)
    fade_in: float = Field(default=0.02, ge=0, le=5)
    fade_out: float = Field(default=0.1, ge=0, le=5)

    @model_validator(mode="after")
    def fades_fit(self):
        if self.fade_in + self.fade_out > self.duration:
            raise ValueError("sound effect fades must fit within duration")
        return self


class Keyframe(Model):
    time: float = Field(ge=0)
    x: float = Field(ge=-2, le=2)
    y: float = Field(ge=-2, le=2)
    scale: float = Field(default=1, gt=0, le=4)
    opacity: float = Field(default=1, ge=0, le=1)
    easing: Easing = "ease_in_out"


class Graphic(Model):
    """Declarative, editable graphics. Coordinates are fractions of the output canvas."""
    kind: Literal["text", "rect", "ellipse", "arrow", "line", "image"]
    source: str | None = None
    fit: Literal["contain", "cover"] = "contain"
    gradient: Gradient | None = None
    shadow: Shadow | None = None
    start: float = Field(default=0, ge=0)
    end: float | None = Field(default=None, gt=0)
    x: float = Field(default=0.1, ge=-2, le=2)
    y: float = Field(default=0.1, ge=-2, le=2)
    width: float = Field(default=0.8, gt=0, le=2)
    height: float = Field(default=0.15, gt=0, le=2)
    # For lines/arrows, (x,y) is the tail and (x2,y2) the head.
    x2: float | None = Field(default=None, ge=-2, le=2)
    y2: float | None = Field(default=None, ge=-2, le=2)
    text: str | None = Field(default=None, min_length=1, max_length=1000)
    fill: Color = "#FFFFFF"
    stroke: Color = "#00000000"
    stroke_width: float = Field(default=0.003, ge=0, le=0.05)
    radius: float = Field(default=0.02, ge=0, le=0.5)
    font_size: float = Field(default=0.055, gt=0, le=0.5)
    align: Literal["left", "center", "right"] = "center"
    style: Literal["plain", "impact", "banner"] = "plain"
    panel: Color = "#111827E8"
    opacity: float = Field(default=1, ge=0, le=1)
    enter: Literal["none", "fade", "slide_left", "slide_up", "pop"] = "none"
    exit: Literal["none", "fade", "slide_left", "slide_up", "pop"] = "none"
    animation_seconds: float = Field(default=0.3, gt=0, le=5)
    keyframes: list[Keyframe] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def valid_graphic(self):
        if self.end is not None and self.end <= self.start:
            raise ValueError("graphic end must be after start")
        if self.kind == "text" and not self.text:
            raise ValueError("text graphic requires text")
        if (self.kind == "image") != (self.source is not None):
            raise ValueError("source is required only for image graphics")
        if self.gradient and (self.kind not in ("text", "rect", "ellipse") or self.style == "banner"):
            raise ValueError("gradient supports plain/impact text, rect and ellipse")
        if self.kind in ("arrow", "line") and (self.x2 is None or self.y2 is None):
            raise ValueError("arrow/line requires x2 and y2")
        times = [k.time for k in self.keyframes]
        if times != sorted(set(times)):
            raise ValueError("keyframe times must be strictly increasing")
        if self.end is not None and times and times[-1] > self.end - self.start:
            raise ValueError("keyframe extends past graphic end")
        return self


class Scene(Model):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    source: str | None = None
    source_in: float = Field(default=0, ge=0)
    speed: float = Field(default=1, ge=0.25, le=8)
    # x/y/width/height in normalized source coordinates
    crop: tuple[float, float, float, float] | None = None
    duration: float | None = Field(default=None, ge=0.5, le=3600)
    background: str = Field(default="#111827", pattern=r"^#[0-9a-fA-F]{6}$")
    background_gradient: Gradient | None = None
    voice: Voice | None = None
    audio: str | None = None
    audio_text: str | None = None
    source_volume: float = Field(default=0, ge=0, le=2)
    source_rect: tuple[float, float, float, float] | None = None
    camera: list[CameraKeyframe] = Field(default_factory=list, max_length=100)
    sound_effects: list[SoundEffect] = Field(default_factory=list, max_length=100)
    caption_mode: Literal["burn", "sidecar", "off"] = "burn"
    graphics: list[Graphic] = Field(default_factory=list, max_length=100)
    character: Character | None = None
    title: str | None = Field(default=None, max_length=150)
    captions: list[Caption] = Field(default_factory=list, max_length=100)
    transition: Literal["cut", "fade", "wipeleft", "slideright"] = "cut"

    @model_validator(mode="after")
    def valid_scene(self):
        if self.voice and self.audio:
            raise ValueError("choose voice or audio, not both")
        if not self.voice and not self.audio and self.duration is None:
            raise ValueError("duration is required without narration")
        if self.crop:
            x, y, w, h = self.crop
            if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1
                    and x + w <= 1 and y + h <= 1):
                raise ValueError("crop must fit within normalized source bounds")
        if self.source_rect:
            x, y, w, h = self.source_rect
            if not self.source or not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1
                                      and 0 < h <= 1 and x + w <= 1 and y + h <= 1):
                raise ValueError("source_rect requires a source and must fit within output bounds")
        if self.camera:
            if not self.source:
                raise ValueError("camera requires source")
            times = [k.time for k in self.camera]
            if times != sorted(set(times)):
                raise ValueError("camera times must be strictly increasing")
        return self


class Music(Model):
    source: str
    volume: float = Field(default=0.12, ge=0, le=1)
    duck: bool = True


class Project(Model):
    version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=120)
    width: int = Field(default=1280, ge=320, le=3840, multiple_of=2)
    height: int = Field(default=720, ge=240, le=2160, multiple_of=2)
    fps: Literal[24, 25, 30, 60] = 30
    transition_seconds: float = Field(default=0.4, ge=0.1, le=1)
    font: str | None = None
    credits: list[str] = Field(default_factory=list)
    music: Music | None = None
    scenes: list[Scene] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_scenes(self):
        if len({s.id for s in self.scenes}) != len(self.scenes):
            raise ValueError("scene ids must be unique")
        if self.scenes[0].transition != "cut":
            raise ValueError("first scene must have transition=cut")
        return self
