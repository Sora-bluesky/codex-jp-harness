# ja-output-harness

Codex が返すチャットの日本語を、自動で読みやすく整えるローカル検品ツール。

Codex でバイブコーディングしていると、チャット応答の日本語に英単語が裸で混ざり、技術比喩が助詞に溶け込み、1 文が長すぎる — ということが頻発します。このプロジェクトはそれを機械的に封じます。インストール後はあなたの操作は不要です。

> [!WARNING]
> **Disclaimer**
>
> 本プロジェクトは OpenAI による支援・承認・提携を受けていない**非公式のコミュニティツール**です。「Codex」「ChatGPT」等は OpenAI の商標であり、本ハーネスが検査対象とする CLI / アプリを客観的に指す目的でのみ言及しています。

## 何をするか

- Codex の日本語応答を毎回ローカルで検品する
- 違反があれば Codex にその場で自己修正させる
- 修正しきれなかった違反は次のセッション開始時に再教育する
- 追加の外部通信は一切なし、応答トークンも増えない

## 誰に向いているか

- Codex（CLI または App）でバイブコーディングしている人
- チャット応答に英単語が素のまま混ざる日本語に不満を感じている人
- プロンプトで何度注意しても直らない挙動を、仕組みで封じたい人

## 必要なもの

- Codex 0.120 以降（CLI または App）
- Python 3.11 以降 と [uv](https://docs.astral.sh/uv/)
- macOS / Linux / Windows（Windows は PowerShell 7+ または Git Bash）

## クイックスタート

### 1. インストール

```bash
git clone https://github.com/Sora-bluesky/ja-output-harness.git
cd ja-output-harness
uv sync
bash scripts/install.sh --append-agents-rule
```

Windows PowerShell の場合は最後の行を次に置き換えます:

```powershell
pwsh scripts/install.ps1 -AppendAgentsRule
```

### 2. Codex を再起動

システムトレイから完全に終了 → 起動し直します（アプリはウィンドウを閉じるだけだと常駐することがあります）。

### 3. 使う

いつも通り Codex を使うだけ。日本語応答のたびに裏で検品が走り、違反があれば Codex が自己修正します。

## 動作確認

Codex で日本語応答を 1 回もらった後、次のファイルに 1 行追加されていれば正常動作です。

```
~/.codex/state/jp-harness-lite.jsonl
```

## 何が違反として検出されるか

- **裸の英単語**: `parity` `slice` `pipeline` 等をバッククォート無しで書く
- **技術比喩の流用**: `fail-close` `fast-forward` `handoff` 等を助詞で使う
- **識別子過多**: 1 文に英語識別子を 3 個以上
- **長文**: 1 文 80 文字超（識別子を含む文では 50 文字超）
- **裸の PR / issue 番号**: `PR #123` `issue #42` 形式

ルールは [`config/banned_terms.yaml`](config/banned_terms.yaml) で追加・調整できます。

## アンインストール

```bash
bash scripts/uninstall.sh
```

PowerShell は `pwsh scripts/uninstall.ps1`。あなたが書いた AGENTS.md や他の Codex 設定には触れません。

## リンク

- **[CHANGELOG.md](CHANGELOG.md)** — 変更履歴
- **[DEVELOPERS.md](DEVELOPERS.md)** — アーキテクチャ・モード比較・カスタマイズ・ドッグフーディング
- **[解説記事（Zenn）](https://zenn.dev/sora_biz/articles/ja-output-harness-milestone)** — 設計の経緯
- **[docs/DEPRECATION.md](docs/DEPRECATION.md)** — 撤去条件（Codex 本体が公式対応したらこのリポジトリはアーカイブされます）

## License

[MIT License](LICENSE)
