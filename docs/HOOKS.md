# Codex Hooks（Stop + SessionStart）

本ハーネスは Codex の `Stop hook` を強制層に据え、`SessionStart hook` で翌セッションに再教育を回す構成を主軸とする（既定の `strict-lite`）。本ドキュメントでは両 `hook` の役割・仕組み・導入手順・フォールバック挙動を解説する。Codex CLI と Codex App は同じ `codex` バイナリを共有するため、本仕様は両者に共通して適用される。

> **バージョン整合**: Codex `0.120` で experimental として公開、`v0.124.0` で GA（stable）化された（[PR #19012](https://github.com/openai/codex/pull/19012)）。`0.124+` では `[features] codex_hooks = true` の宣言が不要で、本ハーネスの導入スクリプトが書き込む宣言は無害な冗長として残る。リポ内 `.codex/config.toml` に書いた `hook` が発火しない既知バグ（[Issue #17532](https://github.com/openai/codex/issues/17532)）は `2026-04-24` 時点で未解決のため、本ハーネスは**グローバル `~/.codex/hooks.json` にのみ登録**する方針を採る。

## なぜ `hook` が必要か

モデルへの指示だけで日本語品質を強制するには、「呼び出す/呼び出さない」の判断が LLM 側に残ってしまう。`Stop hook` が Codex 公式の `{"decision":"block","reason":"..."}` を返すと、Codex 実行系が**同じターン内で言い直しを強制する**。LLM 側の判断に依存しない。

そこで本ハーネスは以下のループを敷く:

1. **`Stop hook`**: ターン終了時にローカル検品し、`ERROR` 違反があれば `{"decision":"block","reason":"..."}` を返す（`strict-lite`）。`lite` は記録のみ。`strict` は `finalize` 呼び出しの形跡が無ければ `missing-finalize` を記録する
2. **`SessionStart hook`**: 次回セッション開始時、未消化エントリを読んで再教育プロンプトを標準出力に注入する（最大 400 文字）

これで「検出 → 同一ターン内言い直し → 翌セッションで再教育」のループがセッション間で閉じる。既定の `strict-lite` では **同一ターン内で 95%+ を自動言い直し + 翌セッションで残り数 % の再教育** の二層構成が完成する。

## hook 仕様

### Stop hook: `hooks/stop-finalize-check.{ps1,sh}`

**発火タイミング**: Codex のターンが `Stop` 状態に遷移した直後（応答送信後、次ユーザー入力待ちに入る前）。

**Codex 0.120.x の stdin 仕様**（JSON）:
```json
{
  "session_id": "...",
  "turn_id": "...",
  "transcript_path": "/path/to/transcript.jsonl (or null)",
  "cwd": "/path/to/cwd",
  "hook_event_name": "Stop",
  "model": "gpt-5-codex",
  "permission_mode": "auto",
  "stop_hook_active": false,
  "last_assistant_message": "..."
}
```

**検知ロジック（モード別）**:

冒頭で `~/.codex/state/jp-harness-mode` を読み、以下に分岐する:

- **`off`**: 即 `exit 0`（ハーネスは完全に不可視）
- **`strict-lite` / `lite`**: `rules_cli --append-lite` を呼び、下書きをローカルで検品する
  1. `last_assistant_message` に日本語文字（ひらがな `U+3040`–`309F` / カタカナ `U+30A0`–`30FF` / 漢字 `U+4E00`–`9FFF`）が 1 文字も含まれなければ → スキップ
  2. 検品結果を `~/.codex/state/jp-harness-lite.jsonl` に `metrics.record_lite` 経由で追記
  3. `strict-lite` の場合、`ERROR` 違反があって `stop_hook_active == false` なら `{"decision":"block","reason":"..."}` を標準出力に書く
- **`strict`**: `finalize` の呼び忘れを検知
  1. 日本語文字が含まれなければ → スキップ
  2. `transcript_path` が `null` または読み取り不能 → 安全側でスキップ（確信が持てない時は誤検知を避ける）
  3. 会話ログ内に `finalize` の文字列があれば → スキップ（呼んだ証拠あり）
  4. いずれにも該当しなければ → `missing-finalize` エントリを `~/.codex/state/jp-harness.jsonl` に追記

**Contract**:
- 標準出力: `strict-lite` で `{"decision":"block"}` を返す場合のみ書く、他は空
- 終了コード: **常に 0**（`hook` がセッションを壊さない）
- 標準エラー: 例外時のみ 1 行書く

### SessionStart hook: `hooks/session-start-reeducate.{ps1,sh}`

**発火タイミング**: Codex（CLI / App）が起動する / `/clear` で履歴を消去する際。

**stdin 仕様**（JSON）:
```json
{ "session_id": "...", "source": "startup" | "resume" | "clear" }
```

**挙動**:
1. `source == "resume"` → スキップ（既存文脈を壊さない）
2. モード読み取り: `~/.codex/state/jp-harness-mode` が `off` なら → スキップ
3. `~/.codex/state/jp-harness.jsonl`（`strict` モードの `missing-finalize` ログ）と `~/.codex/state/jp-harness-lite.jsonl`（`strict-lite` / `lite` の違反ログ）を `jp-harness-cursor.json` のバイトオフセットから読み直す
4. 有効エントリが 0 件 → スキップ
5. 有効エントリを違反種別で集計し、上位 3 件を `(種別 (N 回)), ...` 形式に整形
6. 再教育プロンプトを標準出力に書く（**ハードキャップ 400 文字**、`MCP` 応答サイズ制限の余裕込み）
7. カーソルを atomic rename で進めて再注入を抑止する

**出力例（`strict-lite` / `lite`）**:
```
[ja-output-harness] 前回セッションで日本語応答に違反を検出しました。内訳: banned_term (5 回), bare_identifier (2 回), sentence_too_long (1 回)。応答を返す前に、禁止語の言い換えと識別子のバッククォート化、1 文 80 文字以内を意識してください。
```

**出力例（`strict`）**:
```
[ja-output-harness] 前回セッションで mcp__jp_lint__finalize の呼び忘れを検出しました。内訳: missing-finalize (3 回)。日本語応答を返す前に必ず finalize を呼んでください。除外は 4 パターンのみ（コード単独 / 20 字以内の相槌 / yes-no / 日本語なし）。迷ったら呼ぶ。
```

**Contract**:
- stdout: 再教育プロンプト（または空）
- exit: **常に 0**
- stderr: 例外時のみ 1 行書く

## state ファイル

モードによって書き込み先が分かれる。

### `~/.codex/state/jp-harness-lite.jsonl`（`strict-lite` / `lite`）

`Stop hook` の `rules_cli --append-lite` が 1 ターンごとに追記する JSON Lines。

**1 行の例**:
```json
{"schema_version":"1","ts":"2026-04-22T02:06:01Z","session":"019daea0-...","ok":false,"violation_count":2,"rule_counts":{"sentence_too_long":1,"banned_term":1},"mode":"strict-lite","expires":"2026-04-23T02:06:01Z"}
```

| フィールド | 説明 |
|---|---|
| `schema_version` | スキーマ版。破壊的変更があれば繰り上げる |
| `ts` | UTC タイムスタンプ（ISO 8601, `Z` サフィックス） |
| `session` | 検知したセッション ID |
| `ok` | 違反ゼロなら `true`、あれば `false` |
| `violation_count` | 検出した違反の総数 |
| `rule_counts` | 違反種別ごとの内訳（`banned_term` / `bare_identifier` / `sentence_too_long` 等） |
| `mode` | 検品時のモード |
| `expires` | 有効期限。期限切れは `SessionStart hook` で無視される |

### `~/.codex/state/jp-harness.jsonl`（`strict`）

`strict` モードの `Stop hook` が `missing-finalize` 呼び忘れを検出したときに追記する JSON Lines。

**1 行の例**:
```json
{"schema_version":"1","ts":"2026-04-20T14:32:07Z","session":"abc-123","violation":"missing-finalize","expires":"2026-04-21T14:32:07Z","consumed":true}
```

### `~/.codex/state/jp-harness-cursor.json`

`SessionStart hook` が上記 2 ファイルを atomic に読むためのバイトオフセット記録。

**退避方針**: `SessionStart hook` は `jp-harness-cursor.json` のオフセット以降のみ評価するため、無制限に肥大化しても挙動は安定する。`jp-harness-lite.jsonl` は 20 MB 超で自動ローテーション（`.1.jsonl` に退避）、保持世代は 1 のみなので総使用量は約 40 MB で頭打ちになる。

## 導入

`Codex CLI 0.120` 以上で導入スクリプトを実行すると、既定で `hook` が登録される。Codex `0.124+` では `codex_hooks` が GA 化されているため `[features]` 宣言は不要だが、本スクリプトは `0.120` 〜 `0.123` のため書き込む（無害の冗長）。

### Windows (PowerShell)
```powershell
pwsh scripts\install.ps1 -AppendAgentsRule
```

### macOS / Linux / Git Bash
```bash
bash scripts/install.sh --append-agents-rule
```

**導入で行う変更**:
1. `~/.codex/config.toml` に `[features] codex_hooks = true` を書き込む（既にあればスキップ、`0.124+` では冗長）
2. `~/.codex/hooks.json` を `config/hooks.example.json` テンプレートから生成し、`{{STOP_COMMAND}}` / `{{SESSION_START_COMMAND}}` をリポ内スクリプトの絶対パスで置換する
3. `~/.codex/state/jp-harness-mode` にモードを書き込む
4. `strict` モードを選んだ場合のみ `~/.codex/config.toml` に `[mcp_servers.jp_lint]` を追加する
5. 既存 `hooks.json` と内容が同じならスキップ、差分があれば `-ForceHooks` / `--force-hooks` で上書きする

**Codex バージョンゲート**: `codex --version` の結果が `0.120.0` 未満なら導入スクリプトは警告を出して `hook` 設定をスキップする（他の導入処理は継続）。

**冪等性**: 再実行しても副作用は重複しない。`codex_hooks = true` は 1 回だけ書かれ、`hooks.json` の差分比較もホワイトスペース無視で行う。

## 生成される hooks.json（Windows 例）

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [{ "type": "command", "command": "pwsh -NoProfile -File \"C:\\path\\to\\hooks\\session-start-reeducate.ps1\"", "timeout": 10 }]
      },
      {
        "matcher": "clear",
        "hooks": [{ "type": "command", "command": "pwsh -NoProfile -File \"C:\\path\\to\\hooks\\session-start-reeducate.ps1\"", "timeout": 10 }]
      }
    ],
    "Stop": [
      {
        "hooks": [{ "type": "command", "command": "pwsh -NoProfile -File \"C:\\path\\to\\hooks\\stop-finalize-check.ps1\"", "timeout": 5 }]
      }
    ]
  }
}
```

macOS / Linux では `bash "/path/to/hooks/*.sh"` 形式に置換される。

## 性能目標

`hooks/bench.{ps1,sh}` でベンチマーク可能:

```powershell
pwsh hooks\bench.ps1
```

```bash
bash hooks/bench.sh
```

| hook | 想定頻度 | 目標（script body） | 備考 |
|---|---|---|---|
| Stop | 1 ターンごと | **< 50 ms** | transcript 走査 + 条件分岐のみ。正規表現 1 回、I/O は条件次第 |
| SessionStart | 1 セッションごと | **< 100 ms** | jsonl 末尾 20 行 parse + 集計。起動時 1 回のみ |

**Windows での注意**: `pwsh -NoProfile -File` のコールドスタートが約 500 ms かかるため、`hooks/bench.ps1` の計測値（プロセス起動込み）は `WARN` 表示になるのが通常である。スクリプト本体の処理は数 ms 〜数十 ms。Codex の Stop hook はターン送信後に非同期で発火するため、体感 UX への影響はない。SessionStart hook はセッション起動時 1 回のみで、Codex 側の timeout（10 秒）に対して十分な余裕がある。

実測参考値（Windows 11 / PowerShell 7.4 / NVMe SSD）:
- Stop: mean ≈ 580 ms（うち pwsh 起動 ≈ 530 ms、本体処理 ≈ 50 ms）
- SessionStart: mean ≈ 580 ms（同）

POSIX 環境（macOS / Linux）では Python 起動がおおむね 50–100 ms で済むため目標内に収まりやすい。

## プライバシー

本 hook は以下を外部に送信しない:
- transcript の中身（検索のみ、抽出しない）
- `last_assistant_message` 本文（日本語判定のみ、保存しない）
- ユーザー名・ファイルパス（ログに書かない）

state ファイルに書くのは `session_id` / `ts` / 違反種別の集計（`rule_counts`）のみ。応答本文や個人情報・プロジェクト固有情報は一切残さない。

## フォールバック設計

すべての hook は **exit 0 保証**。想定外のエラーが起きても Codex のターンは止まらない。

| 状況 | 挙動 |
|---|---|
| stdin が空 / 不正 JSON | スキップして exit 0 |
| `transcript_path` が null | fail-open でスキップ（誤検知を避ける） |
| state ファイルの write に失敗 | stderr に 1 行書いて exit 0 |
| Python が PATH にない（`.sh` 版） | exit 0（hook なしで動作継続） |
| Codex 0.120 未満 | install 時に warn、hook 登録されない |

## 既知の制約

1. **リポ内 `.codex/config.toml` では動かない**（[Issue #17532](https://github.com/openai/codex/issues/17532)）。本ハーネスはグローバル `~/.codex/hooks.json` にのみ登録する。
2. **`strict` モードで会話ログに `finalize` という語が別文脈で登場すると誤スキップ**（例: ユーザーが質問で "finalize" を含めた場合）。発生頻度は低く、安全側の方針として許容する。
3. **`strict` モードで `MCP` サーバー停止時は呼び忘れが 100%** になるが、`Stop hook` はそれでも記録する。`SessionStart hook` の再教育プロンプトで `jp_lint MCP が停止していないか確認してください` に相当する案内が出る運用になる（将来拡張）。
4. **Codex App で `hook` が発火しない場合あり**: Codex `0.122` の実験機能許可リストに `codex_hooks` が無いビルドでは、App 単独環境で `strict-lite` / `lite` が動かないことがある。導入スクリプトは Codex CLI 未検出時に `strict` に自動でフォールバックする。

## トラブルシューティング

### `hook` が発火しない

1. `codex --version` が `0.120.0` 以上か確認（`0.124+` 推奨）
2. `~/.codex/config.toml` に `[features] codex_hooks = true` があるか（`0.124+` では省略可）
3. `~/.codex/hooks.json` がリポ内スクリプトの**絶対パス**を指しているか
4. Codex（CLI / App）を再起動したか（`hooks.json` は起動時にのみ読まれる）
5. `ja-output-toggle status` で `off` になっていないか確認（`off` なら `hook` は即終了する）

### Stop hook が日本語応答で記録してくれない（Japanese Windows）

cp932 デフォルトの Windows コンソールで hook が起動される場合、PowerShell がデフォルトの `[Console]::InputEncoding` を cp932 として読むため、Codex が UTF-8 で渡した JSON を誤デコードして `ConvertFrom-Json` が silent fail する可能性がありました。v0.2.12 で **stdin / stdout / stderr を UTF-8 に強制**する設定を `.ps1` 側に入れたため、v0.2.12 以降の利用者は影響を受けません。v0.2.6〜v0.2.11 で hook を配置した利用者は `git pull && uv sync` のみで解消します（Codex 再起動は不要、hook 起動時に毎回 UTF-8 が効きます）。

### state ファイルが更新されない

```powershell
# 手動で Stop hook を実行してみる
$payload = '{"session_id":"test","turn_id":"t1","transcript_path":null,"last_assistant_message":"これは日本語のテストです。","stop_hook_active":false}'
$payload | pwsh -NoProfile -File hooks\stop-finalize-check.ps1
Get-Content $env:USERPROFILE\.codex\state\jp-harness.jsonl -Tail 3
```

### 再教育プロンプトが出ない

```powershell
# 手動で SessionStart hook を実行してみる
'{"source":"startup"}' | pwsh -NoProfile -File hooks\session-start-reeducate.ps1
```

state ファイルに未消化エントリがあれば stdout にプロンプトが出る。出なければ `consumed: true` が付いていないか / `expires` が過去になっていないかを確認。

## アンインストール

`scripts/uninstall.ps1` / `scripts/uninstall.sh`（v0.3.4 以降）は以下を自動実行する:

1. `config.toml` の `[mcp_servers.jp_lint]` ブロックを削除（`.bak` に退避）
2. `hooks.json` 内で ja-output-harness の hook script（絶対パス、または `ja-output-harness` / `codex-jp-harness` マーカー）を参照するエントリを削除。すべて除去されて `hooks.json` が空になる場合はファイル自体を削除（`.bak` 作成）
3. `config.toml` の `codex_hooks = true` 行を削除。**ただし pruning 後に `hooks.json` に他の hook が残っている場合は触らない**（共存する他プラグインを巻き込まないため）
4. `AGENTS.md` の品質ゲート規約ブロックは**手動削除**（ユーザーが他ルールを追記している可能性があるため意図的）

### 残骸が気になる場合の手動手順

```powershell
# ~/.codex/AGENTS.md を開いて <!-- ja-output-harness --> で囲まれた範囲を削除
# 他に jp-harness を参照する残り物を確認
Select-String -Path $env:USERPROFILE\.codex\*.* -Pattern 'ja-output-harness' -AllMatches
```

```bash
grep -rl 'ja-output-harness' "$HOME/.codex" 2>/dev/null
```

## 参考

- [Codex CLI Hooks ドキュメント](https://github.com/openai/codex/blob/main/docs/config.md)（公式）
- [Issue #17532: repo-local hooks](https://github.com/openai/codex/issues/17532)
- [Issue #17132: PreSkillUse / PostSkillUse](https://github.com/openai/codex/issues/17132)
- `docs/ARCHITECTURE.md`: 全体設計との関係
- `docs/OPERATIONS.md`: 月次運用監視
