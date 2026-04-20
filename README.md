# codex-jp-harness

Codex CLI の日本語出力を強制的に品質担保するための MCP 検品ゲート + Stop / SessionStart hook ハーネス。

📝 **設計の経緯・実測データ（32→0 違反）の解説記事**: [Codex の日本語を救ったのは「ずんだもん」だった](https://zenn.dev/sora_biz/articles/codex-jp-harness-milestone)

> ⚠️ **本ツールは暫定対策です**。OpenAI が Codex CLI に日本語自然化を公式実装するまでの繋ぎとして設計されています。公式対応が出揃った時点でこのリポジトリは archive されます。詳細は [`docs/DEPRECATION.md`](docs/DEPRECATION.md) を参照してください。

## 1. なぜ存在するのか

Codex CLI の日本語出力には、日本語として読みづらい特徴が頻発します:

- 英語語順をそのまま直訳した文
- 禁止すべき英語比喩（`slice`, `parity`, `fail-close` 等）が助詞でそのまま混入
- ファイル名と一般語がバッククォートなしで混在
- 1 文に英語識別子が 7 個以上詰め込まれるケース

Codex CLI には出力前の postprocess / pre-response hook が存在しないため、ルール（`AGENTS.md`）だけでは違反が混入し続けます。本ハーネスは **MCP サーバーを「検品係」として間に噛ませ**、Codex が最終応答を出す直前に必ず通るゲートとして機能します。加えて Codex 0.120.0 以降の Stop / SessionStart hook で**呼び忘れを次セッションで再教育**する後方検知ループを持ちます。

### 主な機能

| 機能 | 検出対象 / 挙動 |
|---|---|
| 禁止語検出 | `slice`, `parity`, `done`, `active`, `ready`, `squash`, `dispatch`, `handoff`, `regression`, `fail-close`, `fast-forward`, `contract drift` |
| バッククォート抜け検出 | ファイル名・ブランチ名・パラメータ名・PR/issue 番号の裸書き |
| 1 文識別子過多検出 | 1 文に英語識別子が 3 個以上 |
| 名詞句過連続検出 | の-chain / 英語識別子連鎖 / カタカナ長連鎖 |
| 呼び忘れ検知（Stop hook） | `finalize` 未呼び出しの日本語応答を state ファイルに記録 |
| 再教育ループ（SessionStart hook） | 次回セッション起動時に再教育プロンプトを注入 |

## 2. 仕組み

```
ユーザー: 「進捗を報告して」
Codex:   （下書き作成）
Codex:   → mcp__jp_lint__finalize(draft) を呼ぶ
jp-lint: 禁止語・バッククォート抜け・識別子過多を検査
         → NG なら violations を返す
Codex:   （violations を読んで書き直し）
Codex:   → mcp__jp_lint__finalize(rewrite) 再呼び出し
jp-lint: ok:true を返す
Codex:   クリーン版のみユーザーに返す
```

**呼び忘れが起きた場合**の後方検知ループ:

```
Stop hook:         transcript に finalize が出ていなければ state に記録
SessionStart hook: 次回起動時に state を読み、再教育プロンプトを注入
```

この二層構成で、**同一ターン内自動修正（95%+）+ 翌セッションでの再教育（残り数%）** をカバーします。

- 全体像（スイスチーズモデル）: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- hook 詳細仕様と state スキーマ: [`docs/HOOKS.md`](docs/HOOKS.md)

## 3. インストール

### 対象環境

- macOS / Linux / Windows（Windows は PowerShell 7+ または Git Bash）
- Python 3.11+
- Codex CLI（`~/.codex/` が存在すること）。hooks を使う場合は **0.120.0 以上**
- [uv](https://github.com/astral-sh/uv)（推奨）または pip

### パターン A: 超簡易インストール（Codex に任せる）

下記のプロンプトを Codex CLI にそのまま貼り付けるだけで、Codex が自律的に進めます。

```
次のリポジトリを自分のマシンにインストールしてほしい:
https://github.com/Sora-bluesky/codex-jp-harness

手順:
1. 任意のプロジェクト用ディレクトリに git clone する
   (例: Windows なら %USERPROFILE%\Projects\ など、
    macOS/Linux なら ~/src/ や ~/Projects/ など)
2. リポジトリ内で `uv sync` を実行する（uv 未インストールならインストールから）
3. OS に応じたインストールスクリプトを実行する
   - Windows (PowerShell): `pwsh scripts\install.ps1 -AppendAgentsRule`
   - macOS / Linux / Git Bash: `bash scripts/install.sh --append-agents-rule`
   (Codex config.toml への MCP 登録、AGENTS.md への品質ゲート規約追記、
    jp-harness-tune skill の ~/.codex/skills/ への配置を一括で行う)
4. `mcp__jp_lint__finalize(draft="slice を進めた")` を呼んで ok:false が返ることを確認する
5. 完了したら、Codex CLI の再起動が必要であることを私に伝える

各手順の結果を簡潔に報告しながら進めてよい。
破壊的な操作が必要になった時だけ確認して。それ以外は自律的に進めてよい。
```

### パターン B: 手動インストール

**macOS / Linux / Git Bash on Windows**:

```bash
git clone https://github.com/Sora-bluesky/codex-jp-harness.git
cd codex-jp-harness
uv sync
bash scripts/install.sh --append-agents-rule
```

**Windows (PowerShell)**:

```powershell
git clone https://github.com/Sora-bluesky/codex-jp-harness.git
cd codex-jp-harness
uv sync
pwsh scripts\install.ps1 -AppendAgentsRule
```

どちらのスクリプトも `~/.codex/config.toml` に MCP サーバー登録を追記し、`~/.codex/skills/jp-harness-tune/SKILL.md` を配置します（`--skip-skill` / `-SkipSkill` で skill 配置のみ opt-out 可）。`--append-agents-rule` / `-AppendAgentsRule` 指定時は `~/.codex/AGENTS.md` にも `config/agents_rule.md` の内容を追記します。

### hooks を有効化する（opt-in, experimental）

Stop + SessionStart hook で呼び忘れの後方検知ループを有効にするには `--enable-hooks` / `-EnableHooks` を追加:

```bash
bash scripts/install.sh --append-agents-rule --enable-hooks
```

```powershell
pwsh scripts\install.ps1 -AppendAgentsRule -EnableHooks
```

これで `~/.codex/hooks.json` が生成され、`config.toml` に `codex_hooks = true` が追記されます。Codex CLI 0.120.0 未満では警告が出て hooks 設定はスキップされます（他のインストール処理は継続）。詳細と仕様は [`docs/HOOKS.md`](docs/HOOKS.md) を参照。

### インストールで変更されるユーザー環境

```
~/.codex/
├── config.toml              [mcp_servers.jp_lint] が追記される
│                            --enable-hooks 指定時は codex_hooks = true も追記
├── AGENTS.md                --append-agents-rule 指定時、品質ゲート規約が末尾に追記
├── hooks.json               --enable-hooks 指定時に生成（テンプレートから置換）
├── jp_lint.yaml             (任意・手動配置) user-local override
├── state/
│   └── jp-harness.jsonl     Stop hook の記録（自動生成、手動管理不要）
└── skills/
    └── jp-harness-tune/     install script が自動配置する対話チューニング skill
        └── SKILL.md
```

どちらのインストーラーも、既にエントリが存在する場合はスキップするか再インストール時に書き直すため、**同じコマンドを何度実行しても結果は同じ**（副作用が重複しない）。アンインストーラーで `config.toml` から関連エントリを削除できます。

### クローン後のリポジトリ構造

```
codex-jp-harness/
├── README.md / AGENTS.md / LICENSE / CHANGELOG.md / CONTRIBUTING.md
├── pyproject.toml                     mcp[cli], pyyaml, pytest, ruff
├── src/codex_jp_harness/
│   ├── server.py                      FastMCP サーバー本体（finalize ツール公開）
│   └── rules.py                       lint ロジック（純関数）
├── config/
│   ├── banned_terms.yaml              禁止語・閾値の SSoT（12 語）
│   ├── agents_rule.md                 ~/.codex/AGENTS.md に追記される品質ゲート規約
│   └── hooks.example.json             ~/.codex/hooks.json のテンプレート
├── hooks/
│   ├── stop-finalize-check.{ps1,sh}   Stop hook
│   ├── session-start-reeducate.{ps1,sh}  SessionStart hook
│   └── bench.{ps1,sh}                 hook 性能計測
├── scripts/
│   ├── install.{ps1,sh}               インストーラー
│   └── uninstall.{ps1,sh}             アンインストーラー
├── skills/jp-harness-tune/            対話チューニング skill
├── tests/                             pytest 81 件 + 実 Codex 出力 fixtures
└── docs/
    ├── ARCHITECTURE.md                設計判断（スイスチーズモデル / Tier 比較）
    ├── HOOKS.md                       hook 仕様・state スキーマ・トラブルシューティング
    ├── INSTALL.md                     詳細インストール手順
    ├── OPERATIONS.md                  運用監視・指標・公式対応の観測方法
    └── DEPRECATION.md                 公式対応時のアンインストール手順
```

## 4. 運用とチューニング

### severity 三段階の意味

各違反には severity が付与される。`finalize` は **ERROR が 0 件なら `ok:true`** を返す。

| severity | 意味 | 対応 |
|---|---|---|
| `ERROR` | 読み手に誤解を与える、または日本語として明らかに崩れている | **必ず修正**。残っていれば `ok:false` |
| `WARNING` | 避けた方が自然だが致命的ではない | 強く推奨。`advisories` で通知されるが `ok:true` は返る |
| `INFO` | 参考情報（好みの問題） | 読み流してよい |

`finalize` の summary には内訳が含まれる（例: `5件の違反を検出 (3 ERROR, 1 WARNING, 1 INFO)`）。

### User-local override — バンドル規則を自プロジェクトに合わせる

`~/.codex/jp_lint.yaml` を置くと、バンドル済みの `banned_terms.yaml` に対して追加・上書き・無効化ができる。リポジトリのコードは触らない。

**探索優先順位**:
1. `$CODEX_JP_HARNESS_USER_CONFIG`（明示指定）
2. `$XDG_CONFIG_HOME/codex-jp-harness/jp_lint.yaml`
3. `~/.codex/jp_lint.yaml`（既定）

**yaml の書き方**:

```yaml
# ~/.codex/jp_lint.yaml

# バンドル済みの禁止語を無効化（プロジェクト用語と衝突する場合など）
disable:
  - slice          # 例: データ分析で "time slice" を常用するチームでは外す

# 既存エントリの severity だけ差し替え
overrides:
  handoff:
    severity: WARNING   # ERROR → WARNING に緩める

# プロジェクト固有の禁止語を追加
add:
  - term: foobar
    suggest: "独自用語 foobar は日本語訳を使う"
    severity: ERROR
    category: project

# 閾値を上書き（任意）
thresholds:
  max_identifiers_per_sentence: 4
```

### `codex-jp-tune` — 対話的に override を編集する CLI

yaml を直接書くのが億劫なら `codex-jp-tune` を使う（`uv sync` 済みの環境で動く）。

```bash
codex-jp-tune show                              # 有効な設定を確認
codex-jp-tune path                              # override ファイルの場所を表示
codex-jp-tune disable slice                     # 一時的に無効化
codex-jp-tune enable slice                      # 戻す
codex-jp-tune set-severity handoff WARNING      # severity を差し替え
codex-jp-tune add foobar --suggest "foobar は日本語訳を使う" --severity ERROR
codex-jp-tune remove foobar
```

### Codex Skill `$jp-harness-tune`

`install.ps1` / `install.sh` は `~/.codex/skills/jp-harness-tune/SKILL.md` を自動配置します。Codex CLI の入力欄で `$` を押してスキル一覧を開き、`$jp-harness-tune` を選択します（Codex CLI のスキルは `/` ではなく `$` sigil で呼び出します）。スキルは判断支援（本当にルールを緩める必要があるか）を挟んでから `codex-jp-tune` を実行します。

**opt-out**: skill 配置が不要なら `install.ps1 -SkipSkill` / `install.sh --skip-skill` を指定してください。

再インストール時の挙動: 配置先に既存の `SKILL.md` があり、内容がバンドル版と一致していれば上書き（冪等）、カスタム編集して差分があれば上書きをスキップし stderr に警告を出します。

### 典型的な運用フロー

1. Codex が `finalize` で `ok:false` を返したら、まずはそのまま書き直しを待つ
2. 同じ語が高頻度で検出される場合、まず **その語がプロジェクト文脈で本当に避けるべきか** を判断する
3. 避けるべきなら規則のままにし、Codex 側に学習させる。プロジェクト用語として許容するなら `codex-jp-tune disable <term>` で外す
4. 逆に、プロジェクト固有の避けたい語が検出されないなら `codex-jp-tune add <term> --suggest "..."` で追加する

### 運用監視

月 1 回、以下の指標を確認:
- finalize 呼び出し回数
- retry 発生率（> 30% なら禁止語リストの見直しサイン）
- 違反種別の頻度分布
- 呼び忘れ率（> 5% なら `AGENTS.md` の強化サイン）
- （hooks 有効時）`~/.codex/state/jp-harness.jsonl` の末尾エントリ

詳細は [`docs/OPERATIONS.md`](docs/OPERATIONS.md) を参照。

## 5. 公式対応への導線

### アンインストール（公式対応時）

OpenAI が Codex CLI に以下のいずれかを公式実装した時点で、本ハーネスは役目を終えます:
- Codex CLI 本体が日本語自然化を標準装備
- Pre-response hook（出力前書き換え）の公式機構
- `PreSkillUse` / `PostSkillUse` hook（[Issue #17132](https://github.com/openai/codex/issues/17132)）の実装

アンインストール手順は [`docs/DEPRECATION.md`](docs/DEPRECATION.md) 参照。

### v0.2.0 以前の利用者へ（内部呼称の移行）

v0.2.0 以前では `config/agents_rule.md` の本文を内部で「**7.p ルール**」、severity 関連の将来拡張を「**7.q**」と呼んでいました。これらは当初の `~/.codex/AGENTS.md` の番号体系（7.a〜7.o）に由来する歴史的通称で、v0.2.1 以降は「**品質ゲート規約**」に統一しています。

- **実体への影響はなし**: `~/.codex/AGENTS.md` に「7.p」「7.q」として追記済みの内容はそのまま動作します
- **呼び名だけの変更**: 現行ドキュメントからは「7.p」「7.q」呼称を削除しました（CHANGELOG の過去エントリは歴史的記録として保持）
- **再インストール時の挙動**: `install.ps1 -AppendAgentsRule` / `install.sh --append-agents-rule` を再実行すると、新しい見出し (`## 日本語技術文の品質ゲート`) で再追記されます。旧ブロックは自動削除されないため、手動で整理してください

### 関連リンク

- Zenn 記事: [Codex の日本語を救ったのは「ずんだもん」だった](https://zenn.dev/sora_biz/articles/codex-jp-harness-milestone)（設計経緯・32→0 違反の実測・VOICEVOX 発見）
- [OpenAI Codex CLI](https://github.com/openai/codex)
- 関連 Issue: [#17132](https://github.com/openai/codex/issues/17132), [#17532](https://github.com/openai/codex/issues/17532), [#18189](https://github.com/openai/codex/issues/18189)

### ライセンス

MIT License。[LICENSE](LICENSE) 参照。
