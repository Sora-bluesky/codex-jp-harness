# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
