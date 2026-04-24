# インストール

## 前提条件

- macOS / Linux / Windows（Windows は PowerShell 7+ または Git Bash）
- Python 3.11 以上
- [uv](https://github.com/astral-sh/uv)（推奨）または pip
- **Codex CLI 0.120 以上**（`codex` コマンドが PATH 上で使えること）。`v0.124.0` 以降を推奨（hook が GA 化、`[features]` 宣言が不要になった）
  - 導入スクリプトは `0.120` 〜 `0.123` のため `codex features enable codex_hooks` を実行する。`0.124+` では無害の冗長実行になる
  - Codex CLI が未導入の場合、導入スクリプトは `MCP` 経由の `strict` モードに自動でフォールバックする（検品は動くが応答トークンが毎ターン増える）
- `git` が使えること
- （パターン A で自動化するなら）ログイン済みの Codex（CLI / App どちらでも可）

## モード

導入スクリプトは 3 モードから 1 つを選ぶ。`--mode` 未指定なら `codex` CLI の有無で自動判定する。

| モード | 既定？ | 仕組み | 出力トークン増分 |
|---|---|---|---|
| **`strict-lite`** | ✅（Codex CLI 検出時） | `Stop hook` がローカル検品し、`ERROR` で `{"decision":"block"}` を返して Codex が同じターン内で言い直す | 違反時のみ 1 ターン分（違反ゼロなら 0） |
| `lite` | | `Stop hook` が検品するが `block` せず記録のみ。翌セッションで再教育 | 0（`block` しない） |
| `strict` | Codex App 単独環境の既定 | `MCP` `finalize` ゲートが毎ターン下書きを検品。`fast path` で自動修正 | `+1.00×` 〜 `+2.00×` を毎ターン |

明示指定は `--mode=<name>` / `-Mode <name>`。モードは `~/.codex/state/jp-harness-mode` に 1 行のマーカーとして保存され、再導入しても尊重される。

### オン/オフの切替

導入後、アンインストールせずに一時的に無効化できる。モデル更新後（例: `GPT-5.5` 世代）のハーネス有り/無しの比較に使う。手段は 2 つ。

**CLI（ターミナル利用時）**:

```bash
ja-output-toggle status    # 現在のモード確認
ja-output-toggle off       # 無効化（応答は素通り）
ja-output-toggle on        # 再有効化（直前のモードを復元）
ja-output-toggle set lite  # モードを明示指定
```

**プロンプト（Codex App 利用時）**:

Codex App にはチャット欄しかないため、下記のプロンプトを貼って Codex に同じファイル操作を代行させる。

`off` にする:

````
ja-output-harness をオフにしてほしい。具体的には:
1. `~/.codex/state/jp-harness-mode` を読み、中身が `off` 以外なら
   その中身を `~/.codex/state/jp-harness-mode.bak` に保存する
2. `~/.codex/state/jp-harness-mode` に `off` の 1 行だけを書き込む
3. 完了後、現在のモードと直前のモード（もしあれば）を教えてほしい
````

`on` に戻す:

````
ja-output-harness をオンに戻してほしい。具体的には:
1. `~/.codex/state/jp-harness-mode.bak` を読む（無ければ `strict-lite` を使う）
2. その中身を `~/.codex/state/jp-harness-mode` に書き込む
3. 完了後、現在のモードを教えてほしい
````

`status` だけ:

````
`~/.codex/state/jp-harness-mode` と `~/.codex/state/jp-harness-mode.bak` の中身をそのまま見せて。
````

`off` のときは `Stop hook` と `SessionStart hook` の両方が冒頭で即 `exit 0` する。Codex の再起動は不要（`hook` は毎ターン `jp-harness-mode` を読み直す）。

## パターン A: 超簡易インストール（Codex に任せる）

手動コマンドを避けたい人はこちらが速い。Codex（CLI / App）に下記のプロンプトをそのまま貼り付けると、Codex が自律的に `git clone` → `uv sync` → `install.ps1` → 動作確認までを実行してくれる。

````
次のリポジトリを自分のマシンにインストールしてほしい:
https://github.com/Sora-bluesky/ja-output-harness

手順:
1. 任意のプロジェクト用ディレクトリに git clone する
   (例: Windows なら %USERPROFILE%\Projects\ など、
    macOS/Linux なら ~/src/ や ~/Projects/ など)
2. リポジトリ内で `uv sync` を実行する（uv 未インストールならインストールから）
3. OS に応じたインストールスクリプトを実行する
   - Windows (PowerShell): `pwsh scripts\install.ps1 -AppendAgentsRule`
   - macOS / Linux / Git Bash: `bash scripts/install.sh --append-agents-rule`
   （config.toml への features 登録、hooks.json 書き込み、
    AGENTS.md への品質ゲート規約追記を一括で行う。
    strict モードが選ばれたときのみ [mcp_servers.jp_lint] も追記）
4. Codex を 1 回完全に再起動し、日本語で何か応答をもらい、
   `~/.codex/state/jp-harness-lite.jsonl` に 1 行追加されていれば正常動作
   （strict モードの場合は `~/.codex/state/jp-harness-metrics.jsonl`）
5. 完了したら、Codex（CLI / App）の再起動が必要であることを私に伝える

各手順の結果を簡潔に報告しながら進めてよい。
破壊的な操作が必要になった時だけ確認して。それ以外は自律的に進めてよい。
````

完了メッセージが出たら Codex（CLI / App）を再起動し、下の「動作確認」セクションで挙動を確かめる。

## パターン B: 手動インストール

### 1. リポジトリを取得

```powershell
cd C:\Users\<username>\Projects\
git clone https://github.com/Sora-bluesky/ja-output-harness.git
cd ja-output-harness
```

### 2. 依存をインストール

```powershell
uv sync
```

### 3. Codex に登録

**macOS / Linux / Git Bash on Windows**:

```bash
bash scripts/install.sh --append-agents-rule
```

**Windows (PowerShell)**:

```powershell
pwsh scripts\install.ps1 -AppendAgentsRule
```

どちらのスクリプトも以下を自動で実行する:
- `~/.codex/config.toml` に `[features] codex_hooks = true` を書き込む（Codex `0.120` 〜 `0.123` では必須、`0.124+` では既定有効のため無害の冗長）
- `~/.codex/hooks.json` に `Stop` と `SessionStart` のエントリを書き込む（既存のユーザー `hook` は壊さずマージする）
- `~/.codex/state/jp-harness-mode` にモードを書き込む
- `strict` モードを選んだ場合のみ、`~/.codex/config.toml` に `[mcp_servers.jp_lint]` を追記する
- `--append-agents-rule` / `-AppendAgentsRule` を付けた場合、`~/.codex/AGENTS.md` にモード別の品質ゲート規約（`config/agents_rule.md` または `config/agents_rule_lite.md`）を追記する

フラグ無しで実行した場合、`AGENTS.md` は自動更新せず、警告で手動追記を促す。既存の `AGENTS.md` に独自の品質ゲート規約がある場合はこちらを推奨する。

`install.sh` は Git Bash / WSL 検出時に `cygpath` で Windows 形式のパスに自動で変換する。

### 4. Codex を再起動

`config.toml` の変更は Codex 再起動で反映される。

## 動作確認

Codex セッションを開いて日本語で何か 1 回やり取りする。そのうえで、モード別に以下を確認する:

### `strict-lite` / `lite`（既定）

`~/.codex/state/jp-harness-lite.jsonl` に 1 行追加されていれば正常動作:

```bash
# macOS / Linux
tail -1 ~/.codex/state/jp-harness-lite.jsonl

# Windows PowerShell
Get-Content -Tail 1 $env:USERPROFILE\.codex\state\jp-harness-lite.jsonl
```

`{"ok": true, "violation_count": 0, ...}` のような行が入っていれば `Stop hook` が発火している。`strict-lite` で違反を意図的に起こしたい場合は、プロンプトで `「slice という単語を入れて進捗を書いて」` と指示してみる（続けて Codex が言い直すはず）。

### `strict`

Codex で `「slice という単語を入れて進捗を書いて」` とリクエストし、`mcp__jp_lint__finalize` が内部で呼ばれて `slice` が自動置換されることを確認する。`~/.codex/state/jp-harness-metrics.jsonl` に 1 行追加されているはず。

## トラブルシューティング

### `Stop hook` が発火しない

1. `~/.codex/config.toml` に `[features] codex_hooks = true` が入っているか確認（Codex `0.124+` では省略可）
2. `~/.codex/hooks.json` に `Stop` と `SessionStart` のエントリがあるか確認
3. リポ内 `.codex/config.toml` では `hook` が発火しない（[Issue #17532](https://github.com/openai/codex/issues/17532)）。グローバル `~/.codex/config.toml` に登録する
4. Codex を完全に終了して再起動する（アプリはウィンドウを閉じるだけだと常駐することがある）

### `strict` モードで `MCP` サーバーが起動しない

```powershell
# 直接起動してエラーを確認
python C:\Users\<username>\Projects\ja-output-harness\src\ja_output_harness\server.py
```

### `strict` モードで Codex が `finalize` を呼ばない

`~/.codex/AGENTS.md` に品質ゲート規約が追記されているか確認する。手動で追記する場合は `config/agents_rule.md` の本文を使う。

## アンインストール

**macOS / Linux / Git Bash on Windows**:

```bash
bash scripts/uninstall.sh
```

**Windows (PowerShell)**:

```powershell
pwsh scripts\uninstall.ps1
```

どちらも `config.toml` から関連エントリを削除します（`AGENTS.md` の編集は手動）。
