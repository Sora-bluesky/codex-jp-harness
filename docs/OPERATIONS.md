# Operations

## 運用監視指標

月1回、以下を確認する。

### stats.json

`config/stats.json`（インストール後に自動生成）:

```json
{
  "finalize_calls_total": 1234,
  "retry_count_distribution": { "0": 980, "1": 200, "2": 40, "3": 14 },
  "violations_by_type": {
    "banned_term": 150,
    "bare_identifier": 80,
    "too_many_identifiers": 30,
    "noun_chain_no": 20
  },
  "last_updated": "2026-05-01T10:00:00+09:00"
}
```

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
