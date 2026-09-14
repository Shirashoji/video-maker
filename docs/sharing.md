# ClaudeとChatGPTで編集を引き継ぐ

Video Makerの編集データは、AIの会話の中ではなく**Mac上のワークスペース（既定 `~/Movies/VideoMaker`）**に保存されます。Claude Cowork・ChatGPT Work・Codex・CLIのどれから使っても、同じフォルダを読み書きします。

| 場面 | 方法 |
| --- | --- |
| 同じMacで、Claude Coworkで途中まで作りChatGPT Workで続ける（逆も同じ） | 何も移さなくてよい。**新しい会話で「続きを編集して」と頼む** |
| 別のMac・別の人に渡す | `export_project` で `.videomaker.zip` を作り、相手が `import_project` で取り込む |
| 完成動画だけを渡す | `export_render` でMP4とSRTを書き出す |

## 同じMacで引き継ぐ

前提は、両方のアプリに**同じビルドのVideo Maker**を導入していることです（[Claude Cowork](cowork-plugin.md) / [ChatGPT Work](work-plugin.md)）。古いビルドが残っていると、使えるツールや項目が食い違います。どちらでも `workspace_info` の `workspace` が同じパスを指していることを確認してください。環境変数 `VIDEO_MAKER_WORKSPACE` を片方だけに設定すると、別のフォルダを見てしまいます。

### 編集を終えるとき（引き継ぐ側）

AIに次のように頼みます。

> 今日の作業はここまで。次の担当者向けに、プロジェクトの notes に「目的・決めたこと・残作業」を書いて保存して。

プロジェクトJSONの `notes` は引き継ぎメモです（最大4000文字）。字幕や動画には出ません。JSON自体に入るので、どのクライアントで開いても、別のMacに移しても一緒に届きます。会話の履歴はアプリをまたいで引き継げません。台本の意図やユーザーから受けた指示のうち、今後も守るべきものはここに残してください。

### 続きを始めるとき（受け取る側）

> Video Makerで workspace_info を見て、「操作説明.json」の notes を読んでから続きを編集して。

`workspace_info` はプロジェクトごとに次を返します。

- `name` / `scenes` / `notes`：内容と引き継ぎメモ
- `modified` / `revision`：最終保存時刻と内容のハッシュ
- `latest_render`：最後に完了したレンダーの `job_id` と動画パス。再レンダーせずに `inspect_frames` や `export_render` で確認できます

### 同時に編集したとき

`read_project` は `revision` を返します。保存時に `save_project(..., overwrite=true, base_revision=<読んだときのrevision>)` を渡すと、その間に別のアプリが保存していた場合は上書きせずに `Conflict` エラーになります。AIは読み直して変更をまとめてから保存し直します。同梱Skillはこの手順に従うよう指示しています。

上書きした旧版は `revisions/<プロジェクト名>/<UTC時刻>-<revision>.json` に残ります。元に戻したい場合は、その内容で `save_project` するよう依頼してください。

レンダーはアプリごとに別プロセスで実行されます。同じプロジェクトを両方のアプリから同時にレンダーしないでください。

## 別のMac・別の人に渡す

> 「操作説明.json」を素材ごと ~/Desktop に書き出して。

`export_project(path, destination)` は、プロジェクトJSONと参照している素材（録画・立ち絵・画像・BGM・効果音・フォント）を1つの `<名前>.videomaker.zip` にまとめます。中には `manifest.json`（revision・notes・素材のSHA-256）が入ります。レンダー結果とVOICEVOXの音声キャッシュは含めません。受け取った側で再生成されます。

受け取る側：

> ~/Downloads/操作説明.videomaker.zip を import_project で取り込んで、notes を読んで続きを編集して。

`import_project` は素材を同じ相対パスに展開します。

- 同じ内容のファイルがすでにあれば再利用します。
- 同じパスに**内容の違うファイルがある場合は何も上書きせず**にエラーを返します。
- 同名のプロジェクトがある場合は `overwrite=true` が必要です。旧版は `revisions/` に残ります。
- `path` で別名に保存することもできます。

CLIでも同じことができます。

```sh
uv run video-maker projects
uv run video-maker export-project 操作説明.json ~/Desktop
uv run video-maker --workspace ~/Movies/VideoMaker import-project ~/Downloads/操作説明.videomaker.zip
```

注意：

- 素材の利用条件（キャラクター規約など）は受け取る人にも適用されます。再配布が禁止された素材を含むzipを他人に渡さないでください。
- VOICEVOXの話者IDは、受け取る側に同じ話者がインストールされている必要があります。
- zipは暗号化されません。

## うまくいかないとき

- **片方のアプリでプロジェクトが見えない**：両方で `workspace_info` を実行し、`workspace` のパスを比べてください。違う場合は `VIDEO_MAKER_WORKSPACE` の設定を揃えます。
- **片方にだけ `export_project` などのツールがない**：古いビルドが入っています。各導入手順の「更新」に従って入れ直してください。
- **Coworkでツールが1つも出ない**：クラウドで実行されるCoworkセッションでは、プラグインに同梱したローカルMCPが起動しません（[anthropics/claude-code#87537](https://github.com/anthropics/claude-code/issues/87537)）。Macのデスクトップアプリ上のセッションで使ってください。
