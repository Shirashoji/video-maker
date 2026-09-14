# Video Maker

生成AIが**編集者として素材を選び、台本・カット・字幕・立ち絵を組み立てる**ためのローカルMCPとSkillです。映像の生成モデルは使いません。VOICEVOXとFFmpegで、編集内容をJSONから再現可能なMP4にします。

GUIの動画編集ソフトに依存せず、FFmpegとVOICEVOXを用いて本ツール単体で動画出力まで完結する独立した編集エンジン方式を採用しています。編集内容はJSONで宣言的に管理され、字幕や立ち絵が合成（焼き込み）された完成形のMP4動画を直接書き出します（外部の動画編集ソフトとのタイムライン連携やプロジェクトファイルの相互変換機能はありません）。

## できること

- ローカル動画・画像・音声の取り込み、メタデータとフレーム一覧の取得、無音区間の候補抽出（取り込み前の絶対パスも検査可、フレームは時間範囲指定可）
- 指定時刻のフレームを原寸で1枚取り出して内容を説明・確認する（`extract_frame`）。サムネイルでは読めない画面内の文字も確認でき、取り出したPNGは図解素材として再利用可
- レンダー前に確定尺・字幕時刻・図形の表示時刻・カメラの実効注視点を返すドライラン（`plan_timeline`）
- 完成した動画・SRT・編集JSONのワークスペース外への書き出し（`export_render`）
- Claude・ChatGPT・Codex間の編集の引き継ぎ：同じワークスペースの共有、引き継ぎメモ（`notes`）、同時編集の衝突検出（`base_revision`）、素材込みのプロジェクトzip（`export_project` / `import_project`）
- シーンの順番変更、切り出し、0.1〜20倍速、領域クロップ、静止画の挿入
- シーン内の区間ごとの早送り・スローモーション（`speed_ramps`）。待ち時間は畳み、速い操作は引き伸ばす。元音声も追従
- VOICEVOXの話者選択、台本から音声合成、実際の音声長に合わせた字幕
- キャラクターPSDのレイヤー確認とPNG書き出し、立ち絵の配置、音量連動の口パク
- 日本語テロップ・見出し、カット・ディゾルブ・ワイプ・スライド
- JSONで作る図形・矢印・説明スライド、キーフレームによる移動・拡縮・フェード
- **HTML/CSS（Flexbox/Grid）やMermaid（ダイアグラム）、SVGベクター画像の直接取り込みとアニメーション合成**（Headless Chrome / Mermaid CLI / resvg-py連携）
- **スライドや図解を動画全体レンダー前に1秒で透過PNGプレビュー・検証するツール（`render_asset`）と雛形生成（`asset_template`）**
- 録画と図解の透過合成・小窓配置、帯付き／縁取りテロップの登場・退場アニメーション
- グラデーション文字・背景、影付きカード・角丸画像、録画のズーム／パン、効果音の時刻指定
- キーノート風テンプレート（minimal / colorful）、字幕の焼き込み・SRTのみ・非表示の切り替え
- 元音声とナレーションのミックス、BGMループ・フェード・ナレーション連動の音量低下
- 低解像度プレビュー（シーン指定・解像度指定つき）、本番MP4、SRT、編集JSON、クレジット一覧、編集履歴
- 読み方の辞書（`readings`）による合成専用の読み替え。字幕・SRTは元の表記を保持

AIが素材を理解して構成を決める部分は、接続先のCodex等が担当します。レンダラー自身に意味理解や文字起こし機能はありません。APIキーを別途用意する必要はなく、既存のAIクライアントからツールを呼びます。

## 導入（Claude / ChatGPT）

1つのビルドから、ClaudeとChatGPTの両方に同じプラグインを入れられます。どちらもMacのデスクトップアプリで、ローカルMCPとして動きます。

**共通の準備**

1. Macに次を用意する。
   - VOICEVOX（アプリを起動しておく）
   - `brew install uv ffmpeg`
2. リポジトリで次を実行する。

   ```sh
   uv sync --extra dev
   .venv/bin/python scripts/build_plugin.py
   ```

   `dist/` にアップロード用のzipと、ローカルマーケットプレイスができます。

**使う場所ごとの手順**

| 使う場所 | 手順 | 詳細 |
| --- | --- | --- |
| **Claude Cowork**（Claude Desktop） | Coworkタブ → **Customize → Plugins** → Personal pluginsの **＋** → **Upload plugin** で `dist/video-maker.zip` を選ぶ（`.zip` のみ受け付けます） | [Claudeへの導入](docs/cowork-plugin.md) |
| **Claude Code** | `claude plugin marketplace add <repo>/dist` → `claude plugin install video-maker@video-maker-local` | [Claudeへの導入](docs/cowork-plugin.md#3b-claude-code-に導入する) |
| **ChatGPT Work / Codex**（ChatGPTデスクトップ） | `codex plugin marketplace add <repo>/dist` → `codex plugin add video-maker@video-maker-local` → ChatGPTアプリを再起動 | [ChatGPTへの導入](docs/work-plugin.md) |

**導入の確認**

導入後は、**新しい**タスクまたは会話で次のように依頼します。

> Video Makerで workspace_info と environment_status を実行して、保存先とVOICEVOXの接続を確認して。

**注意**

- ローカルMCPを含むため、次の環境では動きません。
  - ブラウザ版ChatGPT
  - クラウドで実行されるCoworkセッション
- 初回起動時に、uvが固定済みの依存関係をダウンロードします。
- 保存場所は `VIDEO_MAKER_WORKSPACE` / `VIDEO_MAKER_RUNTIME` で変更できます。
  - 素材とプロジェクト：`~/Movies/VideoMaker`
  - 実行環境：`~/Library/Caches/video-maker/venv`
  - どちらもプラグインの更新や削除では消えません。

**依頼の例**

> `/Users/.../録画.mov` を使って、ずんだもんの1分の操作説明動画を作って。重要な操作を見せながら説明し、字幕と口パクを付けて。まずプレビューを確認してから本番を書き出して。

- 素材をチャットにアップロードする必要はありません。
- 開発用の立ち絵などのアセットは、GitHubリポジトリには含まれていません。配置方法とクレジットは [アセットの導入方法](docs/assets-setup.md) を参照してください。

## ClaudeとChatGPTで編集を引き継ぐ

どのアプリから使っても、編集データは同じ `~/Movies/VideoMaker` に保存されます。そのため、**同じMacならファイルを移さずに**、Claude Coworkで作った編集をChatGPT Workで続けられます（逆も同じ）。

- **終えるとき**：「notesに目的・決めたこと・残作業を書いて保存して」と頼む。
  - `notes` はプロジェクトJSONに入る引き継ぎメモです。
- **始めるとき**：新しい会話で「workspace_infoを見て、notesを読んでから続きを編集して」と頼む。
- **同時に編集したとき**：`save_project` の `base_revision` により、相手の保存を上書きせず `Conflict` として止まります。
- **別のMacや別の人に渡すとき**：`export_project` で素材ごと `.videomaker.zip` にまとめ、相手が `import_project` で取り込みます。

詳しくは [編集の引き継ぎ](docs/sharing.md) を参照してください。

MCPが未接続でも、このフォルダの `AGENTS.md` とSkillからCLIを使って同じ編集ができます。

## CLI

```sh
uv sync --extra dev
uv run video-maker doctor
uv run video-maker speakers
uv run video-maker validate demo.json
uv run video-maker plan demo.json
uv run video-maker render demo.json --preview
uv run video-maker render demo.json --preview --scene step-2 --width 1920
uv run video-maker render demo.json
uv run video-maker inspect /Users/me/Movies/recording.mov
uv run video-maker frames assets/demo/screen.mp4 --start 12 --end 18
uv run video-maker frame assets/demo/screen.mp4 --time 14.5
```

既定の作業場所は `workspace/`。別の場所は `video-maker --workspace /absolute/path ...` で指定します。

FFmpeg/ffprobeは別途必要です（このMacは導入済み）。文字描画にPillowを使用するため、FFmpegのlibass/drawtext対応は不要です。Pythonは3.11以上を使います。音声合成先は既定で `http://127.0.0.1:50021`、変更時は `VOICEVOX_URL` を指定します。依存関係は `uv.lock` に固定します。

```sh
# 立ち絵のない最小例を試す
cp examples/minimal.json workspace/minimal.json
uv run video-maker render minimal.json

# ローカル検証用の背景動画とプロジェクトを作る
uv run python scripts/create_demo.py
uv run video-maker render demo.json

# テスト
uv run pytest -q
```

図解のサンプルは `examples/motion-graphics.json` を `workspace/` にコピーしてレンダーできます。
`scene.graphics` をコードで編集するだけで、図の配置・文字・配色・動きを変更できます。
録画シーンにも同じ要素を重ねられ、`source_rect` で録画と図解を並べられます。
詳しくは [図解・アニメーションの形式](docs/project-format.md#コードで編集する図解アニメーションテロップ) を参照してください。

キーノート風に作る場合は MCP `presentation_template` または次のCLIで構成を作れます。
大見出し・時間差で登場するカード・録画のズーム・締めを、すべてJSONで編集できます。

```sh
uv run video-maker template --style minimal --source assets/recording.mov > workspace/keynote.json
uv run video-maker render keynote.json --preview
```

素材不要の例は `examples/keynote-minimal.json` と `examples/keynote-colorful.json`。
これは2Dのプレゼンテーション表現です。3D製品映像や撮影素材が必要な場合は別途取り込みます。

## 他のMCPクライアント

STDIOサーバーのコマンドは `<repository>/.venv/bin/python`、引数は次の3つです。

```text
<repository>/scripts/serve.py
--workspace
<repository>/workspace
```

すべて実際の絶対パスに置き換えてください。HTTP待受ポートは作りません。主な呼び出しは `project_schema → inspect_media / import_asset → voicevox_speakers → save_project → plan_timeline → save_project（図解を追記）→ render_preview → job_status → render_final → export_render` です。レンダーは非同期ジョブなので、`job_status` の `complete` と結果パスを確認します。

## ファイルと制約

[編集JSONの書き方](docs/project-format.md) / [JSON Schema](docs/project.schema.json) / [AI用Skill](skills/video-editing/SKILL.md)

ユーザー素材・出力は `workspace/` に置き、Git管理から除外しています。元のダウンロードZIP・PSDは変更していません。キャラクターの利用条件は提供元の規約に従います。`credits` は別テキストとして出力し、表示したい場合はクレジットシーンを追加します。

現段階はローカルMCP/CLI版です。GUIタイムライン、外部動画編集ソフトとの連携（FCPXML等）、文字起こし、単語単位字幕、同一シーン内の複数キャラクター、HDR色管理、ジョブのキャンセル、縦横で倍率の異なるズームは未対応です。既存音声の `audio_text` 自動字幕は概算なので、正確な時刻が必要なら `captions` を指定します。

## 参照した公式資料

- [VOICEVOX Engine API](https://github.com/VOICEVOX/voicevox_engine)
- [FFmpegフィルター](https://ffmpeg.org/ffmpeg-filters.html)
- [MCP Python SDK v1（本実装は互換性のため1系に固定）](https://py.sdk.modelcontextprotocol.io/v1/)
- [psd-tools](https://psd-tools.readthedocs.io/en/latest/reference/psd_tools.html)
- [Codex Skills](https://developers.openai.com/codex/skills)
