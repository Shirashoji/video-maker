# ChatGPT Workへの導入

Video Makerは、ChatGPTデスクトップ向けのローカルAgent Pluginです。配布フォルダに `.codex-plugin/plugin.json`、`.mcp.json`、Skill、実行コード、依存関係ロックを同梱しています。

## 前提

- MacのChatGPTデスクトップでWorkを使用する。
- VOICEVOXを起動する。標準接続先は `http://127.0.0.1:50021`。
- `uv`、`ffmpeg`、`ffprobe` を用意する。このMacは導入済み。
- 日本語フォントはmacOSのヒラギノを使用。別フォントも指定可能。

ローカルMCPを含むプラグインはデスクトップ専用です。ブラウザ版Workで利用するには別途ホストされた接続と素材転送の設計が必要で、このパッケージには含めていません。[対応範囲](https://learn.chatgpt.com/docs/enterprise/plugin-management#desktop-only-plugins)

## 導入と実行

個人マーケットプレイスへ登録後、Pluginsで「Video Maker」を導入してください。CLIを使う場合は、登録済みマーケットプレイス名に対して `codex plugin add video-maker@<marketplace>` を実行します。ChatGPTデスクトップとローカルCodexで使用する形式です。導入後は新しいWorkの会話を開始し、`@Video Maker` を指定します。[プラグインの利用方法](https://developers.openai.com/codex/plugins)

最初の依頼例：

> Video Makerで、素材一覧とVOICEVOXの接続状態を確認して。画面録画とずんだもんの立ち絵を使って解説動画を作りたい。

`workspace_info` → `environment_status` で作業場所と接続を確認します。通常は `~/Movies/VideoMaker` にプロジェクトと素材が保存されます。`import_asset` に素材の絶対パスを渡すと原本を残して取り込みます。台本を書いて `save_project` → `render_preview` → `job_status` → `inspect_frames`（気になる瞬間は `extract_frame`）→ `render_final` の順で進みます。

プラグインはMCPの設定を同梱しているため、ユーザーが別途Pythonコマンドを接続設定へ手入力する必要はありません。初回だけ依存ライブラリを取得します。VOICEVOXアプリとFFmpegそのものは配布しません。

## 配布・更新

```sh
.venv/bin/python scripts/build_plugin.py
```

導入用は `dist/video-maker/`、アーカイブは `dist/video-maker.zip` です。アーカイブ内のルート直下にマニフェスト用フォルダがあります。パッケージ自体に個人素材・絶対ユーザーパス・仮想環境を埋め込みません。マーケットプレイスには、このフォルダを指すエントリを作ります。

ソースを変更した場合はパッケージを再ビルドし、個人マーケットプレイスのソースへ反映して再導入します。導入済みキャッシュを直接編集しないでください。現在の会話のツール一覧は固定される場合があるので、新しい会話で試します。

## 検証の範囲

PythonテストでMCP STDIO接続と編集処理を検証し、実機VOICEVOX＋ユーザー提供立ち絵でMP4を書き出しています。ChatGPT WorkのUI上で新規会話を開始して行う最終操作確認は、導入後の利用側で行います。CLIによるプラグイン導入の成功と、Work会話での実行成功は別の確認として扱います。
