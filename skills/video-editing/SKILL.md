---
name: video-editing
description: Edit local recordings into narrated explainer videos with VOICEVOX, interchangeable PSD or PNG characters, lip sync, captions, cuts, transitions and music using the video-maker MCP or CLI. Use for assembling and revising existing media, not generating video imagery.
---

Use the video-maker tools to turn user-provided material and a script into a reproducible timeline and MP4. The AI selects footage and writes the edit; the local engine executes it. Do not imply the renderer understands screen content on its own.

## Workspace and entry points

This skill is bundled in the Video Maker plugin for Claude desktop Cowork, Claude Code, ChatGPT desktop Work and local Codex. The plugin root is two directories above this skill folder. Call `workspace_info` for the actual asset/project workspace; the installed plugin defaults to `~/Movies/VideoMaker`, configurable through `VIDEO_MAKER_WORKSPACE`. Never store user media in the versioned plugin cache. The development CLI defaults to `<repository>/workspace`.

Use the video-maker MCP if connected. Begin with `workspace_info` and `environment_status`. In Cowork, a sandbox path may differ from a Mac host path: use paths returned by MCP tools and do not assume the Cowork shell can reach the host's files or VOICEVOX at localhost. If local MCP tools are unavailable, explain the connection failure and consult `docs/cowork-plugin.md`; do not substitute a cloud connector pointed at localhost. When a local shell and the installed runtime are available, the CLI can run the same pipeline from the plugin/repository root:

```sh
PYTHONPATH=src .venv/bin/python -m video_maker.cli --workspace workspace doctor
PYTHONPATH=src .venv/bin/python -m video_maker.cli --workspace workspace render demo.json --preview
```

Read `docs/project-format.md` in the repository for project fields and `examples/minimal.json` for a starting point. The authoritative machine-readable format is MCP `project_schema` or `docs/project.schema.json`.

## Coordinate systems

Three different reference frames are in play. Getting these wrong is the most common source of misplaced elements:

- `graphics` `x,y,width,height`, `font_size`, `radius`, `stroke_width`: fractions of the **output canvas**. `x,y` is the top-left corner, except on `arrow`/`line` where it is the tail and `x2,y2` the head.
- `camera` `x,y`: fractions of the **recording's display area** — the `source_rect` box, letterbox/pillarbox bars included — not of the output canvas and not of the source file. The focus is clamped at the edges so the zoom window never leaves that area.
- `crop` `[x,y,width,height]`: fractions of the **source file**, applied before the recording is scaled and padded into its display area.

Do not convert between them by hand. `plan_timeline` returns each scene's `layout` with `display_rect` and `content_rect` in output fractions, `content_rect_in_camera` (where the picture sits once the bars are removed), and `camera` entries carrying `effective_x`/`effective_y` after clamping. `camera_x = (output_x - display_rect[0]) / display_rect[2]`.

## Editing workflow

1. Discover actual assets with `list_assets`, or copy user-selected files using `import_asset`. `inspect_media`, `inspect_frames` and `detect_silence` also accept an absolute path, so inspect a recording *before* importing it and import only what the edit uses. A filename alone does not establish what a recording shows. Give `inspect_frames` a `start`/`end` to aim at a cut, a telop entrance or one scene instead of spreading samples across the whole file. Its tiles are thumbnails; when the question is what a single moment actually shows — which screen is open, whether a telop is legible, what a cut lands on — use `extract_frame(path, time)` for that one frame at full size, and describe it from the image rather than from the filename. `detect_silence` proposes ranges; a silent screen recording may still contain important actions.
2. Get installed styles with `voicevox_speakers`. Select the requested character/style; IDs are engine-specific. Draft scene-sized narration explaining what the selected recording actually shows.
3. PNGs may be used directly. For a PSD, call `psd_layers`, then `export_character` with explicit visibility overrides. Disable sibling mouth layers when enabling another; preserve the source PSD. Export closed/open sprites with exactly the same canvas, pose, and non-mouth layers. PSDTool-specific group rules are not automatically interpreted. Inspect the exported PNGs.
4. Save the strict project JSON. Use relative paths returned by tools, stable scene IDs, and one narration/character configuration per scene. Different scenes may have different characters. Set `source_in`, `speed`, `crop`, and output `duration` to select recording segments. `speed` re-times the whole scene; `speed_ramps` re-times passages within it, so a long wait can be fast-forwarded and a fast interaction shown in slow motion in the same take. Ramp `start`/`end` are source seconds after `source_in`, while captions, graphics and camera stay in output seconds — read `plan_timeline`'s `retiming` for the mapping instead of computing it. Short source clips hold the last frame; inspect whether that looks intentional. Narration determines scene duration when `duration` is omitted.
5. Save the scenes and narration first, then call `plan_timeline` before writing `graphics`, `captions` or `camera` times. It resolves every scene's final duration, caption times, graphic times, camera framing and layout without rendering, reports all problems at once instead of failing on the first, and warms the narration cache the render will reuse. Write the timed layers against those numbers and save again. `"scene_end"` and `"scene_end-0.5"` are accepted for graphic and caption `start`/`end` when a time should follow the scene end; `camera` times and `sound_effects` starts are numeric, so take them from `plan_timeline`.
6. Put relevant source/character credits in `credits`; this creates a text sidecar, not a visible credit scene. Add a final title scene when an on-screen credit is wanted. Respect the supplied asset readme and actual character terms.
7. `render_preview` returns immediately with a job ID. Poll `job_status` at sensible intervals until complete/failed. Open the resulting video and inspect frames at cuts and caption changes; check that important UI is not obscured. The default preview is downscaled and cannot settle whether text inside a recording is legible: pass `scenes` and a larger `width` to re-render just that scene near full size instead of running a whole final. Revise the project using `save_project(overwrite=true)`; it keeps the previous JSON in `revisions/`.
8. Use `render_final` for full resolution. Deliver the MP4 plus the editable project and SRT with `export_render(job_id, destination)`, which copies them to a folder the user names; without it the output only exists under the workspace `renders/<id>/`. State any actual remaining limitation. Failed jobs return a concrete error; fix it before reporting success.

## Timing and scope

- VOICEVOX narration is synthesized in caption-sized phrases. Their actual WAV lengths determine caption boundaries; this is phrase timing, not word-level forced alignment. Imported audio with `audio_text` uses approximate character-weighted timing; supply explicit `captions` for exact timing.
- `synthesize_voice` splits and concatenates exactly as a render does and returns `duration`, per-phrase `chunks` and the `scene_duration` a scene would take, so auditioning one line needs no follow-up `inspect_media`. For a whole project prefer `plan_timeline`.
- Project `readings` (`{"GraphVisAgent": "グラフビズエージェント"}`) changes only what VOICEVOX is asked to say. Captions, burned-in text and SRT keep the original spelling, so product names stay correct on screen. Longer entries are substituted first.
- Transitions overlap scene ends. The engine adds quiet handles around narration so narration from adjacent scenes does not overlap. Do not shorten a scene below the required voice length; the renderer rejects truncation.
- Mouth-open/closed switching follows audio energy, not phoneme-specific visemes. It requires two full transparent sprites; a single PNG remains static.
- `source_volume` defaults to zero. Enable it intentionally; it is mixed with narration. BGM may duck against a separate narration stem.
- No transcription, video generation, automatic semantic cut selection inside the engine, FCPXML round-trip, or Final Cut Pro UI automation is implemented. MP4 can be opened in a video editor, while editable layers remain in JSON.
- All rendering is local. VOICEVOX must be running at `http://127.0.0.1:50021` unless `VOICEVOX_URL` is configured. Render jobs are serial, retain artifacts, and are marked interrupted after server restart; resubmit to continue.

## Telop color and readability

Before choosing or revising telop, title-card or explanatory graphic colors, read [references/telop-color.md](references/telop-color.md). Use it to select a coherent palette, separate text from moving footage, map colors to supported JSON fields and check the rendered result. Preserve explicit user/brand choices; the guide's palettes are starting points, not mandatory themes. Reuse the chosen color roles across scenes rather than inventing a new combination for every telop.

## Code-authored explanations and motion graphics

Author diagrams and animated slides directly in `scene.graphics`; this is editable declarative JSON, not image generation. Consult `docs/project-format.md` and `examples/motion-graphics.json`. Available elements are text, rect, ellipse, arrow and line; combine them into flowcharts, callouts and explanatory slides. `enter`/`exit` provide fade, slide and pop effects, and `keyframes` control position, scale and opacity. No arbitrary code execution is supported.

Use a scene without `source` for a full-screen explanatory slide. Add `graphics` to a recording scene for overlays, or set `source_rect` to put the recording beside the diagram. Import uploaded/local user media first and preserve originals. Use `style: impact` for short emphasized telops and `style: banner` for lower thirds or labels; these are separate from captions and are not included in SRT. Keep important recorded UI and caption areas readable. Prefer a few timed reveals to continuous motion. Read resolved narration/caption times from preview `timeline.json`, align graphics to the speech, inspect frames during entrances, holds and exits, then render final. Graphics paint in array order, below characters, titles and captions.

## Keynote-style product storytelling

Use `presentation_template` (or CLI `template --style minimal|colorful`) as an editable starting point for a premium presentation. Read `docs/project-format.md` and `examples/keynote-minimal.json` / `keynote-colorful.json`. Templates contain placeholder copy: rewrite it to match inspected media and real claims. The returned JSON is not saved until `save_project`.

Build a sequence of a short hero headline, staggered feature cards, a large recording demo and a closing message. Keep one message per scene and consistent spacing/colors. Use `background_gradient`, graphic `gradient`, `shadow` and `kind: image` for visual hierarchy; use restrained `ease_out` motion and hold long enough to read. Images are workspace assets, not generated imagery. Set `camera` keyframes to focus the recording on relevant UI; crop and zoom reduce visible context, so inspect the focus at the start, midpoint and end. Camera times are scene output seconds and do not follow source speed. `caption_mode: sidecar` preserves SRT while allowing uncluttered hero slides. Use `sound_effects` for user-provided or original licensed audio cues; do not add placeholder test tones as production music. Align cues to the motion and audition the final mix. Effects do not enter the narration ducking stem.

Do not promise a studio keynote's 3D cinematography from these 2D tools. State limitations relevant to the requested shot and use imported rendered media when appropriate. Never invent product statistics for a visually impressive card.

Zoom is uniform in both axes; there is no separate horizontal and vertical magnification, and adding one would stretch text out of shape. To feature a tall narrow region such as a chat column, set a fixed `crop` around it and place it in a portrait `source_rect`, then use `camera` keyframes to pan vertically inside that crop as the content scrolls, rather than re-choosing the crop for every scene. Check the framing with `plan_timeline`'s `layout` and `effective_x`/`effective_y` before rendering.

For constant-speed camera zooms, explicitly put `easing: linear` on the starting key of the moving interval; ease_in_out intentionally accelerates/decelerates. Inspect consecutive frames during slow zooms, not only their endpoints or a contact sheet. Track a stationary landmark around the chosen focal point to detect jitter. The renderer uses subpixel camera sampling; do not reintroduce integer crop-based zooms.
