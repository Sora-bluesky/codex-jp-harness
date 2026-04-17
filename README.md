# codex-jp-harness

Codex CLI の日本語出力を強制的に品質担保するための MCP 検品ゲート + Stop hook ハーネス。

> ⚠️ **本ツールは暫定対策です**。OpenAI が Codex CLI に Claude Code 水準の日本語対応を公式実装するまでの繋ぎとして設計されています。公式対応が出揃った時点でこのリポジトリは archive されます。詳細は [`docs/DEPRECATION.md`](docs/DEPRECATION.md) を参照してください。

## なぜ存在するのか

Codex CLI の日本語出力には、日本語として読みづらい特徴が頻発します:

- 英語語順をそのまま直訳した文
- 禁止すべき英語比喩（`slice`, `parity`, `fail-close` 等）が助詞でそのまま混入
- ファイル名と一般語がバッククォートなしで混在
- 1文に英語識別子が7個以上詰め込まれるケース

Codex CLI には出力前の postprocess / pre-response hook が存在しないため、ルール（`AGENTS.md`）だけでは違反が混入し続けます。本ハーネスは **MCP サーバーを「検品係」として間に噛ませ**、Codex が最終応答を出す直前に必ず通るゲートとして機能します。

## 仕組み

```
ユーザー: 「進捗を報告して」
Codex:   （下書き作成）
Codex:   → mcp__jp_lint__finalize(draft) を呼ぶ
jp-lint: 禁止語・バッククォート抜け・識別子過多を検査
         → NG なら violations を返す
Codex:   （violations を読んで書き直し）
Codex:   → mcp__jp_lint__finalize(rewrite) 再呼び出し
jp-lint: ok:true を返す
Codex:   クリーン版のみユーザーに返す
```

Codex が検品を呼び忘れた場合、Stop hook が検知して次セッション起動時に自動再教育プロンプトを注入します。

## 主な機能

| 機能 | 検出対象 |
|---|---|
| 禁止語検出 | `slice`, `parity`, `done`, `active`, `ready`, `squash`, `dispatch`, `handoff`, `regression`, `fail-close`, `fast-forward`, `contract drift` |
| バッククォート抜け検出 | ファイル名・ブランチ名・パラメータ名・PR/issue 番号の裸書き |
| 1文識別子過多検出 | 1文に英語識別子が3個以上 |
| 名詞句過連続検出 | の-chain / 英語識別子連鎖 / カタカナ長連鎖 |
| 呼び忘れ検知 | Codex が finalize を呼ばずに報告を出した場合の検知 |
| 再教育ループ | 呼び忘れ後、次セッション起動時に自動で再教育プロンプトを注入 |

## 対象環境

- macOS / Linux / Windows（Windows は PowerShell 7+ または Git Bash）
- Python 3.11+
- Codex CLI（`~/.codex/` が存在すること）
- [uv](https://github.com/astral-sh/uv)（推奨）または pip

## インストール

### A. 超簡易インストール（Codex に任せる）

手動でクローンや `uv sync` をやるのが億劫な人向け。下記のプロンプトを Codex CLI にそのまま貼り付けるだけでインストールが完了します。Codex が自律的に進めます。

```
次のリポジトリを自分のマシンにインストールしてほしい:
https://github.com/Sora-bluesky/codex-jp-harness

手順:
1. 任意のプロジェクト用ディレクトリに git clone する
   (例: Windows なら %USERPROFILE%\Documents\Projects\apps\ など、
    macOS/Linux なら ~/src/ や ~/Projects/ など)
2. リポジトリ内で `uv sync` を実行する（uv 未インストールならインストールから）
3. OS に応じたインストールスクリプトを実行する
   - Windows (PowerShell): `pwsh scripts\install.ps1 -AppendAgentsRule`
   - macOS / Linux / Git Bash: `bash scripts/install.sh --append-agents-rule`
   (Codex config.toml への MCP 登録と、AGENTS.md への 7.p ルール追記を一括で行う)
4. `mcp__jp_lint__finalize(draft="slice を進めた")` を呼んで ok:false が返ることを確認する
5. 完了したら、Codex CLI の再起動が必要であることを私に伝える

各手順の結果を簡潔に報告しながら進めてよい。
破壊的な操作が必要になった時だけ確認して。それ以外は自律的に進めてよい。
```

前提: `uv` + `git` が使える環境（macOS / Linux / Windows すべて対応）。Codex CLI がその OS で動いていれば、Codex 側が OS を判定して適切なインストールスクリプトを選びます。

### B. 手動インストール

詳細は [`docs/INSTALL.md`](docs/INSTALL.md) を参照。

**macOS / Linux / Git Bash on Windows**:

```bash
git clone https://github.com/Sora-bluesky/codex-jp-harness.git
cd codex-jp-harness
uv sync
bash scripts/install.sh --append-agents-rule
```

**Windows (PowerShell)**:

```powershell
git clone https://github.com/Sora-bluesky/codex-jp-harness.git
cd codex-jp-harness
uv sync
pwsh scripts\install.ps1 -AppendAgentsRule
```

どちらのスクリプトも `~/.codex/config.toml` に MCP サーバー登録を追記し、`--append-agents-rule` / `-AppendAgentsRule` 指定時は `~/.codex/AGENTS.md` にも `config/agents_rule.md` の内容を追記します。

## 運用監視

詳細は [`docs/OPERATIONS.md`](docs/OPERATIONS.md) を参照。

月1回、以下の指標を確認:
- finalize 呼び出し回数
- retry 発生率（> 30% なら禁止語リストの見直しサイン）
- 違反種別の頻度分布
- 呼び忘れ率（> 5% なら AGENTS.md の強化サイン）

## 設計判断

Tier 1〜4 の比較や MCP finalize ゲート採用理由は [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) を参照。

## 撤去（公式対応時）

OpenAI が Codex CLI に以下のいずれかを公式実装した時点で、本ハーネスは役目を終えます:
- Codex CLI 本体が Claude Code 相当の日本語自然化を標準装備
- Pre-response hook（出力前書き換え）の公式機構
- `PreSkillUse` / `PostSkillUse` hook（[Issue #17132](https://github.com/openai/codex/issues/17132)）の実装

撤去手順は [`docs/DEPRECATION.md`](docs/DEPRECATION.md) 参照。

## ライセンス

MIT License。[LICENSE](LICENSE) 参照。

## 関連リンク

- Zenn 記事（公開後にリンク追加予定）
- [OpenAI Codex CLI](https://github.com/openai/codex)
- 関連 Issue: [#17132](https://github.com/openai/codex/issues/17132), [#17532](https://github.com/openai/codex/issues/17532), [#18189](https://github.com/openai/codex/issues/18189)
