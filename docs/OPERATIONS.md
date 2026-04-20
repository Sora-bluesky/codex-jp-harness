# Operations

## 運用監視指標

月1回、以下を確認する。

### jp-harness-metrics.jsonl

`~/.codex/state/jp-harness-metrics.jsonl`（v0.2.9 以降、`finalize` 呼び出しのたびに server.py が 1 行追記する）:

```jsonl
{"schema_version":"1","ts":"2026-04-20T10:00:00Z","draft_chars":128,"draft_bytes":380,"violations_count":0,"severity_counts":{"ERROR":0,"WARNING":0,"INFO":0},"response_bytes":12,"elapsed_ms":1.2,"ok":true}
{"schema_version":"1","ts":"2026-04-20T10:00:03Z","draft_chars":128,"draft_bytes":380,"violations_count":2,"severity_counts":{"ERROR":1,"WARNING":1,"INFO":0},"response_bytes":190,"elapsed_ms":1.8,"ok":false}
```

集計は `codex-jp-stats` CLI（`uv sync` 済みの環境で動く）で行う:

```bash
codex-jp-stats path               # jsonl のパスを表示
codex-jp-stats show               # draft_chars / violations / elapsed_ms の分布と ok 率
codex-jp-stats overhead --window 30   # 同一ターン内 retry の推定（window 秒以内を同一ターンとみなす）
codex-jp-stats tail 20            # 末尾 20 行を生 JSON で表示
```

`overhead` は「draft が tool 引数と最終メッセージで 2 回 output される」前提で、retry 回数から `avg output-factor = retry_rate + 2.0` を出力する。月次でこの値を記録すると、トークンコスト増分のトレンドが追える。

### .jp-lint-violations.jsonl

`~/.codex/.jp-lint-violations.jsonl`（呼び忘れ検知時に追記）:

```jsonl
{"timestamp":"2026-04-20T15:30:00+09:00","session_id":"abc123","detected":"forgot_finalize","snippet":"..."}
```

## 閾値と対応アクション

| 指標 | 閾値 | 対応 |
|---|---|---|
| retry 率 | > 30% | 禁止語リストの `suggest` 文面を見直す、または `config/agents_rule.md` の文面を強化 |
| 呼び忘れ率 | > 5% | `config/agents_rule.md` の文面強化、または finalize 必須の明確化 |
| 誤検知率 | > 10% | `noun_chain_allowlist` 拡充、または閾値調整 |
| MCP サーバー crash | 月1回以上 | ログ確認、依存更新検討 |

## 禁止語リストの更新

`config/banned_terms.yaml` を編集:

```yaml
banned:
  - { term: <新語>, suggest: "<言い換え候補>" }
```

変更後:
1. `uv run pytest` でテスト通過を確認
2. Codex を再起動（MCP サーバーが yaml を再読込）
3. CHANGELOG.md に記載

## 公式対応の観測

本ハーネスは暫定対策。公式対応の動きを月次でチェック:

```powershell
# Issue チェック
gh search issues --repo openai/codex "japanese OR i18n"
gh issue view 17132 --repo openai/codex

# Changelog チェック
gh release list --repo openai/codex --limit 5
```

関連機能（Pre-response hook、PreSkillUse hook 等）が stable リリースされた時点で `docs/DEPRECATION.md` の手順に従い archive する。
