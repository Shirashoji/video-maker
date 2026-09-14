# ChatGPT Work / Codexへの導入

Video Makerは、ChatGPTデスクトップアプリとCodexで使えるAgent Pluginです。同梱しているものは次のとおりです。

- マニフェスト：`.codex-plugin/plugin.json`
- MCPの起動設定：`.mcp.json`
- 編集Skill
- 実行コード

ローカルMCPを含むプラグインは **Desktop only** の扱いになり、**ChatGPTデスクトップアプリでだけ**動きます（[公式の対応範囲](https://learn.chatgpt.com/docs/enterprise/plugin-management)）。ブラウザ版のChatGPTからは使えません。

Claudeでも使う場合は [Claudeへの導入](cowork-plugin.md) を参照してください。同じMacなら、編集データは自動で共有されます（[編集の引き継ぎ](sharing.md)）。

## 1. 前提

- **MacのChatGPTデスクトップアプリ**（Work、またはアプリ内のCodex）
- **Codex CLI**（`codex`）
  - マーケットプレイスの登録に使います。
  - ChatGPTデスクトップアプリとプラグイン設定（`~/.codex/config.toml`）を共有しています。
- **VOICEVOX**：アプリを起動しておく。
- **FFmpeg / ffprobe**
- **uv**

  ```sh
  brew install uv ffmpeg
  ```

- 初回起動時に、uvが依存ライブラリをダウンロードします（ネット接続が必要）。
- 日本語フォントは、macOS標準のヒラギノを使います。

## 2. 配布ファイルを作る

```sh
uv sync --extra dev
.venv/bin/python scripts/build_plugin.py
```

`dist/.agents/plugins/marketplace.json` が、マーケットプレイス `video-maker-local` として `dist/video-maker/` を指します。ビルドのたびに `version` が `0.1.0+build.<時刻>` に変わります。Codexは版ごとにキャッシュを作るため、入れ直すと確実に新しいファイルが使われます。

## 3. 導入する

### 手順

1. `dist/` をマーケットプレイスとして登録する（パスは実際の絶対パスに置き換える）。

   ```sh
   codex plugin marketplace add /Users/<you>/develop/video-maker/dist
   ```

   `Added marketplace video-maker-local` と表示されれば成功です。

2. プラグインをインストールする。

   ```sh
   codex plugin add video-maker@video-maker-local
   ```

   CLIを使わない場合は、ChatGPTデスクトップアプリを再起動し、**Plugins** のディレクトリで提供元 **Video Maker (local)** を選んで **Video Maker** をインストールします。

3. 状態を確認する。

   ```sh
   codex plugin list
   ```

   `video-maker@video-maker-local  installed, enabled` と表示されれば成功です。

4. **ChatGPTデスクトップアプリを再起動**し、**新しいWorkの会話**を開く。
   - 導入前から開いていた会話には、ツールが表示されないことがあります。

5. 動作を確認する。

   > Video Makerで workspace_info と environment_status を実行して、保存先とVOICEVOXの接続を確認して。

   `workspace` に `~/Movies/VideoMaker`、`voicevox_version` にバージョン番号が返れば導入完了です。

### 以前の手順で導入していた場合

以前は `~/.agents/plugins/marketplace.json` から `~/plugins/video-maker` のコピーを指す方法で導入していました。この方法では、古いコピーが残ったまま使われ続けます。二重登録を避けるため、先に削除してください。

1. `codex plugin list` で `video-maker@<旧マーケットプレイス名>` を確認する。
2. `codex plugin remove video-maker@<旧マーケットプレイス名>` を実行する。
3. `~/.agents/plugins/marketplace.json` から `video-maker` の項目を削除する。
   - 個人用マーケットプレイスの `source.path` は、**ホームディレクトリ基準**で解決されます。ルートは `codex plugin marketplace list` の `ROOT` 列で確認できます。

## 4. 使う

新しいWorkの会話で、「Video Makerで」と明示して依頼します。

> `/Users/<you>/Movies/録画.mov` を使って、ずんだもんの1分の操作説明動画を作って。重要な操作を見せながら説明し、字幕と口パクを付けて。まずプレビューを確認してから本番を書き出して。

- 素材をチャットにアップロードする必要はありません。Mac上の絶対パスを伝えれば、`import_asset` が原本を残したままワークスペースへコピーします。
- 作業は通常、次の順で進みます。
  1. `workspace_info` / `environment_status`
  2. `import_asset`
  3. `save_project`
  4. `plan_timeline`
  5. `render_preview`
  6. `job_status`
  7. `inspect_frames` / `extract_frame`
  8. `render_final`
  9. `export_render`

## 5. 更新する

```sh
.venv/bin/python scripts/build_plugin.py
codex plugin add video-maker@video-maker-local
```

2つ目のコマンドで `Installed plugin root: …/video-maker/0.1.0+build.<新しい時刻>` と表示されたら、ChatGPTデスクトップアプリを再起動して新しい会話で試します。

`~/.codex/plugins/cache/` の中を直接編集しないでください。

## 仕組みと保存場所

- `.mcp.json` は `${CLAUDE_PLUGIN_ROOT}/scripts/start-mcp.sh` をstdioで起動します。
  - Codexは互換性のため、`PLUGIN_ROOT` に加えて `CLAUDE_PLUGIN_ROOT` も設定します。
  - そのため、Claudeと同じ設定ファイルで動きます。
- **素材とプロジェクト**：`~/Movies/VideoMaker`（`VIDEO_MAKER_WORKSPACE` で変更可）。Claude側と同じ場所です。
- **実行環境**：`~/Library/Caches/video-maker/venv`（`VIDEO_MAKER_RUNTIME` で変更可）
- VOICEVOXアプリとFFmpegはプラグインに含まれません。

## うまくいかないとき

- **Pluginsに Video Maker (local) が出ない**
  - `codex plugin marketplace list` に `video-maker-local` があるか確認する。
  - ChatGPTデスクトップアプリを再起動する。
- **ツールが古い（例：`export_project` がない）**
  - `codex plugin list` の `PATH` が `dist/video-maker` を指しているか確認する。
  - 「更新する」の手順で入れ直す。
- **「Video Maker requires uv」と出る**：uvを入れてから、アプリを再起動する。
- **VOICEVOXに接続できない**：Mac側でVOICEVOXアプリを起動する。

## 検証の範囲

PythonのテストとMCPスモークテスト（`scripts/smoke_plugin.py`）で、次を確認しています。

- 同梱の起動設定からMCP接続できること
- プレビューの作成
- 書き出し
- プロジェクトのzip化と取り込み

`codex plugin marketplace add` と `codex plugin add` による導入・更新は、隔離した `CODEX_HOME` で確認しました。ChatGPT Workの画面上での会話実行は、導入後に手動で確認してください。

公式資料：

- [Plugins](https://learn.chatgpt.com/docs/plugins)
- [Build plugins](https://developers.openai.com/plugins/build/plugins)
- [Plugin management](https://learn.chatgpt.com/docs/enterprise/plugin-management)
