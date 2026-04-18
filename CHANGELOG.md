# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added (toward v0.2.0)
- **banned_terms 拡張**: 13 → 26 語。新規追加は普遍カテゴリから抽出
  (process: `merge`, `rebase`, `cherry-pick`; concepts: `fingerprint`,
  `fallback`, `fixture`, `payload`, `helper`, `wrapper`; state:
  `pending`, `idle`; review: `verdict`, `blocker`)。
- **severity 三段階**: `ERROR` / `WARNING` / `INFO`。`finalize` は ERROR
  が 0 件なら `ok: true` を返し、WARNING/INFO は `advisories` で通知する。
  ERROR が 1 件でも残れば `ok: false`。修正は MUST。
- **banned_terms.yaml schema v2**: 各エントリに `severity`, `category`,
  `katakana_form` フィールドを追加。後方互換のため省略時はデフォルト値
  (`severity=ERROR`, `category=other`, `katakana_form=""`)。
- `Violation` データクラスに `severity` と `category` フィールド追加。

### Changed (toward v0.2.0)
- `agents_rule.md`: severity 階層の説明を追加。Codex は ERROR を必ず
  修正、WARNING は強く推奨、INFO は参考扱い。
- `finalize` の summary 文字列に severity 別件数を含める
  (例: `5件の違反を検出 (3 ERROR, 1 WARNING, 1 INFO)`)。
- **User-local override (rc2)**: `~/.codex/jp_lint.yaml` を置くと、
  バンドル済み `banned_terms.yaml` に対して `disable` / `overrides` /
  `add` / `thresholds` を適用できる。探索優先順位は
  `$CODEX_JP_HARNESS_USER_CONFIG` → `$XDG_CONFIG_HOME/codex-jp-harness/jp_lint.yaml`
  → `~/.codex/jp_lint.yaml`。存在しなければ無視してバンドル値を使う。
- **`codex-jp-tune` CLI (rc2)**: ユーザー設定を対話的に編集する
  console script を追加。サブコマンドは `path` / `show` / `disable` /
  `enable` / `set-severity` / `add` / `remove`。pyyaml のみ依存。

## [0.1.3] - 2026-04-18

配布安全性 patch。配布物に残っていた特定プロジェクト名・個人 Vault パスを匿名化し、markdown link 内 URL の誤検出も併せて修正。

### Security
- Sanitized test fixtures and documentation: removed project-specific
  identifiers (a previous downstream project name and several internal
  task IDs of the form TASK-NNN) and personal Obsidian Vault sub-paths.
  Fixtures now use generic placeholder names (`sample-core.ps1`,
  `my-app/src-tauri`, `TASK-101`〜`TASK-106`) that retain the same
  violation counts but carry no real-project context.
- Added `.mailmap` so `git log` displays the historical commit author as
  the project alias (raw commits on the remote remain unchanged).
- New CI workflow (`.github/workflows/sanitize.yml`) rejects any tracked
  file that reintroduces personal or project-specific strings.

### Fixed
- `bare_identifier` no longer flags the URL inside markdown links of the
  form `[text](url)`. The URL portion is now masked before identifier
  detection. The label portion is still scanned, so identifiers written
  as link text remain caught.

### Changed
- `config/agents_rule.md`: trigger description now refers to generic vault
  folders (`Notes/`, `Docs/`, `Articles/`) rather than personal-vault names.

## [0.1.2] - 2026-04-17

v0.1.0 / v0.1.1 で見過ごしていた 3 件のユーザビリティ修正。

### Changed
- **`config/agents_rule.md` をスタンドアロン形式に刷新**。v0.1.1 までは
  「`   p. ...`」形式で筆者のローカル `~/.codex/AGENTS.md` 構造（7.a〜7.o の
  番号付きリスト前提）に強く依存していた。他ユーザーの AGENTS.md に追記すると
  孤立した「p.」で始まる読めないブロックになっていた。
  新しい形式は `## 日本語技術文の品質ゲート` から始まる独立セクション
  (`##` + `###` 見出し構成)。フレッシュな AGENTS.md にも既存ルール群の
  末尾にも追記でき、個人情報や環境固有のパスは一切含まない。
- **README の「冪等」を平易な日本語に置換**。「冪等に動く」→「同じコマンドを
  何度実行しても結果は同じ（副作用が重複しない）」。技術者向け文書でも、
  日本語が読める人に自然に伝わる語を優先する方針。

### Added
- `config/banned_terms.yaml` に `冪等` を追加。自分のツールが自分のドキュメント
  の読みづらさも検出できるようになった（dogfooding）。suggest は
  「何度実行しても同じ結果、繰り返しても安全」。テスト 2 件追加で合計 30 件。

## [0.1.1] - 2026-04-17

v0.1.0 リリース同日の追従リリース。7.p トリガー範囲の拡張と、リポ固有の規約文書（AGENTS.md）を追加。

### Added
- Project-level `AGENTS.md` at repo root. Complements the global
  `~/.codex/AGENTS.md` with repo-specific context: stack, branch
  protection rules, dogfooding intent, deprecation trigger, release
  workflow. Codex and Claude Code read both when working here.
- README.md "ディレクトリ構成" section showing the cloned repo layout
  plus the `~/.codex/` files that install.ps1 / install.sh modify.
  Helps users understand what they get and what the installer touches.

### Changed
- AGENTS.md 7.p trigger scope widened from "progress reports" only to
  "all Japanese technical writing": learning notes, docs, design memos,
  release notes, release articles. File append case clarified: the
  appended chunk goes through finalize; existing body stays untouched.
  Motivated by observed bare-identifier violations in learning notes
  (narrow slice, parity, fail-close, regression, contract drift — all
  bare).

## [0.1.0] - 2026-04-17

初回公開リリース。Zenn 記事 [Codex の日本語を救ったのは「ずんだもん」だった](https://zenn.dev/sora_biz/articles/codex-jp-harness-milestone) と同日公開。

### Documented
- Zenn writeup published at
  https://zenn.dev/sora_biz/articles/codex-jp-harness-milestone
  ("Codex の日本語を救ったのは「ずんだもん」だった"). README now links
  to it as the primary narrative for the 32→0 milestone, the VOICEVOX
  register-switch hypothesis, and the prompt-layer vs runtime-layer
  tradeoffs.

### Added
- Cross-platform support. `scripts/install.sh` and `scripts/uninstall.sh`
  mirror the PowerShell scripts for macOS, Linux, and Git Bash on Windows.
  install.sh auto-converts MSYS paths to native Windows form via
  `cygpath` when running on Git Bash so Codex (non-MSYS process) can
  spawn the venv python correctly.
- README and docs/INSTALL.md now show both install paths side by side.
  pyproject.toml classifier changed to "OS Independent".
- `config/agents_rule.md` gains three post-v0.1.0 clauses to cover failure
  modes observed in a real Codex session log:
  - **Session-wide identifier rule**: code identifiers (file names, func
    names, branch names, PR numbers, task IDs, param names, commands)
    must be backtick-wrapped in every Japanese output, not only in
    report-shaped messages that trigger finalize.
  - **"Check first, then call" is banned**: Codex must call finalize
    first and fall back only on actual error. Saying "let me check if
    jp_lint is usable" is itself a forgot-to-call symptom.
  - **Ambiguous reference words are banned**: phrases like 対象テスト /
    広い確認 / 前面 / 公開面 / 一式 force the reader to guess scope.
    Replace with concrete command/module names (e.g. `cargo test -p X`).
- Test fixtures capturing the full before/after story:
  `codex_actual_output.txt` (32 violations), `codex_after_voicevox.txt`
  (4 violations), `codex_after_strengthened.txt` (0 violations).
- Sentence length rule (`sentence_too_long`): flags sentences over 80 chars
  (or 50 chars if they contain code identifiers). VOICEVOX-inspired:
  sentences that cannot be spoken aloud in one breath are usually packed
  too densely.
- AGENTS.md 7.p now includes a "imagine the user plays the response
  through VOICEVOX" directive to shift Codex's register toward natural
  speakable Japanese.
- AGENTS.md 7.p further strengthened with three enforcement clauses:
  explicit trigger condition, explicit prohibition on skipping the tool,
  and a self-check directive. This flipped Codex from 0% self-initiated
  finalize calls to a working retry loop.

### Milestone
- **32 → 0 violations** (-100%) on the same progress report prompt,
  across three progressive rule-tightening steps. No Stop hook required.
  Confirms that the prompt-layer + MCP finalize gate hybrid is sufficient
  for v0.1.0 ship.

### Fixed
- Server identity `FastMCP("jp-lint")` → `FastMCP("jp_lint")` so the
  advertised name matches the config.toml key.
- `install.ps1` now registers the repo's `.venv` python executable
  instead of relying on system `python`, which lacked `mcp[cli]` and
  `pyyaml`. The server was silently ImportError-ing on startup.

### Added
- Phase A complete: MCP server (`jp-lint`) with `finalize` tool exposing three detection rules
  - Banned term detection (12 initial terms from `banned_terms.yaml`)
  - Bare identifier detection (code-like tokens not wrapped in backticks)
  - Too-many-identifiers-per-sentence detection (default limit: 2)
  - Code blocks and inline code are excluded from detection
- `src/codex_jp_harness/rules.py` — pure-function lint engine
- `src/codex_jp_harness/server.py` — FastMCP server exposing `finalize(draft)`
- `config/banned_terms.yaml` — single source of truth for rules
- `tests/test_rules.py` — 24 passing unit tests
- `tests/fixtures/{bad,good}_samples.md` — real-world samples
- `scripts/install.ps1` — registers MCP server in `~/.codex/config.toml`
- `scripts/uninstall.ps1` — removes MCP server registration
- Phase 0 complete: Repository skeleton (README, LICENSE, CI, docs)
