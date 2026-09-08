"""Create deterministic UI test footage, a quiet test music bed, and a demo project.

Uses the user's extracted zundamon PNGs if available; otherwise uses no character.
This draws a UI fixture, not AI-generated video content.
"""
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from video_maker.graphics import font_path
from video_maker.media import ffmpeg

root = Path("workspace").resolve()
assets = root / "assets" / "demo"
assets.mkdir(parents=True, exist_ok=True)
font = font_path()
large, normal, small = [ImageFont.truetype(font, n) for n in (44, 28, 20)]
base = Image.new("RGB", (1280, 720), "#101725")
d = ImageDraw.Draw(base)
d.text((55, 36), "VIDEO MAKER", font=large, fill="#e9f4ff")
d.text((55, 98), "素材から、伝わる解説動画へ。", font=normal, fill="#9aafc7")
d.rounded_rectangle((45, 165, 895, 585), radius=20, fill="#192638")
d.text((80, 195), "編集プロジェクト", font=normal, fill="#e9f4ff")
for i, (label, color) in enumerate([("画面録画  /  必要な部分を切り出す", "#4199dc"),
                                  ("ナレーション  /  VOICEVOX", "#48c7a6"),
                                  ("字幕  /  音声に合わせて表示", "#d6b868")]):
 y = 270 + i * 88
 d.rounded_rectangle((80,y,850,y+62), radius=9, fill=color)
 d.text((100,y+12), label, font=normal, fill="#101725")
d.text((55, 645), "DEMO FOOTAGE  •  実際の画面録画へ差し替え可能", font=small, fill="#9aafc7")
pipe = subprocess.Popen(["ffmpeg","-y","-loglevel","error","-f","rawvideo","-pix_fmt","rgb24",
                         "-s","1280x720","-r","15","-i","-","-an","-c:v","libx264",
                         "-preset","fast","-pix_fmt","yuv420p",str(assets/'screen.mp4')], stdin=subprocess.PIPE)
try:
 for i in range(15*12):
  frame=base.copy(); draw=ImageDraw.Draw(frame)
  x=80+int(770*i/(15*12))
  draw.line((x,255,x,535), fill="white", width=3)
  draw.ellipse((x-6,246,x+6,258), fill="white")
  pipe.stdin.write(frame.tobytes())
finally:
 pipe.stdin.close()
if pipe.wait(): raise RuntimeError("demo footage encoding failed")
ffmpeg(["-f","lavfi","-i","sine=frequency=220:duration=4:sample_rate=48000",
        "-af","volume=0.12","-c:a","pcm_s16le",str(assets/'music.wav')])
character = {"image":"assets/zundamon/closed.png","mouth_open":"assets/zundamon/open.png","height":0.68}
if not (root/character['image']).exists(): character=None
project={"version":1,"name":"ずんだもんのAI動画編集デモ","width":1280,"height":720,"fps":30,
 "credits":["VOICEVOX:ずんだもん","立ち絵: 坂本アヒル（ユーザー提供素材）","背景映像・テスト音: ローカル検証用素材"],
 "music":{"source":"assets/demo/music.wav","volume":0.15,"duck":True},
 "scenes":[
  {"id":"intro","source":"assets/demo/screen.mp4","character":character,
   "voice":{"text":"こんにちは、ずんだもんなのだ。録画した素材を使って、解説動画を作るのだ。","speaker":3}},
  {"id":"editing","source":"assets/demo/screen.mp4","source_in":2,"speed":1.5,"character":character,
   "transition":"fade","voice":{"text":"必要なところを切り出して、音声と字幕を重ねるのだ。口も音に合わせて動くのだ。","speaker":3}},
  {"id":"finish","source":"assets/demo/screen.mp4","source_in":6,"character":character,
   "transition":"wipeleft","voice":{"text":"キャラクターを変えたり、場面転換を加えたりできるのだ。編集内容は保存して、あとから直せるのだ。","speaker":3}}
 ]}
(root/'demo.json').write_text(json.dumps(project,ensure_ascii=False,indent=2))
print(root/'demo.json')
