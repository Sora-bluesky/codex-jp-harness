# codex-jp-harness

Codex が日本語で書く報告・ドキュメント・記事を、最終応答の直前で自動検品するための Python パッケージです。Codex の返答を間で読む MCP サーバー（`finalize` ツール）を主体とし、呼び忘れを拾う 2 種類のフックで補完します。Codex CLI / Codex App の両方で動きます。

> ℹ️ **対応範囲**: 本ハーネスは **Codex CLI（`openai/codex` の Rust バイナリ）と Codex App（macOS / Windows のデスクトップ版）の両方**に適用されます。両者は内部的に同じ `codex` バイナリを共有し、`~/.codex/config.toml` / `~/.codex/AGENTS.md` / `~/.codex/hooks.json` を同じ場所から読むため、本ハーネスのインストールは両方の利用形態に同時に反映されます（dogfooding は Codex App で実施）。

📝 **設計の経緯・実測データ（32→0 違反）の解説記事**: [Codex の日本語を救ったのは「ずんだもん」だった](https://zenn.dev/sora_biz/articles/codex-jp-harness-milestone)

> ⚠️ **本ツールは暫定対策です**。OpenAI が Codex 本体に日本語自然化を公式実装するまでの繋ぎとして設計されています。公式対応が出揃った時点でこのリポジトリは archive されます。詳細は [`docs/DEPRECATION.md`](docs/DEPRECATION.md) を参照してください。

## 1. なぜ存在するのか

Codex の日本語出力には、日本語として読みづらい特徴が頻発します:

- 英語語順をそのまま直訳した文
- 禁止すべき英語比喩（`slice`, `parity`, `fail-close` 等）が助詞でそのまま混入
- ファイル名と一般語がバッククォートなしで混在
- 1 文に英語識別子が 7 個以上詰め込まれるケース

Codex には出力前のフック（postprocess、つまり最終応答の直前に文字列を書き換える機構）が公式には存在しないため、ルール（`AGENTS.md`）だけでは違反が混入し続けます。本ハーネスは **MCP サーバーを「検品係」として間に挟み**、Codex が最終応答を出す直前に必ず通るゲートとして機能します。加えて Codex 0.120.0 以降の Stop / SessionStart フックで**呼び忘れを次セッションで再教育**する後方検知ループを持ちます（CLI / App どちらでも同じフックが動きます）。

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

この二層構成で、**同一ターン内での自動修正（95%+）と、翌セッションでの再教育（残り数%）** をカバーします。

- 全体像（スイスチーズモデル）: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- hook 詳細仕様と state スキーマ: [`docs/HOOKS.md`](docs/HOOKS.md)

## 3. インストール

### 対象環境

- macOS / Linux / Windows（Windows は PowerShell 7+ または Git Bash）
- Python 3.11+
- Codex CLI または Codex App がインストール済み（`~/.codex/` が存在すること）。hooks を使う場合は **Codex 0.120.0 以上**
- [uv](https://github.com/astral-sh/uv)（推奨）または pip

### パターン A: 超簡易インストール（Codex に任せる）

下記のプロンプトを Codex（CLI / App どちらでも）にそのまま貼り付けるだけで、Codex が自律的に進めます。

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
5. 完了したら、Codex（CLI または App）の再起動が必要であることを私に伝える

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

これで `~/.codex/hooks.json` が生成され、`config.toml` に `codex_hooks = true` が追記されます。Codex 0.120.0 未満では警告が出て hooks 設定はスキップされます（他のインストール処理は継続）。詳細と仕様は [`docs/HOOKS.md`](docs/HOOKS.md) を参照。

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

どちらのインストーラーも、既にエントリが存在する場合はスキップするか再インストール時に書き直すため、**同じコマンドを何度実行しても結果は同じ**（副作用が重複しない）。`scripts/uninstall.ps1` / `scripts/uninstall.sh` で `config.toml` から `[mcp_servers.jp_lint]` セクションを削除できます（`AGENTS.md` は手動削除）。

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

### severity（重要度）の三段階

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
codex-jp-tune discover --file <path>            # Codex 出力から候補を抽出（v0.2.18+）
```

### 候補の発掘（discover）

Codex の実際の出力には、バンドル済み禁止語に含まれない生英語（`preview` / `review` / `iframe` / `composer` / `overlay` / `context` / `drawer` など）が頻繁に混ざります。手動で 1 語ずつ追加するのは大変なので、`codex-jp-tune discover` が **貼ったドラフトから未登録の候補を頻度順で抽出**します。

#### 推奨フロー（スキル経由、対話的）

プロジェクトに馴染む語を対話で絞って登録するなら、Codex App / Codex CLI からスキルを呼ぶのが一番早いです。

1. **Codex の入力欄で `$` を押す** → スキル一覧が開く（Codex のスキルは `/` ではなく `$` 記号で呼び出す仕様）
2. **`$jp-harness-tune` を選ぶ**（対象語が先に決まっていれば続けて自然文で書いてよい。例: `$jp-harness-tune 最近の出力から禁止語候補を抽出したい`）
3. スキルが意図を確認してくるので **「6. 候補抽出（discover）」** を選ぶ
4. スキルの指示に従って **最近の Codex 応答を貼る**（paste）か、**ファイルパスを指定する**（例: `.claude/local/operator-handoff.md`）
5. スキルが頻度上位の候補を TSV で提示する
6. **1 語ずつ次を答える**:
   - 追加するか（Y/N）— UI ラベルや製品名（`Back to Code`, `Ports` など）は N
   - 推奨言い換え — スキルが自動提案する日本語を採用するか、別案を書く
   - severity — 一般名詞は `ERROR`、業界カタカナ語なら `WARNING` で充分な場合もある
7. 合意のたびにスキルが `codex-jp-tune add <term> --suggest "..." --severity ERROR` を実行する
8. 最後に `codex-jp-tune show` で反映を確認。取り消したい語があれば `codex-jp-tune remove <term>`

Codex の再起動は不要。MCP サーバーは override を毎回読み直します。次の `finalize` 呼び出しから追加した語が ERROR として検出され、fast-path で自動修正されます。

#### CLI 単体（スクリプト / バッチで使う場合）

```bash
# ログファイルから抽出（上位 20 語を TSV 出力）
codex-jp-tune discover --file .claude/local/operator-handoff.md --top 20

# パイプ経由
cat recent-output.md | codex-jp-tune discover --stdin --top 20

# JSON 出力（スクリプト処理用）
codex-jp-tune discover --file recent.md --format json --top 20
```

出力列: `count` / `term` / `suggested_replacement`（辞書から自動補完）/ `first_context`。出力を見て手動で `codex-jp-tune add` を叩くこともできますが、判断を挟むためスキル経由を推奨します。

### Codex Skill `$jp-harness-tune` — チューニング専用の対話スキル

**役割**: ルールを変える前に「本当に必要か」をワンクッション挟むための相談相手。利用者が「このルール、自分のプロジェクトには合わない」と感じたときに呼び出します。

**呼び出し方**:

Codex（CLI / App）の入力欄で `$` を押すとスキル一覧が開きます（Codex のスキルは `/` ではなく `$` で呼び出す仕様）。一覧から `$jp-harness-tune` を選び、続けて自然文で相談内容を書きます。

```
$jp-harness-tune  slice という語をこのリポでは許容したい
```

**スキルが行う 4 ステップ**:

1. 現在の有効ルールを `codex-jp-tune show` で提示
2. 緩める／追加する前に「本当に必要か」を問う（例: `slice` を外す前に「時間区間」で言い換えられないか）
3. 合意が取れたら `codex-jp-tune` の該当サブコマンドを実行
4. 変更後の差分と、元に戻す方法を案内

**配置について**: `install.ps1` / `install.sh` が `~/.codex/skills/jp-harness-tune/SKILL.md` を自動配置します。スキル配置が不要な場合は `-SkipSkill` / `--skip-skill` で opt-out。再インストール時、配置先の `SKILL.md` がバンドル版と一致していれば上書き（冪等）、差分があれば上書きをスキップして stderr に警告を出します。

### 典型的な運用フロー

`finalize` が `ok:false` を返したときの判断は、次の 3 分岐に集約されます。

**1. そのまま Codex に書き直させる**（まず最初に試す）

Codex は違反の具体名（`slice` → `時間区間` など）を受け取って自動で rewrite するため、ほとんどのケースはこれで収束します。同じ語が何度も出る場合のみ、下の 2 か 3 を検討してください。

**2. 特定の語を検出対象から外す**（プロジェクト用語として許容したい場合）

例: データ分析チームで `time slice` を日常的に使う → `codex-jp-tune disable slice`

**3. プロジェクト固有の禁止語を追加する**（検出されるべき語が検出されていない場合）

例: 社内で過去に誤用が起きた `foobar` を確実に止めたい → `codex-jp-tune add foobar --suggest "foobar は日本語訳を使う"`

迷ったら `$jp-harness-tune` スキルを呼んで判断を整理します。ルールを緩める方向の変更は日本語品質を下げる方向なので、スキル側がワンクッション挟みます。

### 運用監視

v0.2.9 以降、`finalize` 呼び出しごとに `~/.codex/state/jp-harness-metrics.jsonl` に 1 行ずつ記録されます（20 MB を超えると 1 世代のみ自動退避、合計約 40 MB で頭打ち）。付属の `codex-jp-stats` CLI で集計できます:

```bash
codex-jp-stats show                       # 呼び出し数・ok 率・draft 文字数 / elapsed ms の分布
codex-jp-stats overhead --window 30       # 同一ターン内の retry 率とトークン overhead 推定
codex-jp-stats tail 20                    # 末尾 20 件を生 JSON で表示
```

月 1 回、以下の指標を確認します:
- finalize 呼び出し回数（`show` の `total calls`）
- retry 発生率（`overhead` の `avg retries per turn`。0.5 を超えたら禁止語リストの見直しサイン）
- 違反種別の分布（`show` の `violations` 統計）
- 呼び忘れ率（`~/.codex/state/jp-harness.jsonl` の末尾エントリ数。hooks 有効時のみ）

詳細は [`docs/OPERATIONS.md`](docs/OPERATIONS.md) を参照。

## 5. 公式対応への導線

### アンインストール（公式対応時）

OpenAI が Codex（CLI / App）に以下のいずれかを公式実装した時点で、本ハーネスは役目を終えます:
- Codex 本体が日本語自然化を標準装備
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
