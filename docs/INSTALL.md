# インストール

## 前提条件

- Windows 11 (PowerShell 7+)
- Python 3.11 以上
- [uv](https://github.com/astral-sh/uv) （推奨）または pip
- Codex CLI がインストール済み (`~/.codex/` が存在する)
- `git` が使えること
- （パターン A で自動化するなら）ログイン済みの Codex CLI

## パターン A: 超簡易インストール（Codex に任せる）

手動コマンドを避けたい人はこちらが速い。Codex CLI に下記のプロンプトをそのまま貼り付けると、Codex が自律的に `git clone` → `uv sync` → `install.ps1` → 動作確認までを実行してくれる。

````
次のリポジトリを自分のマシンにインストールしてほしい:
https://github.com/Sora-bluesky/codex-jp-harness

手順:
1. Documents\Projects\apps\ 配下に git clone する
2. リポジトリ内で `uv sync` を実行する（uv 未インストールならインストールから）
3. `pwsh scripts\install.ps1 -AppendAgentsRule` を実行する
   （config.toml への MCP 登録と、AGENTS.md への 7.p ルール追記を一括で行う）
4. `mcp__jp_lint__finalize(draft="slice を進めた")` を呼んで ok:false が返ることを確認する
5. 完了したら、Codex CLI の再起動が必要であることを私に伝える

各手順の結果を簡潔に報告しながら進めてよい。
破壊的な操作が必要になった時だけ確認して。それ以外は自律的に進めてよい。
````

完了メッセージが出たら Codex CLI を再起動し、下の「動作確認」セクションで挙動を確かめる。

## パターン B: 手動インストール

### 1. リポジトリを取得

```powershell
cd C:\Users\<username>\Documents\Projects\apps\
git clone https://github.com/Sora-bluesky/codex-jp-harness.git
cd codex-jp-harness
```

### 2. 依存をインストール

```powershell
uv sync
```

### 3. Codex に登録

```powershell
pwsh scripts\install.ps1 -AppendAgentsRule
```

`install.ps1` は以下を自動実行:
- `~/.codex/config.toml` に `[mcp_servers.jp_lint]` を追記（既存エントリは自分のリポパスで書き直し）
- `-AppendAgentsRule` フラグ指定時: `~/.codex/AGENTS.md` に `config/agents_rule.md` の 7.p ルール本文を追記

`-AppendAgentsRule` なしで実行した場合、AGENTS.md は自動更新されず、警告メッセージで手動追記を促します。既存の AGENTS.md に独自の 7.p がある場合はこちらを推奨。

### 4. Codex を再起動

`config.toml` の変更は Codex 再起動で反映される。

## 動作確認

Codex セッションを開き、以下を入力:

```
今のタスクの進捗報告を書いて。テストとして slice という語をどこかに入れて。
```

期待される動作:
1. Codex が下書きに `slice` を含める
2. 内部で `mcp__jp_lint__finalize` を呼ぶ
3. `ok: false` が返り、`slice` 違反が指摘される
4. Codex が書き直して `限定的な変更` 等に置換
5. `ok: true` が返り、クリーン版がユーザーに表示される

## トラブルシューティング

### MCP サーバーが起動しない

```powershell
# 直接起動してエラーを確認
python C:\Users\<username>\Documents\Projects\apps\codex-jp-harness\src\codex_jp_harness\server.py
```

### Codex が finalize を呼ばない

`~/.codex/AGENTS.md` に 7.p が追記されているか確認。手動で追記する場合は `docs/ARCHITECTURE.md` のサンプルを参照。

### hook が動かない

Issue #17532 のため、リポジトリローカルの `config.toml` では hook が動かない。**グローバル `~/.codex/config.toml` にのみ登録**すること。

## アンインストール

```powershell
pwsh scripts\uninstall.ps1
```

`uninstall.ps1` は `config.toml` から関連エントリを削除する（`AGENTS.md` の編集は手動）。
