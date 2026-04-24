# Operations

## 運用監視指標

月1回、以下を確認する。

### `jp-harness-metrics.jsonl`（`strict` モード）

`~/.codex/state/jp-harness-metrics.jsonl`。`strict` モードの `MCP` `finalize` 呼び出しのたびに `server.py` が `metrics.record` 経由で 1 行追記する。

```jsonl
{"schema_version":"1","ts":"2026-04-20T10:00:00Z","draft_chars":128,"draft_bytes":380,"violations_count":0,"severity_counts":{"ERROR":0,"WARNING":0,"INFO":0},"response_bytes":12,"elapsed_ms":1.2,"ok":true}
{"schema_version":"1","ts":"2026-04-20T10:00:03Z","draft_chars":128,"draft_bytes":380,"violations_count":2,"severity_counts":{"ERROR":1,"WARNING":1,"INFO":0},"response_bytes":190,"elapsed_ms":1.8,"ok":false}
```

### `jp-harness-lite.jsonl`（`strict-lite` / `lite`）

`~/.codex/state/jp-harness-lite.jsonl`。`Stop hook` 経由の `rules_cli --append-lite` が `metrics.record_lite` を呼んで 1 行追記する（`v0.4.2` 以降、`_rotate_lock` で競合を避ける）。

```jsonl
{"schema_version":"1","ts":"2026-04-22T02:06:01Z","session":"019daea0-...","ok":false,"violation_count":2,"rule_counts":{"sentence_too_long":1,"banned_term":1},"mode":"strict-lite","expires":"2026-04-23T02:06:01Z"}
{"schema_version":"1","ts":"2026-04-22T02:06:17Z","session":"019daea0-...","ok":true,"violation_count":0,"rule_counts":{},"mode":"strict-lite","expires":"2026-04-23T02:06:17Z"}
```

同じセッション ID で `ok:false` → `ok:true` が 十数秒差で並んでいれば、`strict-lite` の言い直しループが成立している証拠。

### 集計 CLI

`ja-output-stats`（`uv sync` 済みの環境で動く）でまとめて読む:

```bash
ja-output-stats path                 # jsonl のパスを表示
ja-output-stats show                 # 下書き文字数 / 違反数 / 経過ミリ秒の分布、ok 率、fast-path 率
ja-output-stats overhead --window 30 # 同一ターン内 retry 推定（strict 向け）
ja-output-stats tail 20              # 末尾 20 行を生 JSON で表示
ja-output-stats ab-report \
  --baseline 2026-04-14:2026-04-20 \
  --test     2026-04-21:2026-04-27   # Wilson 95% 下限で ship 判定
```

`ab-report` は `ja-output-toggle off` / `on` で切替えた窓を渡せば、ハーネス有り/無しの Wilson 下限比較を出す。`>=70%` なら ship、`50-70%` なら要注意、`<50%` なら default 見直しの判定。

### 素のモデルとの比較（`scan-sessions` + `--source-path`）

`ja-output-toggle off` は `hook` だけを止めるので、`~/.codex/AGENTS.md` の品質ゲート規約はまだ効いている（モデルが規約を読んで整えた応答を返す）。素のモデルを測るには `ja-output-toggle off --full` で規約ごと退避してから、`scan-sessions` で会話ログから後付けで違反率を計測する。

```bash
ja-output-toggle off --full            # モード + AGENTS.md 退避、Codex 再起動
# ...素のモデルで使う...
ja-output-stats scan-sessions \
  --since 2026-04-24T19:00 \
  --until 2026-04-24T19:30 \
  --output-jsonl raw.jsonl             # lite jsonl 互換で書き出す

ja-output-toggle on --full             # 戻す、Codex 再起動
# ...ハーネスありで使う...

ja-output-stats ab-report \
  --baseline 2026-04-24:2026-04-24 \
  --test     2026-04-24:2026-04-24 \
  --source-path raw.jsonl              # 素のモデル側を raw.jsonl で差し替え
```

`scan-sessions` は `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` を走査し、`role=assistant` の `output_text` を日本語判定してから `rules.py` で検品する。応答本文は保存せず、`session_id` / `ts` / 違反の集計だけを `--output-jsonl` に書き出す。

`show` の `fast-path:` 行は `strict` モード時のサーバー側自動修正の割合を示す（`banned_term` のみの `ERROR` を `rewritten` で返すケース）。高いほど再試行の往復が削減されている。

## 候補語の発掘（v0.2.18 以降）

Codex 出力に頻出する生英語のうち、バンドル済み禁止語に入っていないものは `finalize` をすり抜けてしまう。月次でログや最近の応答から候補を抽出し、user-local override に追加する運用が推奨される。

```bash
# 最近の出力ログから頻度上位の生英語を抽出
ja-output-tune discover --file .claude/local/operator-handoff.md --top 20

# 推奨: 対話的に追加するにはスキル経由
# Codex の入力欄で `$jp-harness-tune` を選択 → 意図 6（候補抽出）を選ぶ
```

scan 対象は日本語文中の連続した英字（長さ 3 以上）。内蔵 allowlist（`API`, `HTTP`, `MCP`, `CI`, `PR` 等の標準語彙、`GitHub` / `OpenAI` 等の固有名詞）と既存 banned_term を除外する。候補語には `discover.SUGGESTION_DICT` で自動的に推奨言い換えが付与される（未登録の語は空欄、skill 経由で利用者が決める）。

`overhead` は `strict` モードの「下書きが呼び出し引数と最終メッセージで 2 回出力される」前提で、再試行回数から `出力係数平均 = 再試行率 + 2.0` を出力する。月次でこの値を記録するとトークンコスト増分のトレンドが追える（`strict-lite` / `lite` には適用外）。

**ローテーション**: どちらの `.jsonl` も `active` が 20 MB を超えると自動で `.1.jsonl` に退避され、新しい `active` が始まる。保持世代は 1 のみなので総使用量は約 40 MB で頭打ち。`ja-output-stats` は退避側と `active` を連結して読むため、ローテーションで履歴が失われることはない（古い退避は次回ローテーション時に上書きされる点のみ注意）。

## 閾値と対応アクション

| 指標 | モード | 閾値 | 対応 |
|---|---|---|---|
| 初手 ok 率（`jp-harness-lite.jsonl` の `ok=true` 比率） | `strict-lite` / `lite` | `< 30%` | `banned_terms.yaml` の追加候補が多い兆候。`ja-output-tune discover` で候補抽出、または `config/agents_rule_lite.md` の文面強化 |
| 再試行率（`ja-output-stats overhead`） | `strict` | `> 30%` | 禁止語の `suggest` 文面を見直す、または `config/agents_rule.md` の文面を強化 |
| 呼び忘れ率（`jp-harness.jsonl` の `missing-finalize` 比率） | `strict` | `> 5%` | `config/agents_rule.md` の文面強化、または `finalize` 必須の明確化 |
| 誤検知率（ユーザー目視） | 全モード | `> 10%` | `ja-output-tune disable <term>` で該当語を外す、または `identifier_limit_per_sentence` / `sentence_max_chars` の閾値を緩める |
| `MCP` サーバー crash | `strict` | 月 1 回以上 | ログ確認、依存更新を検討 |

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
