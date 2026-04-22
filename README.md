# ja-output-harness

Codex のフック（Stop / SessionStart）を使って、チャット応答の日本語を自動で検品・修正するハーネスです。

Codex でバイブコーディングしていると、チャット応答の日本語に英単語が裸で混ざり、技術比喩が助詞に溶け込み、1 文が長すぎる — ということが頻発します。このプロジェクトはそれを機械的に封じます。インストール後の追加操作は不要です。

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

## 何が違反として検出されるか

- **裸の英単語**: `parity` `slice` `pipeline` 等をバッククォート無しで書く
- **技術比喩の流用**: `fail-close` `fast-forward` `handoff` 等を助詞で使う
- **識別子過多**: 1 文に英語識別子を 3 個以上
- **長文**: 1 文 80 文字超（識別子を含む文では 50 文字超）
- **裸の PR / issue 番号**: `PR #123` `issue #42` 形式

ルールは [`config/banned_terms.yaml`](config/banned_terms.yaml) で追加・調整できます。

## よくある質問

**トークン消費は増えますか?**
基本は増えません。検品は Codex の外側でローカル実行されるため、応答トークンには 1 byte も足しません。違反が検出されたときだけ Codex が同じターン内で 1 回追加で動きます（実測で +15% 程度）。

**コードや会話内容が外部に送信されたりしますか?**
しません。検品は完全にローカルで実行されます。外部通信は一切ありません。

**既存の AGENTS.md や config.toml に影響しますか?**
管理ブロックを明示的に区切って追記するだけで、既存のルールや設定には一切触れません。アンインストール時も同じブロックだけを削除します。

**合わないルールがあります**
[`config/banned_terms.yaml`](config/banned_terms.yaml) を編集して追加・削除・severity の調整ができます。プロジェクトごとの上書きも可能です（詳細は [DEVELOPERS.md](DEVELOPERS.md)）。

**「違反ありでもそのまま返してほしい」時は?**
プロンプトに「検品不要」「このまま返答」などと指示すれば Codex がスキップします。強制ではない設計です。

**動作確認はどうすれば?**
Codex で日本語応答を 1 回もらった後、`~/.codex/state/jp-harness-lite.jsonl` に 1 行追加されていれば正常動作です。

**自動修正が本当に機能しているか確認するには?**
違反が検出されると、Codex は同じターン内で自動で言い直します（strict-lite モードの挙動）。`jp-harness-lite.jsonl` の同じ `session` の連続エントリで、`ok: false` → 十数秒後に `ok: true` が続いていれば、修正ループが成立している証拠です。実例:

```jsonl
{"ts":"2026-04-22T02:06:01Z","session":"019daea0-…","ok":false,"violation_count":2,"rule_counts":{"sentence_too_long":1,"banned_term":1},"mode":"strict-lite", ...}
{"ts":"2026-04-22T02:06:17Z","session":"019daea0-…","ok":true,"violation_count":0,"rule_counts":{},"mode":"strict-lite", ...}
```

16 秒差で `ok: true` に遷移しているのは、最初の応答で違反 2 件を検出 → Codex が自動 continuation で言い直し → クリーンな応答で確定、の流れを意味します。

**動かないときは?**
Codex を完全に終了して再起動してください。config.toml や hooks.json は起動時にしか読まれません。それでもダメなら [DEVELOPERS.md](DEVELOPERS.md) の troubleshooting を参照してください。

## アンインストール

```bash
bash scripts/uninstall.sh
```

PowerShell は `pwsh scripts/uninstall.ps1`。既存の AGENTS.md や Codex 設定には触れません。

## リンク

- **[CHANGELOG.md](CHANGELOG.md)** — 変更履歴
- **[DEVELOPERS.md](DEVELOPERS.md)** — アーキテクチャ・モード比較・カスタマイズ・ドッグフーディング
- **[解説記事（Zenn）](https://zenn.dev/sora_biz/articles/ja-output-harness-milestone)** — 設計の経緯
- **[docs/DEPRECATION.md](docs/DEPRECATION.md)** — プロジェクトのアーカイブ条件（Codex 本体が日本語自然化を公式実装したら役目を終えます）

## License

[MIT License](LICENSE)
