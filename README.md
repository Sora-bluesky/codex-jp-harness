# codex-jp-harness

Codex CLI の日本語出力を強制的に品質担保するための MCP 検品ゲート + Stop hook ハーネス。

📝 **設計の経緯・実測データ（32→0 違反）の解説記事**: [Codex の日本語を救ったのは「ずんだもん」だった](https://zenn.dev/sora_biz/articles/codex-jp-harness-milestone)

> ⚠️ **本ツールは暫定対策です**。OpenAI が Codex CLI に Claude Code 水準の日本語対応を公式実装するまでの繋ぎとして設計されています。公式対応が出揃った時点でこのリポジトリは archive されます。詳細は [`docs/DEPRECATION.md`](docs/DEPRECATION.md) を参照してください。

## なぜ存在するのか

Codex CLI の日本語出力には、日本語として読みづらい特徴が頻発します:

- 英語語順をそのまま直訳した文
- 禁止すべき英語比喩（`slice`, `parity`, `fail-close` 等）が助詞でそのまま混入
- ファイル名と一般語がバッククォートなしで混在
- 1文に英語識別子が7個以上詰め込まれるケース

Codex CLI には出力前の postprocess / pre-response hook が存在しないため、ルール（`AGENTS.md`）だけでは違反が混入し続けます。本ハーネスは **MCP サーバーを「検品係」として間に噛ませ**、Codex が最終応答を出す直前に必ず通るゲートとして機能します。

## 仕組み

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

Codex が検品を呼び忘れた場合、Stop hook が検知して次セッション起動時に自動再教育プロンプトを注入します。

## 主な機能

| 機能 | 検出対象 |
|---|---|
| 禁止語検出 | `slice`, `parity`, `done`, `active`, `ready`, `squash`, `dispatch`, `handoff`, `regression`, `fail-close`, `fast-forward`, `contract drift` |
| バッククォート抜け検出 | ファイル名・ブランチ名・パラメータ名・PR/issue 番号の裸書き |
| 1文識別子過多検出 | 1文に英語識別子が3個以上 |
| 名詞句過連続検出 | の-chain / 英語識別子連鎖 / カタカナ長連鎖 |
| 呼び忘れ検知 | Codex が finalize を呼ばずに報告を出した場合の検知 |
| 再教育ループ | 呼び忘れ後、次セッション起動時に自動で再教育プロンプトを注入 |

## 対象環境

- macOS / Linux / Windows（Windows は PowerShell 7+ または Git Bash）
- Python 3.11+
- Codex CLI（`~/.codex/` が存在すること）
- [uv](https://github.com/astral-sh/uv)（推奨）または pip

## ディレクトリ構成

### クローン後のリポジトリ構造

```
codex-jp-harness/
├── README.md                  このファイル
├── AGENTS.md                  Codex/Claude Code がこのリポで作業する時の規約
├── LICENSE                    MIT
├── CHANGELOG.md               Keep a Changelog 形式
├── CONTRIBUTING.md
├── pyproject.toml             依存・ビルド設定（mcp[cli], pyyaml, pytest, ruff）
├── .gitattributes             *.sh は LF 固定、*.ps1 は CRLF 固定
├── .gitignore / .gitleaksignore
├── src/
│   └── codex_jp_harness/
│       ├── __init__.py        バージョン定義
│       ├── server.py          FastMCP サーバー本体（`finalize` ツール公開）
│       └── rules.py           Lint ロジック（純関数）
├── config/
│   ├── banned_terms.yaml      禁止語・閾値の単一情報源（12 語 + 各種閾値）
│   └── agents_rule.md         `~/.codex/AGENTS.md` に追記される品質ゲート規約本文
├── scripts/
│   ├── install.ps1            Windows PowerShell 用インストーラー
│   ├── install.sh             macOS / Linux / Git Bash 用
│   ├── uninstall.ps1
│   └── uninstall.sh
├── skills/
│   └── jp-harness-tune/       Codex CLI 用の対話チューニング skill（任意、SKILL.md）
├── tests/
│   ├── test_rules.py          単体テスト 28 件
│   └── fixtures/              実 Codex 出力の before/after
│       ├── codex_actual_output.txt        32 violations (baseline)
│       ├── codex_after_voicevox.txt        4 violations
│       ├── codex_after_strengthened.txt    0 violations
│       ├── bad_samples.md / good_samples.md
└── docs/
    ├── INSTALL.md              詳細インストール手順（パターン A / B）
    ├── ARCHITECTURE.md         設計判断・Tier 比較
    ├── OPERATIONS.md           運用監視・指標・公式対応の観測方法
    └── DEPRECATION.md          公式対応時のアンインストール手順
```

### インストールで変更されるユーザー環境

`scripts/install.ps1` / `scripts/install.sh` を実行すると、以下が書き換わる:

```
~/.codex/
├── config.toml                 [mcp_servers.jp_lint] エントリが追記される
│                               command = venv Python の絶対パス
│                               args = ["-m", "codex_jp_harness.server"]
├── AGENTS.md                   --append-agents-rule / -AppendAgentsRule 指定時、
│                               config/agents_rule.md の品質ゲート規約が末尾に追記される
├── jp_lint.yaml                (任意・手動配置) user-local override。
│                               `codex-jp-tune` で対話編集、または手で yaml を書く
└── skills/
    └── jp-harness-tune/        (任意・手動コピー) 対話チューニング skill。
        └── SKILL.md            Codex CLI から `$jp-harness-tune` で呼び出す
```

どちらのインストーラーも、既にエントリが存在する場合はスキップするか再インストール時に書き直すため、**同じコマンドを何度実行しても結果は同じ**（副作用が重複しない）。アンインストーラーで `config.toml` から関連エントリを削除できる（`AGENTS.md` は手動削除）。

## インストール

### A. 超簡易インストール（Codex に任せる）

手動でクローンや `uv sync` をやるのが億劫な人向け。下記のプロンプトを Codex CLI にそのまま貼り付けるだけでインストールが完了します。Codex が自律的に進めます。

```
次のリポジトリを自分のマシンにインストールしてほしい:
https://github.com/Sora-bluesky/codex-jp-harness

手順:
1. 任意のプロジェクト用ディレクトリに git clone する
   (例: Windows なら %USERPROFILE%\Documents\Projects\apps\ など、
    macOS/Linux なら ~/src/ や ~/Projects/ など)
2. リポジトリ内で `uv sync` を実行する（uv 未インストールならインストールから）
3. OS に応じたインストールスクリプトを実行する
   - Windows (PowerShell): `pwsh scripts\install.ps1 -AppendAgentsRule`
   - macOS / Linux / Git Bash: `bash scripts/install.sh --append-agents-rule`
   (Codex config.toml への MCP 登録と、AGENTS.md への品質ゲート規約追記を一括で行う)
4. jp-harness-tune skill を Codex ユーザースキルとして配置する
   - Windows (PowerShell):
     `New-Item -ItemType Directory -Force $HOME\.codex\skills\jp-harness-tune | Out-Null`
     `Copy-Item skills\jp-harness-tune\SKILL.md $HOME\.codex\skills\jp-harness-tune\`
   - macOS / Linux / Git Bash:
     `mkdir -p ~/.codex/skills/jp-harness-tune`
     `cp skills/jp-harness-tune/SKILL.md ~/.codex/skills/jp-harness-tune/`
   (Codex CLI の入力欄で `$` から `$jp-harness-tune` として呼び出せるようになる)
5. `mcp__jp_lint__finalize(draft="slice を進めた")` を呼んで ok:false が返ることを確認する
6. 完了したら、Codex CLI の再起動が必要であることを私に伝える

各手順の結果を簡潔に報告しながら進めてよい。
破壊的な操作が必要になった時だけ確認して。それ以外は自律的に進めてよい。
```

前提: `uv` + `git` が使える環境（macOS / Linux / Windows すべて対応）。Codex CLI がその OS で動いていれば、Codex 側が OS を判定して適切なインストールスクリプトを選びます。

### B. 手動インストール

詳細は [`docs/INSTALL.md`](docs/INSTALL.md) を参照。

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

どちらのスクリプトも `~/.codex/config.toml` に MCP サーバー登録を追記し、`--append-agents-rule` / `-AppendAgentsRule` 指定時は `~/.codex/AGENTS.md` にも `config/agents_rule.md` の内容を追記します。

## 違反検出時の対処法

`finalize` が `ok:false` を返した時、どう対応するかの指針。Codex 側は自動で書き直しに入るが、利用者側でルールを調整したいケースもある。

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

ファイルが存在しなければバンドル値がそのまま使われる。

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
# 有効な設定を確認
codex-jp-tune show

# override ファイルの場所を表示
codex-jp-tune path

# 禁止語を一時的に無効化 / 戻す
codex-jp-tune disable slice
codex-jp-tune enable slice

# severity を差し替え
codex-jp-tune set-severity handoff WARNING

# プロジェクト固有の禁止語を追加 / 削除
codex-jp-tune add foobar --suggest "foobar は日本語訳を使う" --severity ERROR
codex-jp-tune remove foobar
```

`codex-jp-tune` は pyyaml のみに依存する単独 CLI で、バンドル済み `banned_terms.yaml` には触れない。書き出し時にコメントは保持されないため、リッチな構造を残したい場合は yaml を手編集する。

### Codex Skill (任意)

Codex CLI には `~/.codex/skills/<name>/SKILL.md` を配置するとユーザースキルとして登録される仕組みがあります（スキルファイル名は `SKILL.md` 固定）。リポジトリ同梱の `skills/jp-harness-tune/SKILL.md` をその場所にコピーすると、対話的なチューニング支援が使えます。

```bash
# macOS / Linux / Git Bash
mkdir -p ~/.codex/skills/jp-harness-tune
cp skills/jp-harness-tune/SKILL.md ~/.codex/skills/jp-harness-tune/

# Windows (PowerShell)
New-Item -ItemType Directory -Force $HOME\.codex\skills\jp-harness-tune | Out-Null
Copy-Item skills\jp-harness-tune\SKILL.md $HOME\.codex\skills\jp-harness-tune\
```

配置後の構造:

```
~/.codex/
├── config.toml
├── AGENTS.md
├── jp_lint.yaml                      任意: user-local override
└── skills/
    └── jp-harness-tune/
        └── SKILL.md                  このスキル本体
```

呼び出しは Codex CLI の入力欄で `$` を押してスキル一覧を開き、`$jp-harness-tune` を選択します（Codex CLI のスキルは `/` ではなく `$` sigil で呼び出します）。スキルは判断支援（本当にルールを緩める必要があるか）を挟んでから `codex-jp-tune` を実行します。

`$CODEX_HOME` 環境変数を設定している場合は `$CODEX_HOME/skills/jp-harness-tune/` が配置先になります。

### 典型的な運用フロー

1. Codex が `finalize` で `ok:false` を返したら、まずはそのまま書き直しを待つ
2. 同じ語が高頻度で検出される場合、まず **その語がプロジェクト文脈で本当に避けるべきか** を判断する
3. 避けるべきなら規則のままにし、Codex 側に学習させる。プロジェクト用語として許容するなら `codex-jp-tune disable <term>` で外す
4. 逆に、プロジェクト固有の避けたい語が検出されないなら `codex-jp-tune add <term> --suggest "..."` で追加する

## 運用監視

詳細は [`docs/OPERATIONS.md`](docs/OPERATIONS.md) を参照。

月1回、以下の指標を確認:
- finalize 呼び出し回数
- retry 発生率（> 30% なら禁止語リストの見直しサイン）
- 違反種別の頻度分布
- 呼び忘れ率（> 5% なら AGENTS.md の強化サイン）

## 設計判断

Tier 1〜4 の比較や MCP finalize ゲート採用理由は [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) を参照。

## v0.2.0 以前の利用者へ（内部呼称の移行）

v0.2.0 以前では `config/agents_rule.md` の本文を内部で「**7.p ルール**」、severity 関連の将来拡張を「**7.q**」と呼んでいました。これらは筆者個人の `~/.codex/AGENTS.md` の番号体系（7.a〜7.o）に由来する歴史的通称で、v0.2.1 以降は「**品質ゲート規約**」に統一しています。

- **実体への影響はなし**: `~/.codex/AGENTS.md` に「7.p」「7.q」として追記済みの内容はそのまま動作します
- **呼び名だけの変更**: 現行ドキュメントからは「7.p」「7.q」呼称を削除しました（CHANGELOG の過去エントリは歴史的記録として保持）
- **再インストール時の挙動**: `install.ps1 -AppendAgentsRule` / `install.sh --append-agents-rule` を再実行すると、新しい見出し (`## 日本語技術文の品質ゲート`) で再追記されます。旧ブロックは自動削除されないため、手動で整理してください

## アンインストール（公式対応時）

OpenAI が Codex CLI に以下のいずれかを公式実装した時点で、本ハーネスは役目を終えます:
- Codex CLI 本体が Claude Code 相当の日本語自然化を標準装備
- Pre-response hook（出力前書き換え）の公式機構
- `PreSkillUse` / `PostSkillUse` hook（[Issue #17132](https://github.com/openai/codex/issues/17132)）の実装

アンインストール手順は [`docs/DEPRECATION.md`](docs/DEPRECATION.md) 参照。

## ライセンス

MIT License。[LICENSE](LICENSE) 参照。

## 関連リンク

- Zenn 記事: [Codex の日本語を救ったのは「ずんだもん」だった](https://zenn.dev/sora_biz/articles/codex-jp-harness-milestone)（設計経緯・32→0 違反の実測・VOICEVOX 発見）
- [OpenAI Codex CLI](https://github.com/openai/codex)
- 関連 Issue: [#17132](https://github.com/openai/codex/issues/17132), [#17532](https://github.com/openai/codex/issues/17532), [#18189](https://github.com/openai/codex/issues/18189)
