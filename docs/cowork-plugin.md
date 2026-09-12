# Claude Coworkへの導入

MacのClaude Desktopで使うVideo Makerです。`.claude-plugin/plugin.json`、編集Skill、ローカルMCP、Pythonコードと依存関係ロックを同梱しています。既存のCodex用定義も維持しています。

## インストール

1. Macに `uv`、`ffmpeg`、`ffprobe` を用意し、VOICEVOXを起動します。
2. `.venv/bin/python scripts/build_plugin.py` で配布ファイルを作ります。
3. Claude Desktopの「カスタマイズ」→「プラグイン」でファイルのアップロードを選び、`dist/video-maker.plugin` を指定します。ZIPを求められる場合は同じ内容の `dist/video-maker.zip` を指定します。
4. Video Makerを有効にし、新しいCoworkタスクで以下を依頼します。

> Video Makerでworkspace_infoとenvironment_statusを実行して、素材の保存先とVOICEVOXの接続を確認して。続けて、指定する録画から字幕・口パク付きの解説動画を作りたい。

素材は既定で `~/Movies/VideoMaker` に保存されます。`import_asset` にMac上の素材の絶対パスを渡すと、原本を残して取り込みます。実際の場所は `workspace_info` の応答で確認します。

## 接続と実行環境

同梱 `.mcp.json` は `${CLAUDE_PLUGIN_ROOT}/scripts/start-mcp.sh` をSTDIOで起動します。公開サーバーやAPIキーは不要です。初回はuvが依存関係を取得します。VOICEVOXとFFmpeg自体は同梱しません。

CoworkのシェルとMac上のローカルMCPは別環境の場合があります。素材と成果物の操作はMCPを優先し、Cowork側の `/mnt/...` をMacのパスとして渡さないでください。ツールが表示されなければ、プラグインの有効状態と起動エラーを確認します。`uv` が見つからない場合はMacに導入してから再接続します。VOICEVOXへの接続失敗時はMac側でアプリの起動を確認します。クラウド用カスタムコネクタに `localhost` を登録しても代用できません。

## 検証

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/build_plugin.py
.venv/bin/python scripts/smoke_plugin.py dist/video-maker --workspace workspace/cowork-smoke
```

スモークテストは同梱の起動設定からMCPに接続し、日本語字幕付きプレビューとフレーム取得を確認します。Claude UIでの導入・ツール呼び出しは別途確認が必要です。

公式資料: [Claudeのプラグイン導入](https://support.claude.com/en/articles/13837440-use-plugins-in-claude)、[プラグイン形式とローカルMCP](https://code.claude.com/docs/en/plugins-reference)。
