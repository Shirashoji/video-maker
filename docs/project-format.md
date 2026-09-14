# 編集プロジェクトの形式

JSONのパスは `workspace` 相対です。MCP `import_asset` にユーザー指定の絶対パスを渡すと、原本を残してコピーし、相対パスを返します。`inspect_media` / `inspect_frames` / `extract_frame` / `detect_silence` は絶対パスも受け付けるので、取り込む前に中身を確認できます。schema は `project.schema.json` と MCP `project_schema` から参照できます。未知のキーはエラーになります。

座標系は三つあります。`graphics` の `x,y,width,height` は**出力画面**に対する比率、`camera` の `x,y` は**録画の表示領域**（`source_rect` の枠。ピラーボックスの余白を含む）に対する比率、`crop` は**素材**に対する比率です。手計算せず `plan_timeline` が返す `layout` と `camera` の実効値を使ってください。

```json
{
  "version": 1,
  "name": "操作説明",
  "notes": "目的: 新入生向け。決定: 話者はずんだもん。残作業: step-2の字幕位置の確認",
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "transition_seconds": 0.4,
  "credits": ["VOICEVOX:ずんだもん", "立ち絵: 坂本アヒル"],
  "music": {"source": "assets/bgm.wav", "volume": 0.12, "duck": true},
  "scenes": [
    {
      "id": "step-1",
      "source": "assets/recording.mov",
      "source_in": 12.5,
      "speed": 1.25,
      "source_volume": 0,
      "voice": {"text": "最初に設定画面を開くのだ。", "speaker": 3, "speed": 1},
      "character": {
        "image": "assets/character/closed.png",
        "mouth_open": "assets/character/open.png",
        "side": "right",
        "height": 0.65
      },
      "title": "1. 設定画面を開く"
    }
  ]
}
```

## 素材と尺

`source` は動画または静止画。省略すると `background` の単色背景です。縦横比を維持して画面に収めます。`source_in` は素材内の開始秒、`speed` は0.1〜20倍（シーン全体の基本再生速度）。`crop: [x,y,width,height]` は素材に対する0〜1の比率で、切り抜き後に拡大します。`duration` は編集後の秒数であり、素材の終了時刻ではありません。使用される元映像の長さは概ね `duration * speed` です。途中で素材が終わると末尾フレームを保持します。現在の対象は一般的なSDR素材で、HDR色管理は実装していません。

音声のあるシーンで `duration` を省略すると、実際のナレーション長と前後の余白から決定します。指定した尺が短すぎると切り捨てずにエラーにします。無音シーンには `duration` が必須です。総尺はシーン尺合計からトランジションの重複時間を引いた値です。画面サイズは偶数、fpsは24/25/30/60です。

### 尺を先に確定する（plan_timeline）

図解や字幕の時刻を書く前に MCP `plan_timeline(path)`（CLI は `plan`）を呼ぶと、レンダーせずに確定尺が分かります。返すのはシーンごとの `duration` / `start`、解決済みの `captions` と `graphics` の時刻、`camera` のクランプ後の実効注視点、`layout`（表示矩形）、`required_duration`、`issues` です。問題は最初の一件で止めず全部まとめて返します。ナレーションは `.cache/voicevox/` にキャッシュされるので、この事前計算は本番レンダーの下準備も兼ねます。

`graphics` と `captions` の `start` / `end` には `"scene_end"`、`"scene_end-0.5"` の相対指定も書けます。尺が未確定のまま「終わりの0.5秒前」を表現できます。`camera` の `time` と `sound_effects` の `start` は数値のみなので `plan_timeline` の値を使ってください。

### 早送りとスローモーション（speed / speed_ramps）

`speed` はシーン全体の再生速度です。1より大きければ早送り、小さければスローモーションになります。シーンの途中で速度を変えたいときは `speed_ramps` に区間を並べます。

```json
{
  "id": "walkthrough",
  "source": "assets/recording.mov",
  "source_in": 30,
  "duration": 9,
  "speed_ramps": [
    {"start": 2, "end": 3, "speed": 0.25},
    {"start": 5, "end": 17, "speed": 6}
  ]
}
```

`start` / `end` は **`source_in` から数えた素材内の秒数**です。区間は昇順で重複できません。指定しなかった範囲は `speed` の速度で再生されます。上の例では素材の2〜3秒を4倍に引き伸ばして4秒かけて見せ、5〜17秒の12秒間を1秒に畳んでいます。

出力側の時刻は速度から決まるので、`plan_timeline` が各区間の対応を `retiming` として返します。

```json
"retiming": {
  "source_in": 30, "source_consumed": 11.0,
  "spans": [
    {"source_start": 0, "source_end": 2,  "speed": 1,    "output_start": 0, "output_end": 2},
    {"source_start": 2, "source_end": 3,  "speed": 0.25, "output_start": 2, "output_end": 6},
    {"source_start": 3, "source_end": 5,  "speed": 1,    "output_start": 6, "output_end": 8},
    {"source_start": 5, "source_end": 11, "speed": 6,    "output_start": 8, "output_end": 9}
  ]
}
```

字幕・図解・`camera` の時刻は従来どおり**出力秒**なので、早送り区間にテロップを載せるときは `output_start` / `output_end` を見てください。`source_volume` を上げていれば素材音声も区間ごとに追従します（音程は変わります）。スローモーションはフレームを補間せず複製するので、素材のfpsを下回るとカクつきます。速度は静止画には効きません。素材が途中で尽きた区間は末尾フレームを保持します。

## 音声・字幕

`voice` でVOICEVOX合成、または `audio` で既存音声を指定します。同時指定できません。`voice.speaker` は `voicevox_speakers` で確認してください。文字列の名前は渡せません。声と絵は別指定なので、ずんだもん以外にも対応し、シーンごとに変更できます。

VOICEVOXは字幕単位の短い文に分けて合成し、実測のWAV長で字幕を同期します。`voice.speed`、`pitch`、`volume` も指定可能です。既存音声には `audio_text` を指定すると概算タイミングで字幕が付きます。既存音声の文字起こしは行いません。

MCP `synthesize_voice` は本番と同じ分割・連結で試聴用WAVを作り、`duration`、字幕単位の `chunks`、そのナレーションならシーンが何秒になるかの `scene_duration` を返します。長さを知るために `inspect_media` を呼び直す必要はありません。

読み方だけを変えたい場合はプロジェクト直下の `readings` を使います。

```json
"readings": {"GraphVisAgent": "グラフビズエージェント"}
```

置換はVOICEVOXに渡す文字列にのみ適用されます。字幕・焼き込みテキスト・SRTは元の表記のままなので、製品名を正しく表示したまま読みを調整できます。長いキーから先に置換するため、短い語が長い語の一部を先に消費することはありません。

正確に制御する場合は `captions: [{"text":"説明", "start":0.5, "end":2.4}]` を指定します。時刻はシーン冒頭からの秒であり、素材の `source_in` からではありません。`captions` が空でなければ自動字幕を置き換えます。字幕は日本語対応フォントで透過PNGに描画され、焼き込みとSRTの両方を出力します。SRTは別編集に使えますが、MP4上の焼き込み字幕を消すにはJSONから再レンダーします。

`font` を省略するとmacOSのヒラギノ等を探します。他環境は日本語TTF/OTF/TTCをインポートして指定してください。文字サイズは画面サイズと文字量に応じて調整します。単語ごとの色変更やカラオケ字幕は未対応です。

## 立ち絵・場面転換・BGM

`character.image` は透過PNG、`mouth_open` は口を開いた全身差分PNGです。同じ大きさ・位置のキャンバスを使ってください。音量に応じて二枚を切り替えます。`mouth_open` がなければ静止画です。`height` は画面高さに対する最大比率、`side` は `left` / `right`。一つのシーンで表示するキャラクターは一人です。表情はシーンごとのPNG差し替えで変更できます。

PSDは `psd_layers` でレイヤーを確認し、`export_character` に `{"/4/0":false,"/4/3":true}` のような明示的な変更を渡します。レイヤー番号はファイルごとに異なります。PSDToolの排他選択ルールは自動適用しません。

`transition` はそのシーンへの入り方です。最初は `cut`、以降は `cut` / `fade`（クロスディゾルブ）/ `wipeleft` / `slideright`。重なり時間は `transition_seconds` をフレーム単位に丸めます。発話の前後に余白を作り、隣の発話が重ならないようにします。

`source_volume` は元映像の音量（既定0）、`music.volume` はBGM音量です。BGMは必要尺までループし、始終をフェード、`duck:true` でナレーション中に下げます。テスト用デモの音は単純な確認用トーンです。本制作では使いたいBGMに差し替えてください。

## 保存・出力

MCP `render_preview` は既定で幅640に縮小します。`scenes: ["step-2"]` で特定シーンだけ、`width` で解像度を指定できます（プロジェクト解像度を超える拡大はしません）。録画内の文字が読めるかはプレビュー解像度では判断できないので、そのシーンだけ原寸に近い幅で回してください。シーンを絞ったレンダーは時刻が0から始まり、全体タイムラインとはずれます。`inspect_frames` は `start` / `end` でサンプリング範囲を指定できます。ある一瞬に何が映っているかを確かめたい場合は `extract_frame(path, time)` を使うと、その時刻のフレームを縮小せずに1枚返します（既定幅1280、拡大はしません）。コンタクトシートのサムネイルでは読めない画面内の文字もこちらなら読めます。書き出したPNGは workspace 内に残るので、`kind: "image"` の図解素材としてそのまま使えます。

完成物をワークスペース外に出すには MCP `export_render(job_id, destination, items, overwrite)` を使います。`items` は `video` / `captions` / `project` / `timeline` / `credits` から選び、既定は動画とSRTです。`destination` はフォルダ、または単一項目のときはファイルパスも指定できます。既存ファイルは `overwrite=true` がなければ上書きしません。

`notes` は、次に編集する人やAI向けの引き継ぎメモです（最大4000文字）。動画・字幕・SRTには出ません。

`read_project` は、プロジェクト本体・`revision`（内容のハッシュ）・更新時刻を返します。`save_project` に `base_revision` を渡すと、読んだ後に別のセッション（別のアプリなど）が保存していた場合は `Conflict` で拒否します。

プロジェクトを素材ごと別の環境へ移すには `export_project` / `import_project` を使います（`.videomaker.zip`）。詳しくは [編集の引き継ぎ](sharing.md) を参照してください。

プロジェクト上書き時は `revisions/<プロジェクト名>/<UTC時刻>-<revision>.json` に旧JSONを保存します。レンダーごとに新しい `renders/<id>/` を作るため、既存出力を上書きしません。`project.json`、確定した `timeline.json`、`video.mp4`、`captions.srt`、`credits.txt`、シーン別動画・音声を保持します。音声キャッシュは `.cache/voicevox/` に保存します。

`credits` はサイドカーの文字列です。動画内への表示は必要に応じてクレジットシーンを追加してください。出力フォルダには絶対パスも含まれるため、他PCへの移行には出力フォルダではなく `export_project` で作ったzip（プロジェクトJSONと参照素材）を使います。

MCPのレンダーはジョブ方式・一件ずつの処理です。再起動時に実行中だったジョブは `interrupted` と報告し、再実行が必要です。キャンセル・途中再開・自動キャッシュ掃除は未実装です。長時間・4K・多数シーンの負荷試験はしていません。

## コードで編集する図解・アニメーション・テロップ

`scene.graphics` は図解の宣言的なコードです。画像生成や外部ブラウザを使わず、JSONを編集して再レンダーできます。`source` のないシーンは全画面スライド、指定したシーンは録画に透過合成します。実行可能な例は `examples/motion-graphics.json`。同じシーンに `source` と `source_rect: [0.52, 0.2, 0.45, 0.55]` を追加すると、映像を右側の小窓に配置できます。左側に図解を配置すれば、実演と説明を並べられます。小窓内も元動画の縦横比を維持し、余白は背景色になります。

```json
"graphics": [
  {"kind":"text", "text":"ここがポイント！", "x":0.1, "y":0.15,
   "width":0.8, "height":0.2, "font_size":0.08, "style":"impact",
   "fill":"#FFE18A", "start":1, "end":3, "enter":"pop", "exit":"fade"},
  {"kind":"arrow", "x":0.2, "y":0.5, "x2":0.5, "y2":0.6,
   "fill":"#64E8D2", "stroke_width":0.006, "start":1.5, "end":3}
]
```

- `kind`: `text` / `rect`（角丸矩形）/ `ellipse` / `arrow` / `line`。配列の後の要素が手前になります。描画順は元映像 → graphics → 立ち絵 → title → 字幕です。
- `x,y,width,height`: 出力画面に対する比率。`x,y` は左上、矢印・線のみ始点です。`x2,y2` は矢印・線の終点。映像内の座標ではありません。負の位置も使え、画面外はクリップされます。
- `fill,stroke,panel`: `#RRGGBB` または透過度付き `#RRGGBBAA`。`stroke_width,radius,font_size` は画面高さに対する比率なのでプレビューでも配置が揃います。文字は領域内で折り返し・縮小します。
- テロップは `kind:"text"` と `style:"impact"`（縁取り）または `style:"banner"`（`panel` 色の帯）で作ります。`plain` は通常テキスト、`align` は `left/center/right`。字幕とは独立し、SRTには入りません。
- `start,end`: シーン冒頭からの秒、または `"scene_end"` / `"scene_end-0.5"` の相対指定。`end` 省略時はシーン終了まで。表示範囲は start 以上、end 未満。確定した尺からはみ出す要素はレンダー時にエラーになります。尺が未確定のうちは `plan_timeline` で確定させるか相対指定を使ってください。
- `enter,exit`: `none/fade/slide_left/slide_up/pop`。`animation_seconds` は既定0.3秒。短い表示は表示時間の半分に制限されます。
- `keyframes`: 要素の `start` からの秒 `time` と絶対位置 `x,y`、`scale`（既定1）、`opacity`（既定1）。時刻は昇順・重複不可。先頭以前・末尾以後は端の値を維持。`easing` はそのキーから次までの `linear/ease_in_out/hold`。拡縮は要素の中心基準で、線・矢印の形状も一緒に動きます。要素の `opacity`、登場・退場効果とも組み合わせられます。

AIは最初に実際の録画を確認し、短いテロップ、図解スライド、録画の実演を交互に配置してください。録画を全面に見せる場面では図を小さくし、重要なUIと字幕領域を避けます。ナレーションと図の出現を合わせるには `plan_timeline`（またはプレビューの `timeline.json`）の音声・字幕時刻を確認して `start` を調整します。

内部では要素をPillowで描画し、フレーム単位の透過動画をFFmpegで合成します。任意のPython/JavaScriptの実行、HTML/CSS、SVG読み込み、PowerPointのアニメーション取り込みには対応しません。長尺・4Kのアニメーションは描画時間と中間ファイル容量が増えるため、まずプレビューで確認してください。

## キーノート風の構成と仕上げ

MCP `presentation_template(style="minimal" | "colorful", title=..., subtitle=..., source=...)` は、編集可能なJSONを返します（保存はしません）。暗背景の `minimal` と明るい `colorful` があり、大見出し → 時間差で現れるカード → 任意の録画実演 → 締めの構成です。ブランド公式テンプレートではありません。仮の文言を素材に即した説明に置き換え、`save_project` で保存します。

CLIにも同じ入口があります。保存後に `plan` で確定尺を確認してから図解の時刻を書きます。

```sh
.venv/bin/python -m video_maker.cli template --style colorful --source assets/recording.mov > workspace/keynote.json
.venv/bin/python -m video_maker.cli plan keynote.json
.venv/bin/python -m video_maker.cli render keynote.json --preview
.venv/bin/python -m video_maker.cli render keynote.json --preview --scene demo --width 1920
```

素材不要の例は `examples/keynote-minimal.json` / `examples/keynote-colorful.json`。`scripts/create_keynote_demo.py --source assets/recording.mov` は新しいプロジェクトと控えめなオリジナル効果音を作成します。元ファイルは変更しません。

### グラデーション・影・画像

- `scene.background_gradient: {"colors":["#F8FAFF","#E7EEFF","#FFF1E8"],"direction":"diagonal"}` で背景を着色。2〜8色、方向は `horizontal/vertical/diagonal`、均等な色間隔です。録画の小窓の周囲にも適用されます。小窓内部のレターボックスは `background` 色です。
- `graphic.gradient` も同形式。文字・矩形・楕円の輪郭全体に適用し、`fill` の色を置き換えて透過度を掛け合わせます。帯付き文字、画像、線・矢印には指定できません。
- `graphic.shadow: {"color":"#00000040","blur":0.025,"x":0,"y":0.012}` で柔らかい影を追加。`x` は画面幅、`y,blur` は画面高さに対する比率です。影も要素と一緒に動きます。
- `{"kind":"image","source":"assets/screenshot.png","x":0.1,"y":0.2,"width":0.8,"height":0.6,"fit":"contain","radius":0.03,"shadow":{}}` でスクリーンショット・製品画像・ロゴを配置。`contain` は縦横比を保ち全体を表示（余白は透明）、`cover` は中央を切り抜いて枠を満たします。`radius` は角丸、素材はworkspace内の対応静止画です。既存の登場・退場・キーフレームが使えます。
- `easing:"ease_out"` は減速して止まる動きです。通常の位置・拡縮キーフレームと、以下のカメラで使えます。

### 録画へのズーム・パン

```json
"camera": [
  {"time":0,"zoom":1,"x":0.5,"y":0.5},
  {"time":1,"zoom":1,"x":0.5,"y":0.5,"easing":"ease_in_out"},
  {"time":3,"zoom":1.6,"x":0.3,"y":0.5},
  {"time":4.8,"zoom":1.6,"x":0.3,"y":0.5}
]
```

`time` はシーン開始からの出力秒。`source_in` や `speed` によって時刻は変わりません。`zoom` は1〜6倍で縦横同じ倍率です（縦横で別倍率のズームは文字が歪むため実装していません）。`x,y` は録画表示領域内の注視点（0〜1、既定中央）。先に固定 `crop` と縦横比調整を適用し、その表示領域をズームします。端では画面外が入らないよう注視点を制限します。字幕・図解はズームされません。先頭前・末尾後はキー値を保持し、`easing` は次のキーまでの補間です。拡大で失われる元映像の解像度は復元できません。

指定した `x,y` が実際にどこを向くかは `plan_timeline` の `camera[].effective_x` / `effective_y` と `visible_rect_in_camera` で確認できます。素材と出力の縦横比が違うとピラーボックス・レターボックスが入り、注視点の基準は余白を含んだ表示領域になります。`layout.content_rect_in_camera` が余白を除いた実映像の位置なので、`content_rect_in_camera` の範囲へ写像すれば素材上の狙った位置を指せます。

チャット欄のような縦長の領域を大きく見せる場合は、固定の `crop` でその領域を切り出して縦長の `source_rect` に置き、スクロールには `camera` の縦パンで追従させます。シーンごとに切り出し位置を決め直す必要はありません。

一定の速さで拡大したい場合は、移動区間の開始キーに `easing:"linear"` を指定します。`ease_in_out` は意図的に加速・減速します。キーノートテンプレートのズーム区間は `linear` です。描画は小数ピクセル精度の変換を使い、整数の切り抜き座標による横揺れ・縦揺れを防ぎます。元映像のフレームレートは自動補間しません。

### 効果音と字幕の表示切り替え

```json
"sound_effects": [
  {"source":"assets/whoosh.wav","start":1.2,"source_in":0,
   "duration":0.5,"volume":0.25,"fade_in":0.02,"fade_out":0.1}
],
"caption_mode": "sidecar"
```

効果音はシーン開始からの `start` 秒に挿入。音源の `source_in` から `duration` 秒を使います。尺・フェードが音源やシーンを超える場合はエラーになります。複数音を重ねられ、ナレーション・元音声に混ぜてピークを制限します。BGMのダッキング用ナレーション音声には効果音を混ぜません。

`caption_mode` は `burn`（既定、焼き込み＋SRT）、`sidecar`（SRTだけ）、`off`（両方なし）。ナレーションはそのままです。見出しを大きく見せる場面では `sidecar` を選べます。

### 制作の基準と今後の拡張

一画面一メッセージ、広い余白、短い見出し、同じ色・文字サイズ・動きの繰り返しを基本にします。強調が終わったら動きを止め、実演では録画を大きく表示します。効果音は転換点に絞り、ナレーションとBGMを聞きながら音量を決めます。テンプレートの数値・文言は製品の性能を保証しません。

現在は2D合成です。3D製品モデル、照明付き3Dカメラ、動画レイヤーの自由な多重配置、トラッキング、自動ビート解析、モーションブラー、縦横で倍率の異なるズーム、色の本格的なグレーディングは未実装です。これらが必要な構成は、外部で作った素材を取り込むか追加実装します。

構成の参考となる公式イベント: [Apple Events](https://www.apple.com/apple-events/) / [Google I/O keynote](https://io.google/2025/explore/google-keynote-1/)。レンダー実装の参照: [FFmpeg zoompan](https://ffmpeg.org/ffmpeg-filters.html#zoompan) / [Pillow](https://pillow.readthedocs.io/en/stable/)。
