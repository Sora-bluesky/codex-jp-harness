# Operations

## 運用監視指標

月1回、以下を確認する。

### jp-harness-metrics.jsonl

`~/.codex/state/jp-harness-metrics.jsonl`（v0.2.9 以降、`finalize` 呼び出しのたびに server.py が 1 行追記する）:

```jsonl
{"schema_version":"1","ts":"2026-04-20T10:00:00Z","draft_chars":128,"draft_bytes":380,"violations_count":0,"severity_counts":{"ERROR":0,"WARNING":0,"INFO":0},"response_bytes":12,"elapsed_ms":1.2,"ok":true}
{"schema_version":"1","ts":"2026-04-20T10:00:03Z","draft_chars":128,"draft_bytes":380,"violations_count":2,"severity_counts":{"ERROR":1,"WARNING":1,"INFO":0},"response_bytes":190,"elapsed_ms":1.8,"ok":false}
```

集計は `ja-output-stats` CLI（`uv sync` 済みの環境で動く）で行う:

```bash
ja-output-stats path               # jsonl のパスを表示
ja-output-stats show               # draft_chars / violations / elapsed_ms の分布、ok 率、fast-path 率
ja-output-stats overhead --window 30   # 同一ターン内 retry の推定（window 秒以内を同一ターンとみなす）
ja-output-stats tail 20            # 末尾 20 行を生 JSON で表示
```

`show` の `fast-path:` 行（v0.2.17 以降）は、server-side 自動修正（`banned_term` のみの ERROR を `rewritten` で返すケース）が全呼び出しの何 % を占めたかを示す。高いほど retry 往復が削減されている。

## 候補語の発掘（v0.2.18 以降）

Codex 出力に頻出する生英語のうち、バンドル済み禁止語に入っていないものは `finalize` をすり抜けてしまう。月次でログや最近の応答から候補を抽出し、user-local override に追加する運用が推奨される。

```bash
# 最近の出力ログから頻度上位の生英語を抽出
ja-output-tune discover --file .claude/local/operator-handoff.md --top 20

# 推奨: 対話的に追加するにはスキル経由
# Codex の入力欄で `$jp-harness-tune` を選択 → 意図 6（候補抽出）を選ぶ
```

scan 対象は日本語文中の連続した英字（長さ 3 以上）。内蔵 allowlist（`API`, `HTTP`, `MCP`, `CI`, `PR` 等の標準語彙、`GitHub` / `OpenAI` 等の固有名詞）と既存 banned_term を除外する。候補語には `discover.SUGGESTION_DICT` で自動的に推奨言い換えが付与される（未登録の語は空欄、skill 経由で利用者が決める）。

`overhead` は「draft が tool 引数と最終メッセージで 2 回 output される」前提で、retry 回数から `avg output-factor = retry_rate + 2.0` を出力する。月次でこの値を記録すると、トークンコスト増分のトレンドが追える。

**ローテーション**: active file が 20 MB を超えると自動で `jp-harness-metrics.1.jsonl` に退避され、新しい active が始まる。保持世代は 1 のみなので総使用量は約 40 MB で頭打ち。`ja-output-stats` は archive と active を連結して読むため、ローテーションで履歴が失われることはない（古い archive は次回ローテーション時に上書きされる点のみ注意）。

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
| 誤検知率 | > 10% | `ja-output-tune disable <term>` で該当語を外す、または `thresholds.identifier_limit_per_sentence` / `sentence_length` の閾値を緩める |
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
