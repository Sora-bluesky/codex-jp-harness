# Developers' Guide

ja-output-harness の内部構造・カスタマイズ・運用手順のまとめ。普通に使うだけなら [README.md](README.md) で十分です。

## Architecture

```
ユーザー: 「進捗を報告して」
Codex:   日本語で応答
Stop hook: 応答文字列を local でlint
  ├─ 違反 ok  → そのまま表示
  └─ 違反 ERROR → {"decision":"block"} を emit
                  Codex が同じターン内で自己修正（1 ターン追加）

Stop hook が記録した違反は jp-harness-lite.jsonl に蓄積
SessionStart hook は次回起動時に上位ルールを Codex に再教育
```

詳細: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/HOOKS.md](docs/HOOKS.md)

## Modes

`install.{ps1,sh}` は 3 モードから 1 つを選んでインストールします。`--mode` 未指定なら `codex` CLI の有無を検出して自動選択。

| モード | 追加 output token | 違反時の挙動 | 想定 |
|---|---|---|---|
| **strict-lite**（default）| 0（ERROR 時のみ continuation 1 ターン）| Codex が同じターン内で自己修正 | 大多数のユーザー |
| strict | ~2-3× | MCP `finalize` server がターンごとに検品 | compliance 最優先、overhead 許容 |
| lite | 0 | 違反は記録のみ、翌セッションで再教育 | トークン最優先、違反検出は後追いで OK |

### Codex CLI / Codex App の扱い

- CLI: 3 モードすべて動作
- App: `strict-lite` / `lite` は Codex 0.122 の experimental feature allowlist（[app-server/src/config_api.rs:45](https://github.com/openai/codex/blob/rust-v0.122.0/codex-rs/app-server/src/config_api.rs#L45)）に `codex_hooks` が無く、hook 発火しないケースがある。install auto-detect は CLI 検出時のみ `strict-lite` を推奨、未検出時は `strict` にフォールバック。

### 明示指定

```bash
bash scripts/install.sh --mode=strict --append-agents-rule --force-hooks
pwsh scripts/install.ps1 -Mode strict -AppendAgentsRule -ForceHooks
```

既存 mode marker (`~/.codex/state/jp-harness-mode`) は優先的に尊重されるので、再インストールで勝手に mode が変わることはありません。

## Customize Rules

`config/banned_terms.yaml` がルール本体。

```yaml
banned_terms:
  - term: parity
    replacement: 整合性
    severity: ERROR
identifier_limit_per_sentence: 2
sentence_max_chars: 80
```

プロジェクト固有の上書きは `<repo>/.jp-harness-override.yaml` に配置します（same schema）。詳細: [docs/OPERATIONS.md](docs/OPERATIONS.md)

## Measurement

```bash
ja-output-stats show                         # overall distribution
ja-output-stats ab-report \
  --baseline 2026-04-14:2026-04-20 \
  --test     2026-04-21:2026-04-27           # Wilson 95% CI + ship decision
ja-output-stats tail 20                      # last 20 raw entries
```

`ab-report` は Wilson 下限で `>=70%` なら ship、`50-70%` なら要注意、`<50%` なら default 見直し、の判定を出します。`n<20` は inconclusive、`session=diag` は default で除外。

## Tests

```bash
uv sync
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
```

Windows の `.venv` path は `.venv/Scripts/python.exe`。

## Release Process

1. feature branch → PR
2. CI が全通過（scan / sanitize / test × 4）するのを確認
3. squash merge
4. `git tag -a vX.Y.Z -m "…"` → `git push origin vX.Y.Z`
5. `gh release create vX.Y.Z --notes-file .references/vX.Y.Z-notes.md`

## Further Reading

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — コンポーネント構成と hook ライフサイクル
- [docs/INSTALL.md](docs/INSTALL.md) — インストールの詳細手順とトラブル対応
- [docs/HOOKS.md](docs/HOOKS.md) — Stop hook / SessionStart hook の入出力契約
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — 運用手順、カスタマイズ、メトリクス解析
- [docs/DEPRECATION.md](docs/DEPRECATION.md) — 撤去トリガー

## Contributing

Issue / PR は [GitHub](https://github.com/Sora-bluesky/ja-output-harness) で受け付けています。

- 機能追加: PR 前に issue で方針を相談してください
- バグ修正: 再現手順と期待挙動を書いた PR を送ってください
- ルール追加: `banned_terms.yaml` の項目を増やす PR は歓迎ですが、単語の出典と「なぜ違反なのか」を本文に含めてください

## License

[MIT License](LICENSE)
