# AGENTS.md — codex-jp-harness

> Codex がこのリポジトリで作業する時に参照する規約。グローバルの `~/.codex/AGENTS.md` に上書きせず、**追加の制約**として作用する。

## このリポジトリについて

`codex-jp-harness` は、OpenAI Codex（CLI / App 両対応）の日本語出力を MCP 検品ゲートで品質担保する **暫定ハーネス**。Codex CLI と Codex App は同じ Rust バイナリを共有し、`~/.codex/` 配下の設定を同じ場所から読むため、本ハーネスは両 surface に同時反映される。OpenAI が Codex 本体に日本語自然化を公式実装した時点で archive する前提で設計されている。詳細は [`docs/DEPRECATION.md`](docs/DEPRECATION.md) を参照。

## 技術スタック

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) で依存管理
- `mcp[cli]`（FastMCP パターン）で MCP サーバー実装
- `pyyaml` で設定読み込み
- `pytest` + `ruff` でテスト・Lint

## 重要ファイル

| パス | 役割 |
|---|---|
| `src/codex_jp_harness/rules.py` | Lint ロジック（純関数） |
| `src/codex_jp_harness/server.py` | FastMCP サーバー。`finalize` ツールを公開 |
| `config/banned_terms.yaml` | 禁止語・閾値の単一情報源 |
| `config/agents_rule.md` | ユーザーの `~/.codex/AGENTS.md` に追記される品質ゲート規約本文 |
| `scripts/install.{ps1,sh}` | OS 別インストーラー |
| `tests/test_rules.py` | 単体テスト 28 件 |
| `tests/fixtures/codex_*.txt` | 実 Codex 出力の before/after fixture |

## コーディング規約

- すべての lint ルールは `rules.py` の純関数として実装する（副作用なし、入力は `(text, cfg)`、出力は `list[Violation]`）
- 新しい禁止語は `config/banned_terms.yaml` の `banned` に追加する
- 新しいルールタイプを追加する場合、`rules.py` に `detect_*` 関数を追加し、`lint()` で組み合わせる
- テストは fixture ベースで記述、`tests/fixtures/` に実データを置く
- コミットメッセージは英語（Conventional Commits 準拠）
- CI は **pytest matrix（Windows / Linux × Python 3.11 / 3.12）+ gitleaks** の 5 チェック必須

## ブランチ保護

`main` は保護されている:

- PR 経由のマージ必須（approval は 0 でも可）
- CI 5 チェック全通過必須
- Linear history 必須（squash / rebase のみ）
- force push / delete 禁止
- Admin は緊急時に bypass 可

つまり、直接 `main` への push は禁止。feature branch → PR → CI → squash merge の流れを守る。

## 自分たちの dogfooding

このツール自身が日本語技術文の品質ゲートなので、**このリポで作業する Codex の日本語出力も同じルールに従う**:

- コード識別子（ファイル名・関数名・変数名・ブランチ名・PR 番号・タスク ID・パラメータ名・コマンド名）は**必ずバッククォートで囲む**
- 進捗報告・学習ノート・コミットメッセージ（内容）・PR 説明・リリースノート等は `mcp__jp_lint__finalize` を通す
- 禁止語（`slice`, `parity`, `done`, `active`, `ready`, `squash`, `dispatch`, `handoff`, `regression`, `fail-close`, `fast-forward`, `contract drift`）は使わず言い換える
- 1 文あたり識別子は 2 個まで、文字数は 80 文字（識別子含む文は 50 文字）以内
- VOICEVOX で音読される場面を想像して書く

グローバル `~/.codex/AGENTS.md` に追記された品質ゲート規約を優先する。本ファイルは**リポ固有の技術文脈**を補足する位置づけ。

## アンインストール

OpenAI が以下のいずれかを公式実装した時点で、このリポは archive する:

- Codex 本体（CLI / App 共通）での日本語 register 切替
- Pre-response hook の公式機構
- `PreSkillUse` / `PostSkillUse` hook（[Issue #17132](https://github.com/openai/codex/issues/17132)）

アンインストール手順と観測方法は [`docs/DEPRECATION.md`](docs/DEPRECATION.md) と [`docs/OPERATIONS.md`](docs/OPERATIONS.md)。

## 作業時のチェックリスト

新機能・バグ修正を始める前に:

1. `uv sync` で依存を同期
2. feature branch を切る（`main` には直 push しない）
3. 変更を入れ、`uv run pytest` と `uv run ruff check` が通ることを確認
4. 新規禁止語は `banned_terms.yaml`、新規ルールは `rules.py` + テストを追加
5. `git push -u origin <branch>` → `gh pr create`
6. CI 全通過を確認してから `gh pr merge --squash --delete-branch`
7. ユーザー向け変更なら `CHANGELOG.md` の `[Unreleased]` に追記
8. ユーザー向け影響が大きい変更なら README / docs も更新

リリース時:

1. `CHANGELOG.md` の `[Unreleased]` を `[X.Y.Z] - YYYY-MM-DD` に確定
2. `pyproject.toml` と `src/codex_jp_harness/__init__.py` の version を上げる
3. PR → merge
4. `gh release create vX.Y.Z --title "..." --notes-file ..." --target main`
