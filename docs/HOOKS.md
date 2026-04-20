# Codex Hooks（Stop + SessionStart）

本ハーネスは MCP `finalize` ゲートを主軸としつつ、**呼び忘れ検知と次セッションでの再教育**を Codex CLI 0.120.0 以降の hook 機構で補完する。本ドキュメントでは Stop / SessionStart 両 hook の役割・仕組み・インストール手順・フォールバック挙動を解説する。

> ⚠️ **Experimental**: hook 機構は Codex CLI 0.120.0 以降のプレビュー実装。リポジトリローカルの `.codex/config.toml` では動かない既知バグ（[Issue #17532](https://github.com/openai/codex/issues/17532)）があるため、本ハーネスは**グローバル `~/.codex/hooks.json` にのみ登録**する方針を採る。

## なぜ hook が必要か

MCP `finalize` ゲートは強制力が強いが、**Codex 側が finalize を呼ぶかどうかに依存する**。`AGENTS.md` の品質ゲート規約で呼び出しを促しているが、長い会話の末端や長時間作業中に稀に呼び忘れが発生する（本リポジトリの運用実測で 1〜3% 程度）。

そこで本ハーネスは以下の後方検知ループを追加する:

1. **Stop hook**: ターン終了時、日本語応答を出したのに `finalize` を呼んだ形跡がなければ `missing-finalize` を state ファイルに記録する
2. **SessionStart hook**: 次回セッション開始時、直近の未消化エントリを読んで再教育プロンプトを stdout に注入する（最大 400 文字）

これにより「検出 → 学習 → 再注入」のループが session 間で閉じる。`finalize` 自体の強制力と組み合わせて、**同一ターン内自動修正（95%+）+ 翌セッションでの再教育（残り数%）** の二層構成が完成する。

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

**検知ロジック**:
1. `last_assistant_message` に日本語文字（ひらがな U+3040–309F / カタカナ U+30A0–30FF / 漢字 U+4E00–9FFF）が 1 文字も含まれなければ → スキップ
2. `transcript_path` が null または読み取り不能 → fail-open でスキップ（記録側で確信が持てない時は false positive を出さない）
3. transcript 内に `finalize` の文字列があれば → スキップ（呼んだ証拠あり）
4. いずれにも該当しなければ → `missing-finalize` エントリを state ファイルに追記

**Contract**:
- stdout: 空
- exit: **常に 0**（hook が session を壊さない）
- stderr: 例外時のみ 1 行書く

### SessionStart hook: `hooks/session-start-reeducate.{ps1,sh}`

**発火タイミング**: Codex CLI が起動する / `/clear` で履歴を消去する際。

**stdin 仕様**（JSON）:
```json
{ "session_id": "...", "source": "startup" | "resume" | "clear" }
```

**挙動**:
1. `source == "resume"` → スキップ（既存文脈を壊さない）
2. `~/.codex/state/jp-harness.jsonl` の末尾 20 行を読み、期限切れ（`expires <= now`）と消化済み（`consumed == true`）を除外
3. 有効エントリが 0 件 → スキップ
4. 有効エントリを `violation` 種別で集計し、上位 3 件を `(種別 (N回))、...` 形式に整形
5. 再教育プロンプトを stdout に出力（**ハードキャップ 400 文字**、MCP 応答サイズ制限の余裕込み）
6. 対象エントリに `consumed: true` を付けて state ファイルを書き戻す

**出力例**:
```
[codex-jp-harness] 前回セッションで mcp__jp_lint__finalize の呼び忘れを検出しました。内訳: missing-finalize (3回)。日本語応答を返す前に必ず finalize を呼んでください。除外は 4 パターンのみ（コード単独 / 20字以内相槌 / yes-no / 日本語なし）。迷ったら呼ぶ。
```

**Contract**:
- stdout: 再教育プロンプト（または空）
- exit: **常に 0**
- stderr: 例外時のみ 1 行書く

## state ファイル: `~/.codex/state/jp-harness.jsonl`

Stop hook が追記し、SessionStart hook が消化する JSON Lines 形式。

**1 行の例**:
```json
{"schema_version":"1","ts":"2026-04-20T14:32:07Z","session":"abc-123","violation":"missing-finalize","expires":"2026-04-21T14:32:07Z","consumed":true}
```

| フィールド | 説明 |
|---|---|
| `schema_version` | スキーマ版。破壊的変更があれば bump する |
| `ts` | UTC タイムスタンプ（ISO 8601, `Z` サフィックス） |
| `session` | 検知したセッション ID |
| `violation` | 違反種別。現状は `missing-finalize` のみ |
| `expires` | 有効期限（UTC）。デフォルト 24 時間。期限切れは SessionStart で無視される |
| `consumed` | `true` なら再教育済みで次回以降は無視 |

**退避方針**: 末尾 20 行のみ評価するため、無制限に肥大化しても挙動は安定する。手動ローテートは不要だが、定期的に `~/.codex/state/jp-harness.jsonl.bak` として退避しても良い。

## インストール（opt-in）

hook 機構は experimental のため **`--enable-hooks` / `-EnableHooks` フラグ指定時のみ**有効化する。フラグなしで install を実行した場合、従来どおり MCP 登録のみが行われる。

### Windows (PowerShell)
```powershell
pwsh scripts\install.ps1 -AppendAgentsRule -EnableHooks
```

### macOS / Linux / Git Bash
```bash
bash scripts/install.sh --append-agents-rule --enable-hooks
```

**install が行う変更**:
1. `~/.codex/config.toml` に `codex_hooks = true` を追記（既にあればスキップ）
2. `~/.codex/hooks.json` を `config/hooks.example.json` テンプレートから生成
   - `{{STOP_COMMAND}}` / `{{SESSION_START_COMMAND}}` プレースホルダーをリポジトリ内スクリプトの絶対パスで置換
3. 既存 `hooks.json` と内容が同じなら skip、差分があれば `-ForceHooks` / `--force-hooks` で上書き

**Codex バージョンゲート**: `codex --version` の結果が `0.120.0` 未満なら install は警告を出して hooks 設定をスキップする（他のインストール処理は継続）。

**idempotency**: 再実行しても副作用は重複しない。`codex_hooks = true` は 1 回だけ書かれ、`hooks.json` の差分比較もホワイトスペース無視で行う。

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

state ファイルに書くのは `session_id` / `ts` / `violation` 種別のみ。個人情報・プロジェクト固有情報は一切残さない。

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

1. **リポジトリローカル `.codex/config.toml` では動かない**（[Issue #17532](https://github.com/openai/codex/issues/17532)）。本ハーネスはグローバル `~/.codex/hooks.json` にのみ登録する。
2. **transcript に `finalize` という語が別文脈で登場すると誤スキップ**（例: ユーザーが質問で "finalize" を含めた場合）。発生頻度は低く、fail-open 方針として許容する。
3. **MCP サーバー停止時は呼び忘れ 100%** になるが、Stop hook はそれでも記録する。SessionStart hook の再教育プロンプトで `jp_lint MCP が停止していないか確認してください` に相当するメッセージが出る運用になる（将来拡張）。

## トラブルシューティング

### hook が発火しない

1. `codex --version` が 0.120.0 以上か確認
2. `~/.codex/config.toml` に `codex_hooks = true` があるか
3. `~/.codex/hooks.json` がリポジトリ内スクリプトの**絶対パス**を指しているか
4. Codex CLI を再起動したか（`hooks.json` は起動時にのみ読まれる）

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

`scripts/uninstall.ps1` / `scripts/uninstall.sh` は `config.toml` の `[mcp_servers.jp_lint]` のみ削除する。hooks については現状手動削除:

```powershell
Remove-Item $env:USERPROFILE\.codex\hooks.json -Force
# config.toml から `codex_hooks = true` 行を手動削除
```

v0.3 で uninstall スクリプトに hooks クリーンアップを追加する予定（[backlog]）。

## 参考

- [Codex CLI Hooks ドキュメント](https://github.com/openai/codex/blob/main/docs/config.md)（公式）
- [Issue #17532: repo-local hooks](https://github.com/openai/codex/issues/17532)
- [Issue #17132: PreSkillUse / PostSkillUse](https://github.com/openai/codex/issues/17132)
- `docs/ARCHITECTURE.md`: 全体設計との関係
- `docs/OPERATIONS.md`: 月次運用監視
