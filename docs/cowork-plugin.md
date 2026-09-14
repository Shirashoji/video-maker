# Claude（Cowork / Claude Code）への導入

Video Makerは、編集Skillと**Mac上で動くローカルMCPサーバー**を1つにまとめたClaudeプラグインです。導入先によって手順が異なります。

| 使う場所 | 導入方法 | 更新方法 |
| --- | --- | --- |
| Claude Desktopの**Cowork** | `dist/video-maker.zip` をアップロード | 古いものをアンインストールして再アップロード |
| **Claude Code**（CLI・デスクトップのCodeタブ） | ローカルマーケットプレイス `dist/` を追加してインストール | `claude plugin marketplace update` → `claude plugin update` |

ChatGPTでも使う場合は [ChatGPT Workへの導入](work-plugin.md) を参照してください。同じMacなら編集データは自動で共有されます（[編集の引き継ぎ](sharing.md)）。

## 1. 前提

- **Claudeの有料プラン**（Pro / Max / Team / Enterprise）。プラグインは有料プラン限定です。
- **Macのデスクトップアプリ**。ローカルMCPはMac上で起動します。
  - クラウドで実行されるCoworkセッションでは、プラグインに同梱したstdio MCPが起動せず、Skillだけが読み込まれます（[anthropics/claude-code#87537](https://github.com/anthropics/claude-code/issues/87537)、2026年9月時点で未解決）。
- 次のツールがMacに入っていること。
  - **VOICEVOX**：アプリを起動しておく。接続先は `http://127.0.0.1:50021`。
  - **FFmpeg / ffprobe**
  - **uv**：Pythonと依存関係を自動で用意します。起動スクリプトは `~/.local/bin`、`/opt/homebrew/bin`、`/usr/local/bin` からuvを探します。

  ```sh
  brew install uv ffmpeg
  ```

- 初回起動時に、uvが依存ライブラリをダウンロードします（ネット接続が必要）。

## 2. 配布ファイルを作る

リポジトリのフォルダで実行します。

```sh
uv sync --extra dev
.venv/bin/python scripts/build_plugin.py
```

次のファイルができます。ビルドのたびに `version` が `0.1.0+build.<時刻>` に更新されるため、再導入すると新しい版として扱われます。

```text
dist/
├── video-maker.zip                   ← Coworkにアップロードするファイル
├── video-maker/                      ← プラグイン本体
├── .claude-plugin/marketplace.json   ← Claude Code用のローカルマーケットプレイス
└── .agents/plugins/marketplace.json  ← ChatGPT / Codex用のローカルマーケットプレイス
```

アーカイブには、PSD・立ち絵・動画・生成した音声・仮想環境・個人のパスは含まれません。

## 3A. Claude Cowork に導入する

1. Claude Desktopを開き、**Cowork**タブに切り替える。
2. 左サイドバーの **Customize（カスタマイズ）** → **Plugins（プラグイン）** を開く。
3. **Personal plugins（個人用プラグイン）** の **＋** から **Upload plugin（プラグインをアップロード）** を選ぶ。
4. `dist/video-maker.zip` を選ぶ。
   - アップロードできるのは **`.zip` だけ**です。`.plugin` 形式は「Upload failed」になります（[anthropics/claude-code#40414](https://github.com/anthropics/claude-code/issues/40414)）。
5. インストールされた **Video Maker** を開き、Skill（`video-editing`）とコネクタ（`video-maker`）が有効になっていることを確認する。
6. **新しいCoworkタスク**で、動作を確認する。

   > Video Makerで workspace_info と environment_status を実行して、保存先とVOICEVOXの接続を確認して。

   `workspace` に `~/Movies/VideoMaker`、`voicevox_version` にバージョン番号が返れば導入完了です。

Coworkの「Add marketplace」はGitHubなどのGitリポジトリだけを受け付けます。Macのローカルフォルダ `dist/` は指定できません。

### Coworkでの更新・削除

1. `scripts/build_plugin.py` を再実行する。
2. **Customize → Plugins** で Video Maker を開き、**Uninstall** する。
3. 新しい `dist/video-maker.zip` をアップロードする。
4. 新しいタスクで試す。

アンインストールしても、`~/Movies/VideoMaker` の素材やプロジェクトは消えません。

## 3B. Claude Code に導入する

`dist/` をローカルマーケットプレイスとして登録します。パスは実際の絶対パスに置き換えてください。

```sh
claude plugin marketplace add /Users/<you>/develop/video-maker/dist
claude plugin install video-maker@video-maker-local
```

Claude Codeの対話画面では、`/plugin marketplace add …` と `/plugin install video-maker@video-maker-local` でも同じ操作ができます。

導入後にClaude Codeを再起動すると、ツールが `mcp__plugin_video-maker_video-maker__*` として使えるようになります。

### Claude Codeでの更新

```sh
.venv/bin/python scripts/build_plugin.py
claude plugin marketplace update video-maker-local
claude plugin update video-maker@video-maker-local
```

最後のコマンドが `updated from … to …` と表示したら、Claude Codeを再起動します。

## 仕組みと保存場所

- `.mcp.json` は `${CLAUDE_PLUGIN_ROOT}/scripts/start-mcp.sh` をstdioで起動します。
  - 公開サーバー・待受ポート・APIキーは使いません。
  - ローカルMCPは、ほかのアプリと同じ権限でMac上で動きます。
- **素材とプロジェクト**：`~/Movies/VideoMaker`（`VIDEO_MAKER_WORKSPACE` で変更可）
  - プラグインのキャッシュとは別の場所なので、更新や削除で消えません。
  - ChatGPT側のVideo Makerも既定で同じ場所を使います。
- **実行環境**：`~/Library/Caches/video-maker/venv`（`VIDEO_MAKER_RUNTIME` で変更可）

## うまくいかないとき

- **ツールが表示されない**
  - プラグインとコネクタが有効か確認する。
  - 新しいタスクを開き直す。
  - クラウドセッションでないか確認する。
- **「Video Maker requires uv」と出る**：uvを入れてから、プラグインを無効化→有効化するか、アプリを再起動する。
- **VOICEVOXに接続できない**：Mac側でVOICEVOXアプリを起動する。
- **素材が見つからない**
  - Coworkのシェルは隔離された環境で動くため、`/mnt/...` などのパスはMacのパスとは別物です。
  - 素材はMacの絶対パス（例 `/Users/<you>/Movies/録画.mov`）で `import_asset` に渡してください。
- **クラウド用のカスタムコネクタに `localhost` を登録しても代わりにはなりません**：クラウド用コネクタは、インターネットから到達できるサーバーしか使えないためです。

## 検証

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/build_plugin.py
claude plugin validate dist
.venv/bin/python scripts/smoke_plugin.py dist/video-maker --workspace workspace/cowork-smoke
```

スモークテストは、同梱の起動設定からMCPに接続して次を確認します。

- 字幕付きプレビューの作成
- フレーム取得
- 書き出し
- プロジェクトのzip化と取り込み

Claude画面上でのアップロードとツール呼び出しは、手動で確認してください。

公式資料：

- [Use plugins in Claude](https://support.claude.com/en/articles/13837440-use-plugins-in-claude)
- [Install plugins (Cowork)](https://claude.com/docs/cowork/guide/plugins)
- [Plugin marketplaces (Claude Code)](https://code.claude.com/docs/en/plugin-marketplaces)
- [Plugins reference](https://code.claude.com/docs/en/plugins-reference)
