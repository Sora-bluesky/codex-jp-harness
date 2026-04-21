# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-04-21

v0.3.x の MCP `finalize` gate は 95%+ のリアルタイム compliance を取れる代わりに **output-factor 3.00× / excess +200% output tokens** を払う構造で、「トークン節約したい」層の採用を妨げていた。v0.4.0 は **デフォルトを "lite" モードに切り替え、MCP gate を opt-in の "strict" モードへ降格**する。これで excess overhead は new install で 0.00× が基準になる。

### Added
- **3 つのインストールモード** `install.{ps1,sh} --mode={lite|strict-lite|strict}`:
  - `lite`（新規 install の default）: MCP server を登録しない。Stop hook が assistant message を `ja_output_harness.rules_cli` で検品し `jp-harness-lite.jsonl` に記録。output-factor ≈ 1.00×（excess ~0.00×）。compliance は仮説 60-75%（post-hoc 再教育で翌セッション補正）。
  - `strict-lite`: 同じ lite lint + ERROR 検出時に `{"decision":"block","reason":"..."}` を emit して Codex continuation で self-correct。output-factor ≈ 1.15×（excess ~0.15×）、compliance 95%+。
  - `strict`: v0.3.x 相当の MCP finalize gate。output-factor 2.0〜3.0×。
- **`ja_output_harness.rules_cli`**: assistant message を受け取り JSON で violations を返すローカル CLI。lite / strict-lite Stop hook から呼ばれる。出力は model loop の外で走るため output tokens 0。
- **`config/agents_rule_lite.md`**: lite / strict-lite モード用の短い AGENTS.md ルールブロック（top-5 ERROR + 発火トリガー）。
- **`~/.codex/state/jp-harness-mode`**: Stop hook が runtime に読み取る mode marker。install で書き込み、uninstall で削除。

### Changed
- **AGENTS.md 管理ブロックに BEGIN/END マーカー導入**: `<!-- BEGIN ja-output-harness managed block -->` / `<!-- END ja-output-harness managed block -->` で囲む。mode 切替時の再インストールが旧ブロック（strict/lite 両方）を自動置換するようになり、「strict→lite で MCP ルールが残って Codex が無い tool を呼ぶ」事故を防ぐ（gpt-5.4 review BLOCKER #1）。
- **`Violation.to_dict` の payload slim**: `fix` と `category` フィールドを削除、`snippet` を 50 chars に cap。違反 1 件あたり約 170 bytes（-76%）削減。
- **Stop hook timeout 5s → 15s** + inner subprocess timeout 10s: Windows cold Python start への余裕（gpt-5.4 review MEDIUM #5）。
- **lite / strict-lite で hooks.json mismatch は hard fail**: 従来の warning は enforcement 無しの無言状態を招いていた。`--force-hooks` で上書きを明示要求する（gpt-5.4 review MEDIUM #4）。

### Fixed
- **strict-lite の `stop_hook_active` ガード**: continuation 中の二次 block を抑止し、1 turn で修正できない違反が無限ループに陥らない（gpt-5.4 review BLOCKER #2、`codex-rs/hooks/schema/generated/stop.command.input.schema.json` 準拠）。

### Known Issues
- 並行 Stop hook で `jp-harness-lite.jsonl` への append が稀にレースする可能性（gpt-5.4 review MEDIUM #3）。POSIX の O_APPEND は小さい書き込みで atomic だが、Windows での厳密な保証は無い。v0.4.1 で `metrics.py` の `_rotate_lock` パターンを共有化する予定。

### Notes
- 反映手順: `uv sync --reinstall-package ja-output-harness` → `scripts/install.{ps1,sh} --mode lite -AppendAgentsRule` → Codex 再起動。
- strict ユーザーが lite に移行する場合: `--mode lite -AppendAgentsRule -ForceHooks` を指定すれば AGENTS.md の旧ルールと MCP server 登録が自動で片付く。
- pytest 183 passed（+10）、ruff clean、CI matrix 4/4 + scan + sanitize 通過予定。

## [0.3.8] - 2026-04-21

v0.3.7 のドッグフーディングで `fast-path` 発火率 0% が観測されたが、原因切り分けに必要な情報がメトリクス jsonl に含まれていなかった。schema v2 として `rule_counts` を追加し、`ja-output-stats show` に fast-path miss 診断を追加。

### Added
- **metrics schema v2**: 各エントリに `rule_counts` (rule 名 → 件数) を追加。スキーマ v1 のエントリは読み取り時に `{}` として扱うので後方互換。
- **`ja-output-stats show` にルール別分布**: 全エントリと「ERROR ありで fast-path 未発火」のサブセットの両方で rule_counts 集計を表示。`banned_term` が replacement 無しで applicable を落としているのか、fast-path 実行後に残存 ERROR が出ているのかを切り分けできる。

### Notes
- schema_version は `"1"` → `"2"` へ bump。読み手は `rule_counts` が missing の場合 `{}` にフォールバックすること。
- pytest 173 件 全通過（+2）、ruff clean
- 反映手順: `uv sync` → Codex 再起動

## [0.3.7] - 2026-04-21

gpt-5.4 フォローアップレビューで検出された 6 件（MAJOR 2 / MINOR 3 / NIT 1）を一括解消。uninstall の安全性と docs の実装追従を中心に固める。

### Fixed (MAJOR)
- **uninstall が `codex_hooks = true` を無条件削除** (follow-up MAJOR): `hooks.json` の ja-output-harness エントリを prune した結果、他の hook がまったく残っていない場合にのみ `codex_hooks = true` を外すよう変更。共存する他プラグインの hook を巻き込まない。
- **uninstall の hook 所有判定が部分一致だけ** (follow-up MAJOR): `scripts/uninstall.{sh,ps1}` が `$REPO_ROOT` から導いた hook script の**絶対パス**でまず照合し、失敗時のみ `ja-output-harness` / `codex-jp-harness` の repo マーカー文字列にフォールバック。任意ディレクトリ名で clone されたリポからの install/uninstall でも正しく掃除される。

### Fixed (MINOR)
- **Stop hook regex が server 名を見ていなかった** (follow-up MINOR): `.ps1` / `.sh` 両方の判定から単独 `"name":"finalize"` マッチを外し、`mcp__jp_lint__finalize` の完全修飾名のみで判定。別 MCP server が同名 tool を持つ場合の誤 skip を解消。
- **README / docs/HOOKS.md の uninstall 記述が v0.3.4+ 実装と乖離** (follow-up MINOR / 初回レビュー #50 の docs 追従漏れ): 現行 3 段階挙動（mcp 削除 / hooks prune / codex_hooks 条件付き削除）と AGENTS.md が手動である理由を明記。残骸確認コマンドも追加。
- **`test_version_sync` が source tree しか見ない** (follow-up MINOR): `importlib.metadata.version("ja-output-harness")` を追加で突き合わせ、パッケージ配布物の `METADATA` との乖離も CI で検知できるようにした。

### Fixed (NIT)
- **`cmd_discover` の decode fallback コメントが `latin-1` と書かれていたが実装は UTF-8 replacement** (follow-up NIT): コメントを実装に合わせて修正。

### Notes
- pytest 171 件 全通過（+1）、ruff clean
- 反映手順: `uv sync` → 必要なら install / uninstall を再実行 → Codex 再起動

## [0.3.6] - 2026-04-21

gpt-5.4 code review の NIT 3 件をまとめて掃除 (#56, #57, #58)。挙動変更は軽微な 1 件のみ（summary 文言）。

### Fixed
- **`_summarize([])` の vestigial な空括弧** (#56): `0件の違反を検出 ()` → `0件の違反を検出`。違反ゼロ時のサマリが自然な日本語になる。
- **`stats._format_row()` 未使用関数** (#57): どこからも呼ばれていなかった残骸を削除。
- **`discover.DEFAULT_ALLOWLIST` の `ssh` 重複** (#58): unix/shell tool グループから 2 件目の `ssh` を削除し、process/tools グループに一本化。

### Notes
- pytest 170 件 全通過（既存テスト `TestSummarize.test_empty` は新文言に更新）、ruff clean

## [0.3.5] - 2026-04-21

gpt-5.4 code review の MINOR 5 件をまとめて解消 (#51, #52, #53, #54, #55)。並行耐性・ホットパス性能・env 移行経路の整備。

### Added
- **rules cache** (#55): `server._load_rules_cached` が `(path, mtime)` キーで yaml 再読込を省略。finalize ホットパスの I/O を削減し、mtime 変化時のみ再パースする。
- **`JA_OUTPUT_HARNESS_USER_CONFIG` 環境変数** (#52): 新名称を優先解決。旧 `CODEX_JP_HARNESS_USER_CONFIG` は後方互換で残すが、v0.4.0 で削除予定。相対パスは `.resolve()` で絶対化し、CWD 依存を解消。

### Fixed
- **metrics rotation の排他** (#51): `record` 全体を `O_CREAT|O_EXCL` lock で保護。タイムアウトは 1 秒（best-effort）、取得失敗時は旧挙動に fallback して絶対に finalize を遅延させない。並行 32 スレッド回帰テスト追加。
- **discover が multi-word term を tokenize で割ってしまう** (#53): `existing_terms` に含まれる phrase (`contract drift` 等) を事前マスクしてから走査。単語単独出現は従来通り候補化。
- **Stop hook の `"finalize"` 部分文字列判定が粗い** (#54): `.ps1` / `.sh` 両方の transcript 判定を `mcp__jp_lint__finalize` または `"name": "finalize"` の完全一致に変更。ユーザー引用文の誤 skip と逆の false negative を同時に抑制。

### Notes
- pytest 170 件 全通過（+8）、ruff clean
- 反映手順: `uv sync` → Codex 再起動。`ja-output-tune discover --file` の cp932 ログ対応はそのまま効く。

## [0.3.4] - 2026-04-21

gpt-5.4 code review の MAJOR 3 件を解消 (#46, #47, #50)。shell script 周辺と discover の非 UTF-8 対応。

### Fixed
- **`discover --file` が UTF-8 固定で cp932 ログに落ちる** (#46): UTF-8 → cp932 → UTF-8 with `errors="replace"` の decode fallback を追加。Japanese Windows のログファイルで `UnicodeDecodeError` を吐かなくなった。
- **`install.sh --enable-hooks` の python3 固定** (#47): `resolve_python3` 関数を導入し、`python3` / `python` / `py` の優先順位でプローブ、最後のフォールバックは `.venv` Python。Git Bash + `py` だけの Windows で base install は通るのに hook 設定だけ落ちていた状況を解消。
- **`uninstall.{ps1,sh}` の約束と実装の食い違い** (#50): `[mcp_servers.jp_lint]` に加えて、`config.toml` の `codex_hooks = true` 行と、`hooks.json` の ja-output-harness / codex-jp-harness を参照するエントリを自動プルーニング。AGENTS.md は意図的に手動のまま（他ユーザー定義ルールが混在する可能性）。

### Added
- **`tests/test_tune.TestDiscoverFileEncoding`** +3 件: UTF-8 / cp932 / 無効バイト列の discover round-trip

### Notes
- pytest 162 件 全通過（+3）、ruff clean
- 反映手順: `uv sync` → 必要なら `pwsh scripts\install.ps1 -EnableHooks` / `bash scripts/install.sh --enable-hooks` を再実行 → Codex 再起動

## [0.3.3] - 2026-04-21

gpt-5.4 code review の MAJOR 2 件を解消 (#45, #49)。新ルール追加とドキュメント実態整合。

### Added
- **`pr_issue_number` 検出ルール** (#45): `README.md` と `config/agents_rule.md` が「PR/issue 番号の裸書き」を対象と宣言していたのに `bare_identifier` regex が拾えていなかった。`PR #123` / `issue #42` 等を専用ルールで検出し、fast path でバッククォート自動 wrap。`tests/test_rules.TestPrIssueNumbers` +7 件。

### Fixed
- **README / docs と実装の数値・挙動乖離** (#49):
  - README の機能表を実装に合わせて更新（禁止語 26 語、`identifier_limit_per_sentence: 2` 超過、`pr_issue_number` ルール追加）
  - 「名詞句過連続検出（の-chain / カタカナ長連鎖）」という未実装機能の記述を削除し、代わりに実装済みの文長過多検出 (`sentence_too_long`) を明記
  - `max_identifiers_per_sentence` → `identifier_limit_per_sentence` に正式キー名で記述、`sentence_length` 閾値の書き方も追加
  - `docs/INSTALL.md` の動作確認手順を v0.3.x fast path 挙動（`ok:true, fixed:true, rewritten:"..."`）に更新
  - `docs/OPERATIONS.md` の `noun_chain_allowlist` 参照を削除し、`ja-output-tune disable` / 閾値調整の案内に置換
  - `docs/ARCHITECTURE.md` の fast path 対応範囲を現状（`banned_term` + `bare_identifier` + `pr_issue_number` + 副次効果）に更新
  - `docs/DEPRECATION.md` の uninstall 約束を現行実装（`[mcp_servers.jp_lint]` 削除のみ自動、hook/AGENTS.md は手動）に下げ、完全自動化は Issue #50 で追跡と明記

### Changed
- `server.py` の fast path が `pr_issue_number` も自動修正対象に追加。summary 文言を「識別子/参照 N 件をバッククォート化」に更新。

### Notes
- pytest 159 件 全通過（+7）、ruff clean
- 反映手順: `uv sync` → Codex（CLI / App）再起動

## [0.3.2] - 2026-04-21

gpt-5.4 code review の MAJOR 2 件を解消 (#44, #48)。`tune.py` まわりの core fix。

### Fixed
- **`set-severity` が user-added term に効かない** (#44): `_apply_user_overrides` の順序が「disable → overrides → add」だったため、`add` で追加した term に `overrides` が当たらなかった。順序を「disable → add → overrides」に変更し、両方に適用されるよう修正。
- **`set-severity` が unknown term にも成功表示する** (#44): 存在しない term を指定しても silently 成功して嘘を返していた。bundled + user-added の merged view で lookup し、存在しなければ exit code 1 で拒否。
- **user-local override 更新が非原子的** (#48): 「読み込み → 全体再書き込み」がロックなしで走り、並行 `add`/`remove` で変更が消える可能性があった。`tempfile.mkstemp + os.replace` による atomic write と、`O_CREAT|O_EXCL` の lock file による排他を導入。stale lock は timeout で強制解除。

### Added
- **`tests/test_tune.py`**: +6 件
  - `set-severity` が user-added term の effective severity に反映されるか
  - unknown term は exit code 1 + stderr メッセージ
  - atomic write で tempfile / lock が残らない
  - 8 スレッド並行 `add` で全 term が保存される（last-write-wins しない）
  - `_apply_user_overrides` が add された term の severity を overrides で書き換えられる

### Notes
- pytest 152 件 全通過（+6）、ruff clean
- 反映手順: `uv sync` → Codex（CLI / App）再起動。user override ファイルのスキーマ変更なし

## [0.3.1] - 2026-04-21

v0.3.0 リネーム直後の gpt-5.4 レビューで、`src/ja_output_harness/__init__.py:3` の `__version__` が `0.2.22` のまま残っていることを検出。`pyproject.toml` と `CHANGELOG.md` は `0.3.0` を宣言しているのに実行時バージョンだけ旧値で、障害報告・サポート切り分け・将来の自己診断がずれる状態だった。

### Fixed
- **`__version__`**: `0.2.22` → `0.3.1` に是正。以後は pyproject の `version` と必ず同期する。

### Added
- **`tests/test_version_sync.py`**: `__version__` と `pyproject.toml` の `version` が乖離したら CI が落ちる整合テスト。合わせて CHANGELOG に当該バージョンのエントリが存在するかも検証する。

### Notes
- 機能・挙動に変更なし。リリース後の運用データは継続して有効。

## [0.3.0] - 2026-04-21

**Breaking: リポジトリ / パッケージ / CLI のリネーム**。OpenAI の App Developer Terms は「OpenAI による支援・推奨と誤認される設計」を避けるよう求めており、製品名 **Codex** を冠した識別子（リポ名 `codex-jp-harness`、Python パッケージ `codex_jp_harness`、CLI `codex-jp-tune` / `codex-jp-stats`）は本プロジェクトが非公式ユーティリティであるにもかかわらず誤認を招く可能性があった。そのため商標非依存の名称 `ja-output-harness` へ移行する。機能説明中の「Codex CLI / App」言及は nominative fair use として残置する。

### Changed (Breaking)
- **リポ名**: `codex-jp-harness` → `ja-output-harness`（GitHub の自動 redirect により旧 URL は当面生存）
- **Python パッケージ**: `codex_jp_harness` → `ja_output_harness`（`import ja_output_harness` に変更）
- **CLI スクリプト**: `codex-jp-tune` → `ja-output-tune`、`codex-jp-stats` → `ja-output-stats`
- **pyproject メタ**: `name` / `description` / `keywords` / `urls` / `packages` を新名称に更新。`keywords` から `codex` を除去。`description` を「Japanese output quality gate for LLM coding agents (Codex CLI/App 等) via MCP finalize server」へ広げた

### Added
- **README 冒頭の Disclaimer**（英日併記）: 本プロジェクトが OpenAI の支援・承認・提携を受けていない非公式ツールであり、「Codex」等の商標は検査対象の CLI/アプリを客観的に指す目的でのみ言及していることを明記
- **`scripts/install.*` の MCP server 名自動移行**: `[mcp_servers.jp_lint]` の `args` が旧 module `codex_jp_harness.server` のままなら `ja_output_harness.server` に書き換わる（インストール再実行で適用）

### 維持された nominative 参照
- `Codex CLI` / `Codex App` / `~/.codex/config.toml` / `~/.codex/AGENTS.md` などの製品名・設定パス参照は、検査対象を客観的に指す目的で残置
- スキル名 `jp-harness-tune` はショートカット `$jp-harness-tune` の UX を壊さないため据え置き

### Migration（既存ユーザー向け）
1. `git pull` （または fresh clone）
2. 旧 wheel をアンインストール: `pip uninstall codex-jp-harness` もしくは `uv remove codex-jp-harness`
3. `uv sync`（新パッケージ `ja-output-harness` が install される）
4. `pwsh scripts\install.ps1`（Windows）/ `bash scripts/install.sh`（POSIX）を再実行。`~/.codex/config.toml` の MCP server entry が新 module 参照に置き換わる
5. Codex（CLI / App）を再起動

### Notes
- pytest 144 件 全通過、ruff clean
- PyPI 未公開のため wheel 公開の deprecation 措置は不要
- 機能・挙動に変更なし（v0.2.22 の fast path 拡張を含め、すべての lint / rewrite ロジックは維持）

## [0.2.22] - 2026-04-21

v0.2.21 配布後の実測で output-factor が 3.58× に悪化（retry/turn = 1.58）。n=123 のうち 5+ call の長い尾が 15% に増え、16 call 級のケースも発生。原因は `bare_identifier` 違反（ファイルパス・タスク ID・identifier のバッククォート忘れ）が LLM rewrite に丸投げされ、多段 retry を誘発していたこと。fast-path が対応していたのは `banned_term` のみだったため、`bare_identifier` は slow path で消化されていた。

### Added
- **`rules.apply_backtick_fix(draft, cfg)`**: すべての裸識別子を自動でバッククォート化する純関数。既存のバッククォート span / markdown link URL / fenced code block は保持する。バッククォート化した識別子は `_mask_inline_code` でマスクされるため、副次的に `too_many_identifiers` と `sentence_too_long`（識別子あり branch）も解消される。

### Changed
- **`server._fast_path_applicable`** を拡張。`banned_term`（置換語あり）に加えて **`bare_identifier` / `too_many_identifiers` / `sentence_too_long`** も fast-path 対象と判定するよう変更。再 lint で ERROR が残れば slow path に fallback するため安全。
- **`server.finalize()`** を `_apply_fast_path_fixes` ヘルパーに委譲。banned_term 置換 → bare_identifier バッククォート化 → 再 lint → ERROR ゼロなら `fixed:true` 返却、の流れを一本化。
- **`config/agents_rule.md`** の fast path 節を「禁止語 → 推奨語の置換、および裸の識別子のバッククォート化」と両方カバーする文言に更新。

### Notes
- pytest 144 件（+10）全通過。ruff clean。
- 期待される効果: `bare_identifier` を伴う ERROR ケースが fast-path 発火率に加算される見込み（実測 42% の slow path のうち多くが該当）。output-factor は 3.58× → 2.3〜2.8× への改善を想定。実運用 30 ターン蓄積後に `ja-output-stats overhead` で検証。
- 反映手順: `git pull && uv sync` → Codex（CLI / App）再起動。`~/.codex/AGENTS.md` の規約ブロックを更新するには、旧ブロックを手動削除してから `pwsh scripts\install.ps1 -AppendAgentsRule` を再実行。

## [0.2.21] - 2026-04-21

v0.2.20 配布後の実運用で `ja-output-tune discover` を試したところ、標準技術語（`stdin` / `stdout` / `stderr` / `pester` / `commit` / `push` / `grep` 等）が候補として上がり、判断ノイズを生んでいた。これらはバンドル allowlist に追加しておけば事前除外できる。

### Changed
- **`discover.DEFAULT_ALLOWLIST` を拡張**（追加 25 語）:
  - **標準 I/O ストリーム**: `stdin`, `stdout`, `stderr`
  - **git 動詞 / 名詞**: `commit`, `push`, `pull`, `branch`, `tag`, `clone`, `fork`, `diff`, `blame`, `stash`
  - **テストフレームワーク固有名詞**: `pester`, `pytest`, `jest`, `mocha`, `vitest`, `rspec`, `cargo`, `rustc`
  - **unix / shell ツール名**: `grep`, `awk`, `sed`, `curl`, `wget`, `jq`, `ssh`, `scp`, `rsync`
- これらは日本語に置き換える必要がない（置換候補がない / 固有名詞）ため、discover の signal-to-noise 比を改善。

### Notes
- pytest 134 件（+4 新規 allowlist テスト）全通過。ruff clean。
- 既存利用者は `git pull && uv sync` で反映。
- `merge` / `rebase` は既に `banned_terms.yaml` に INFO severity で登録済みのため allowlist には追加していない（重複を避ける）。

## [0.2.20] - 2026-04-21

v0.2.19 の 8 ステップ walkthrough を実運用で試したところ、スキルが Step 3 の意図メニューを省略して Step 3（判断支援）へ直行する現象を dogfooding で確認した。原因はスキルが「opening メッセージに特定語があれば意図 1/2 と判定」という自然な推論を行うため、discover したかった利用者が意図 6 を選べなかったこと。スキルと README の両方を実態に合わせる。

### Changed
- **`skills/jp-harness-tune/SKILL.md` の Step 2**: 各意図に**キーワード例**を併記し、opening メッセージに該当キーワードがあれば番号確認を省いて該当 Step へ直行する旨を明文化。`slice と done をどう扱うべきか` のように特定語だけ示した場合は意図 1 / 2 として扱う判断ルールを追加。
- **`README.md` Section 4「候補の発掘（discover）」**: 8 ステップ連番を「起動 + 意図明示」と「その後の 5 ステップ」に再構成。`$jp-harness-tune 最近の Codex 出力から禁止語の候補を抽出したい` のような明示的 opening の例を追加し、意図が曖昧なままだと意図 6 に到達しない理由も説明。

### Notes
- コード変更なし。130 件の pytest / ruff check は全通過。
- 既存利用者は `git pull` と install script の再実行（`pwsh scripts\install.ps1 -AppendAgentsRule` / bash 版）で `~/.codex/skills/jp-harness-tune/SKILL.md` も更新される。ただしスキルは MCP とは独立してファイル読み込み時点で評価されるので、更新後は Codex （CLI / App）の再起動を推奨。

## [0.2.19] - 2026-04-21

v0.2.18 の `discover` 節は CLI コマンド中心で、Codex App から対話で使う手順が分かりにくいというフィードバックを受けた docs patch。初回利用者が迷わないよう、スキル経由の 8 ステップを README に明示する。

### Changed
- **README Section 4「候補の発掘（discover）」**を 2 ブロック構造に再構成:
  - **推奨フロー（スキル経由、対話的）**: Codex 入力欄で `$` を押す → `$jp-harness-tune` を選ぶ → 意図 6 → paste or file → 1 語ずつ Y/N・言い換え・severity を応答 → `show` で確認、の 8 ステップを番号付きで明示。Codex 再起動不要の旨も併記。
  - **CLI 単体（スクリプト / バッチで使う場合）**: 従来の bash 例はこちらに集約。

### Notes
- コード変更なし。130 件の pytest / ruff check は全通過。
- 既存利用者への影響なし。`git pull` のみで反映される。

## [0.2.18] - 2026-04-21

v0.2.17 の fast-path は `banned_terms.yaml` に入っている語しか直せず、実運用では fast-path 発火率が 3.1% に留まっていた。原因は Codex 出力に頻出する生英語（`preview` / `review` / `iframe` / `composer` / `overlay` / `drawer` / `context` / `harness` 等）がバンドル済み禁止語の範囲外だったこと。バンドル拡張ではプロジェクト固有の語彙差に追いつけないため、**観測ドラフトから候補を抽出して利用者ごとに育てる** フローへ舵を切る。

### Added
- **`ja-output-tune discover` サブコマンド**: stdin またはファイルから日本語ドラフトを受け取り、未登録の生英語候補を頻度順に抽出する。TSV（既定）/ JSON 両対応、`--top N` / `--min-occurrences N` でチューニング可能。
- **`src/ja_output_harness/discover.py`**: 純関数 `scan_text()` + `Candidate` dataclass。既存の `_strip_code_blocks` / `_mask_inline_code` / `_mask_markdown_links` を再利用して code span・markdown link URL を除外。内蔵 `DEFAULT_ALLOWLIST`（`API` / `HTTP` / `JSON` / `CI` / `PR` / `MCP` / `GitHub` / `OpenAI` などの標準語彙、約 70 語）で標準英語を弾く。`SUGGESTION_DICT` で約 30 語に自動推奨言い換えを付与。
- **skill `$jp-harness-tune` に意図 6「候補抽出（discover）」を追加**。paste / file いずれからでも Codex 出力を受け取り、候補を 1 語ずつ「追加するか」「推奨言い換え」「severity」を対話ヒアリングしてから `ja-output-tune add` を繰り返す。UI ラベルや固有名詞は skip を促す。

### Changed
- **`tune.py` に UTF-8 stdin/stdout/stderr 強制**。cp932 デフォルトの Windows コンソールで discover の Japanese snippet が `UnicodeEncodeError` で落ちる問題を塞いだ（v0.2.11 の stats.py / v0.2.12 の .ps1 hooks と同パターン）。
- **`README.md` Section 4 の運用フロー節**に discover の紹介とコマンド例を追記。
- **`docs/OPERATIONS.md`** に「月次で `discover` を走らせて候補追加」を推奨運用として追記。

### Notes
- pytest 130 件（+19）全通過。ruff clean。
- 既存コマンド（`show` / `path` / `disable` / `enable` / `set-severity` / `add` / `remove`）は変更なし。スキーマ破壊なし。
- dogfooding: 実運用中の別プロジェクトのセッション出力の一部で `preview` / `review` / `drawer` / `terminal` / `desktop` / `code` / `back` が候補として上がることを確認。`SUGGESTION_DICT` 登録済みの語には「プレビュー、確認用」「レビュー」「引き出しパネル」等が自動併記される。
- 期待される効果: 利用者が 10〜20 語を `add` すれば、次の `finalize` からそれらが ERROR として検出され、fast-path で自動修正されるようになる。結果として fast-path 発火率が上がり、output-factor が下がる。

## [0.2.17] - 2026-04-21

v0.2.16 で実測反映した output-factor 3.11× を下げるための仕組み改善。`finalize` に **fast path**（server-side 自動修正）を追加し、違反がすべて決定的に置換可能な `banned_term` の場合は LLM rewrite を経由せず server が直接書き換えた draft を返す。既存クライアントは `fixed:true` を無視しても動作継続（後方互換）。

### Added
- **`rules.extract_replacement(suggest)`**: `banned_terms.yaml` の `suggest` フィールドから最初のカンマ区切りチャンクを置換語として取り出す純関数。30 文字を超える説明的文字列は拒否する。
- **`rules.apply_auto_fix(draft, violations)`**: `banned_term` 違反の置換を `draft` に適用。fenced code block / inline backtick span / markdown link URL は保持する。
- **`server.finalize()` の fast path**: すべての ERROR 違反が `banned_term` かつ置換語が得られる場合、自動修正後の再 lint で ERROR ゼロを確認してから `{"ok": True, "fixed": True, "rewritten": ..., "summary": ...}` を返す。再 lint で新規 ERROR が出たら従来の slow path にフォールバック。
- **`metrics.record()` の `fixed` フィールド**: fast path 発火を記録する additive な boolean。既存 reader は欠損時 `False` として扱う。
- **`ja-output-stats show` の `fast-path:` 行**: fast path 発火率を表示（例: `fast-path: 12 (30.0% server-side auto-rewrite)`）。
- **`config/agents_rule.md` に fast path 節**: `fixed:true` を受け取ったら `rewritten` をそのまま返す旨を追記。`~/.codex/AGENTS.md` にも install script 経由で反映される。

### Changed
- **`docs/ARCHITECTURE.md` のデータフロー節**に fast path / slow path の分岐を明記。fast path の目的が「retry のゼロ化によるトークン削減」であることを明文化。
- **`docs/OPERATIONS.md`** に `ja-output-stats show` の `fast-path` 指標の読み方を追記。

### Notes
- pytest 111 件（+21）全通過。新規テストは `test_rules.TestExtractReplacement` / `TestApplyAutoFix`、`test_server.TestFastPathGate` ほか。
- 既存利用者への破壊的変更なし。`finalize` の応答スキーマは追加フィールドのみ。
- 期待される効果: retry 率 1.11/turn → 0.3〜0.5/turn、output-factor 3.11× → 2.3〜2.5×。実運用 20〜30 ターン蓄積後に `ja-output-stats overhead` で実測し、効果を確認する。
- 反映手順: `git pull && uv sync`、Codex（CLI / App）再起動で MCP server が新コードを読み直す。

## [0.2.16] - 2026-04-21

v0.2.9 で仕込んだ実測機構が十分な統計量（n=91 バースト / 192 calls）を溜めたため、`docs/ARCHITECTURE.md` の「トークン消費の増分」文言を実測値に差し替える patch。

### Changed
- **`docs/ARCHITECTURE.md` のトレードオフ節に実測値を反映**。従来の「実測誘導」文言を、`ja-output-stats overhead --window 30` による n=91 時点の実測（avg output-factor = 3.11× baseline、+211% output tokens over no-finalize baseline）に置換。分布特性（75% のターンが 1-2 call で完結、重度 retry 5+ call は 8%）も併記した。実測値は運用とともに変動するため、随時再計測が推奨される旨を明記。

### Notes
- コード変更なし。90 件の pytest と ruff check は全通過。
- 測定期間: 2026-04-20 夜に metrics をリセットして以降、約 1 日の運用で n=91 バースト蓄積。前半（n=19, 26）では 5-6 call バーストの比率が 20% 前後だったが、n=91 では 8% まで下がり healthier な分布に収束した。
- 既存の「+30〜50%」という v0.2.5 以前の設計時見積もりから、実測ベースで +211% へ更新。設計時見積もりは draft を tool 引数と最終メッセージの 2 箇所で出力するモデルを考慮していなかったための過小推定。

## [0.2.15] - 2026-04-20

README の「Codex Skill `$jp-harness-tune`」と「典型的な運用フロー」節が読みにくいというフィードバックを受けた、わかりやすさの patch。

### Changed
- **Skill 節**を「役割」「呼び出し方」「スキルが行う 4 ステップ」「配置について」の 4 ブロックに再構成。実際の入力例（`$jp-harness-tune slice という語をこのリポでは許容したい`）を掲載し、スキルが内部で行う動作を番号付き手順で明示した。再インストール時の冪等挙動は「配置について」内の短い注記に収めた。
- **典型的な運用フロー**を、連番手順から「`ok:false` を返したときの 3 分岐」に再構成。書き直し待ち／検出対象から外す／禁止語を追加する、の各分岐を太字見出し + 具体例（`time slice` を許容 / `foobar` を追加）で示した。迷った場合のスキル呼び出しを末尾に配置。

### Notes
- コード・挙動変更なし。90 件の pytest と ruff check は全通過。
- 既存利用者に追加作業は不要。`git pull` のみで反映される。

## [0.2.14] - 2026-04-20

Codex App 対応の明示化と、README の日英混在レビューに基づく読みやすさ patch。コード挙動に変更なし。

### Changed
- **ドキュメント全面で「Codex CLI」を「Codex（CLI / App）」に整理**。README、`docs/INSTALL.md`、`docs/HOOKS.md`、`docs/ARCHITECTURE.md`、`docs/DEPRECATION.md`、`config/agents_rule.md`、`AGENTS.md`、`skills/jp-harness-tune/SKILL.md`、install/uninstall スクリプトのランタイム出力、`src/*.py` の docstring、issue template まで。Codex App のデスクトップ版は同じ Rust バイナリを使い `~/.codex/` を共有するため、本ハーネスは両 surface で動作する旨を冒頭 box で明示した。
- **README を日英混在観点でメタ認知レビュー（3 ラウンド）**。以下を適用:
  - 冒頭 1 文を初見読者向けに噛み砕いた説明に置換（「MCP 検品ゲート + Stop / SessionStart hook ハーネス」の立て続け用語を回避）
  - 「両方の surface に反映」→「両方の利用形態に反映」
  - 「間に噛ませ」→「間に挟み」
  - 「95%+ + 残り数%」の `+` を「と」で接続
  - 見出し「severity 三段階の意味」→「severity（重要度）の三段階」
  - 「`$` sigil で呼び出します」→「`$` 記号で呼び出します」
  - 「アンインストーラーで関連エントリを削除」→「`[mcp_servers.jp_lint]` セクションを削除（`AGENTS.md` は手動削除）」
  - 「運用監視」節を v0.2.9 以降の `ja-output-stats` CLI を前提に書き直し、`show` / `overhead` / `tail` の実行例を掲載。retry 率 > 0.5 を見直しサインとして明示

### Notes
- コード変更なし。90 件の pytest と ruff check は全通過。
- ユーザー向け破壊的変更なし（install / uninstall の動作不変、スクリプトの stdout 文言のみ変更）。
- 誤記修正に近い patch のため、既存利用者に追加作業は不要。`git pull` のみで反映される。

## [0.2.13] - 2026-04-20

開発者の `uv sync` 一発で pytest / ruff / pytest-cov が揃うよう、dev 依存を PEP 735 の `[dependency-groups]` 形式に追加する chore。従来の `[project.optional-dependencies]` も残しているため、pip 利用者の `pip install -e '.[dev]'` は引き続き動く。

### Changed
- **`pyproject.toml` に `[dependency-groups] dev = [...]` を追加**（pytest>=8.0 / pytest-cov>=5.0 / ruff>=0.5）。`uv sync` はデフォルトでこのグループを同期するため、コントリビューターが `--extra dev` を覚えていなくてもテスト環境が整う。
- **`[project.optional-dependencies] dev` は維持**。pip 経由のインストールと extras 指定での同期を壊さないための wire 互換。

### Notes
- コード変更なし。90 件の pytest と ruff check は全通過。
- 既存開発者が v0.2.12 で `uv sync` を走らせて dev 依存がプルーニングされた場合、v0.2.13 以降は `uv sync` だけで自動復活する。

## [0.2.12] - 2026-04-20

hook の標準入力が Japanese Windows (cp932 デフォルト) で誤デコードされ、Stop hook が missing-finalize を記録できなくなる実バグの修正。v0.2.11 までは stdout / stderr のみ UTF-8 に強制していたが、`[Console]::In` はデフォルトで `InputEncoding` を使うため、Codex が UTF-8 で piped した JSON payload が cp932 として解釈され `ConvertFrom-Json` が silent fail する経路が残っていた。

### Fixed
- **`hooks/stop-finalize-check.ps1` と `hooks/session-start-reeducate.ps1` の先頭で `[Console]::InputEncoding` を UTF-8 に強制**。これにより cp932 デフォルトの環境でも Codex から piped された UTF-8 JSON が正しく読める。
- **`docs/HOOKS.md` のトラブルシューティングに本件を追記**。v0.2.6〜v0.2.11 の利用者向けに `git pull && uv sync` だけで解消する旨を明記した（Codex 再起動不要、hook は起動ごとに `.ps1` を読み直す）。

### Notes
- bash 版 hook は `PYTHONIOENCODING=utf-8` を既に v0.2.6 で設定済み（stdin も stdout も）なので影響なし。
- E2E 検証で dogfooding 利用者（Japanese Windows）が FAIL を踏んで検出。Codex CLI 自体の挙動変更ではなく PowerShell のデフォルト設定に起因するので、他の Windows 利用者にも影響する可能性があった。
- テスト変更なし（既存 90 件全通過）。.ps1 の挙動変更はテストランナーから検証できないため、手動検証のみ。

## [0.2.11] - 2026-04-20

`ja-output-stats overhead` が Windows の cp932 コンソールで `UnicodeEncodeError` で落ちる問題の patch。出力文字列に含まれる `≈` (U+2248) と `×` (U+00D7) が cp932 にないため、デフォルト codepage の環境でクラッシュしていた。

### Fixed
- **`stats.main()` で `sys.stdout` / `sys.stderr` を UTF-8 に再構成**。`io.TextIOWrapper.reconfigure(encoding='utf-8')` を使用。reconfigure が存在しない環境（旧 Python / リダイレクト済みストリーム等）では silent no-op となり、従来挙動を維持する。
- これにより Windows の cp932 コンソールでも `≈`、`×`、日本語文字が文字化けせず出力される。

### Notes
- コードパス以外の変更なし。pytest は 90 件全通過、ruff clean。
- v0.2.9 / v0.2.10 で `ja-output-stats overhead` を試して Windows で落ちた利用者は、`uv sync` で更新してください（MCP サーバー本体は変更ないので再起動不要。CLI 自体は `.venv` が新しくなれば即動く）。

## [0.2.10] - 2026-04-20

v0.2.9 で追加した metrics jsonl が長期運用で青天井に肥大するのを防ぐ size-based rotation を追加する patch。既存データは失わず、`ja-output-stats` は archive も併読する。

### Added
- **`metrics.DEFAULT_MAX_BYTES = 20 MB` のしきい値を導入**。`record()` は書き込み前にファイルサイズを O(1) で確認し、20 MB を超えていたら `jp-harness-metrics.1.jsonl` に rename して新しい active ファイルを開始する。保持世代は 1 のみ（前回の `.1.jsonl` があれば上書き）で、総ディスク使用量は最大でも約 `2 * max_bytes = 40 MB` に収束する。
- **`metrics.archive_path()` helper**: active file から archive パスを導出する純関数（`jp-harness-metrics.jsonl` → `jp-harness-metrics.1.jsonl`）。
- **`stats._read_entries()` が archive → active の順に連結読み込み**。ローテーション後も `ja-output-stats show` / `overhead` は全履歴を参照する。

### Notes
- pytest は 90 件（+3）全通過。新規は rotation 発火・archive 上書き（世代 1 のみ）・stats が両方を読むことの検証。
- ルーリングは fail-silent。stat() 失敗や rename 失敗でも tool 応答は継続する。
- `max_bytes` は `record()` の引数で上書き可能（テスト用の tiny 値 / 将来の設定拡張）。

## [0.2.9] - 2026-04-20

`finalize` 呼び出しの実測機構を追加する minor リリース。これまで `ARCHITECTURE.md` で「トークン消費 +30〜50%」と設計時見積もりを掲載していたが、実測に基づく数字に置き換えるための計測基盤を先に整備した。既存運用への破壊的変更はなく、メトリクス書き込みに失敗しても `finalize` 自体は継続する（fail-silent）。

### Added
- **`src/ja_output_harness/metrics.py`**: 各 `finalize` 呼び出しを `$CODEX_HOME/state/jp-harness-metrics.jsonl` に 1 行ずつ追記するモジュール。スキーマは `ts / draft_chars / draft_bytes / violations_count / severity_counts / response_bytes / elapsed_ms / ok`。I/O 失敗は例外を握り潰す。
- **`src/ja_output_harness/stats.py` と `ja-output-stats` CLI**: 蓄積した jsonl を集計する。
  - `ja-output-stats path`: jsonl のパスを表示
  - `ja-output-stats show`: 呼び出し数・ok 率・draft_chars / violations / elapsed の分布（mean / median / p90 / p99 / max）
  - `ja-output-stats overhead --window 30`: 連続呼び出しを同一ターンとみなし、retry 率と「avg output-factor (draft が tool 引数と最終メッセージで 2 回出力される → retry_rate + 2.0)」を表示
  - `ja-output-stats tail N`: 末尾 N 件を生 JSON で表示
- **`pyproject.toml` の `[project.scripts]` に `ja-output-stats` を登録**。`ja-output-tune` と同じ枠で `uv sync` 後に即利用可能。

### Changed
- **`server.py` の `finalize()` に計測を組み込んだ**。violations 計算と response 整形を維持しつつ、`time.perf_counter()` で elapsed を測り、`metrics.record()` を呼ぶ。I/O が失敗しても tool 応答には影響しない。
- **`docs/ARCHITECTURE.md` の「+30〜50%」を削除**。実測誘導の文言に置換し、v0.2.9 以降は `ja-output-stats overhead` で取得する方針に変更。
- **`docs/OPERATIONS.md` を更新**。旧 `stats.json` 記述を `jp-harness-metrics.jsonl` + `ja-output-stats` フローに書き換えた。

### Notes
- pytest は 87 件（+6）全通過。新規は `tests/test_metrics.py`（record 動作・IO エラー握り潰し・show/overhead/tail コマンドの出力検証）。
- 既存利用者は再インストール（`install.ps1` / `install.sh`）で `.venv` が更新され、`ja-output-stats` が使えるようになる。再起動は不要（MCP サーバーだけは再起動で新コード反映）。
- 蓄積データが一定量たまり次第、`ARCHITECTURE.md` に実測値を反映する（将来の patch リリース）。

## [0.2.8] - 2026-04-20

ドキュメント描画の patch リリース。v0.2.7 まで `docs/assets/arch-03-layer-responsibility.svg` が `<b>` タグを vector path として描画しており、GitHub で「`<b>AGENTS.md 規約層</b>`」のようにリテラル文字列として表示されていた。Figma MCP が太字指定を HTML タグ文字列のままグリフ化したのが原因。該当図を Mermaid 図に置き換えた。

### Fixed
- **`docs/ARCHITECTURE.md` の「レイヤー責務」図を Mermaid に置換**。`<b>` glyph 問題を根本解消し、GitHub native renderer に任せる方針に変更した。User / Runtime / Harness / Persistence の 4 層と依存関係を `flowchart TB` で表現。
- **`docs/assets/arch-03-layer-responsibility.svg` を削除**。

### Notes
- 他 3 枚の SVG（arch-01 / arch-02 / arch-04）は `<b>` タグ問題がないためそのまま保持。
- コード変更なし。既存 81 件の pytest は全通過。

## [0.2.7] - 2026-04-20

ドキュメント描画の patch リリース。v0.2.6 で `docs/assets/` に配置したアーキテクチャ図 4 枚が拡張子 `.png` で保存されていたが中身は SVG XML だったため、GitHub が `image/png` として解釈してレンダリングに失敗していた。拡張子を `.svg` に統一し、Markdown の `![...](...)` 参照も併せて更新した。

### Fixed
- **`docs/assets/arch-0[1-4]-*` を `.png` から `.svg` に改名**。Figma MCP でエクスポートした図は SVG だったため、拡張子の方を実体に合わせた。`docs/ARCHITECTURE.md` の 4 箇所の参照も更新。
- **`.gitattributes` に `*.svg text eol=lf` を追加**。SVG は XML テキストであり、CRLF 変換で diff が膨らむのを防ぐ。

### Notes
- コード変更なし。既存 81 件の pytest は全通過。
- v0.2.6 を既にインストール済みの利用者は再インストール不要（hooks 関連バイナリの変更はない）。リポジトリを pull し直すだけで画像が表示されるようになる。

## [0.2.6] - 2026-04-20

Codex 0.120.0+ の Stop / SessionStart hook を opt-in で組み込む minor リリース。MCP `finalize` ゲートの呼び忘れを次セッション起動時に再教育プロンプトで補完する後方検知ループを追加した。MCP 本体と既存運用への破壊的変更はなく、`--enable-hooks` 指定時のみ hooks が配置される。

### Added
- **`hooks/stop-finalize-check.{ps1,sh}`**: Stop hook。Codex 0.120.x の stdin 仕様を受けて `last_assistant_message` + transcript を走査し、日本語応答かつ `finalize` 未呼び出しなら `~/.codex/state/jp-harness.jsonl` に `missing-finalize` を記録する。fail-open（null transcript は誤検知を避けてスキップ）。
- **`hooks/session-start-reeducate.{ps1,sh}`**: SessionStart hook。`source=startup|clear` 時に state を読み、上位 3 種別の違反を 400 文字以内の再教育プロンプトに整形して stdout に出力する。`source=resume` では既存文脈を壊さないためスキップ。対象エントリには `consumed: true` を付けて再書き込み。
- **`hooks/bench.{ps1,sh}`**: Stop / SessionStart 両 hook を 10 回実行して mean / max を表示するベンチ。
- **`config/hooks.example.json`**: `~/.codex/hooks.json` のテンプレート。install script が `{{STOP_COMMAND}}` / `{{SESSION_START_COMMAND}}` を絶対パスで置換して書き出す。
- **`scripts/install.{ps1,sh}` に `--enable-hooks` / `-EnableHooks` フラグ**: opt-in で hook 配置を有効化する。Codex CLI 0.120.0 未満では警告を出してスキップ、他のインストール処理は継続。`--force-hooks` / `-ForceHooks` で既存 `hooks.json` を上書き。
- **`docs/HOOKS.md`**: hook 仕様・state スキーマ・性能目標・プライバシー方針・トラブルシューティングをまとめたドキュメント。
- **`docs/assets/arch-0[1-4]-*.svg`**: ARCHITECTURE に埋め込む技術図 4 枚（スイスチーズ層構造 / データフロー / レイヤー責務 / コンテキスト失効）。

### Changed
- **`docs/ARCHITECTURE.md` を全面改訂**。ASCII 図に加えて PNG 図を埋め込み、MCP ゲート + Stop / SessionStart hook の二層構成を説明する節を追加した。
- **`README.md` を 5 セクション構造に整理**（なぜ存在するのか / 仕組み / インストール / 運用とチューニング / 公式対応への導線）。既存情報は保持しつつ、hook 関連の案内を「仕組み」「インストール」に組み込んだ。
- **`config/agents_rule.md` に 1 行追記**: 呼び忘れは Stop hook が検知して次回セッション起動時に再教育プロンプトが注入される旨を明記した。install で `~/.codex/AGENTS.md` に反映される。

### Fixed
- **Windows + Git Bash で `.sh` hook が Microsoft Store の python3 スタブを掴んで無音失敗する問題**。python 実行可能ファイルを `--version` 相当の呼び出しで検証し、スタブを弾くように修正した。
- **`.sh` hook が Windows の cp932 コードページで日本語プロンプトを出力して文字化けする問題**。`PYTHONIOENCODING=utf-8` を強制して UTF-8 出力に統一した。合わせて `.ps1` も `[Console]::OutputEncoding = UTF-8` を設定した。

### Notes
- 既存利用者への影響なし。従来の `install.ps1 -AppendAgentsRule` / `install.sh --append-agents-rule` は挙動が変わらない。hooks を使いたい場合のみ `-EnableHooks` / `--enable-hooks` を追加する。
- hooks はリポジトリローカルの `.codex/config.toml` では動作しない既知バグ（[Issue #17532](https://github.com/openai/codex/issues/17532)）があるため、グローバル `~/.codex/hooks.json` にのみ登録する。
- `install.ps1` / `install.sh` は `codex --version` が 0.120.0 未満の場合に `codex_hooks` 設定を書かず、他の処理を継続する。既存環境の互換性は保たれる。
- 既存 81 件の pytest は全通過。hook 関連の E2E は 7 シナリオを手動で検証（null transcript fail-open / 英語応答スキップ / 日本語 + 未呼び出し記録 / transcript に finalize 有りでスキップ / startup + 未消化で再教育 / resume でスキップ / 期限切れ無視）。

## [0.2.5] - 2026-04-19

ドキュメントの汎用化 patch。インストール手順で例示していたディレクトリが特定の個人規約寄りだったため、より一般的なパス例に置換した。合わせて `config/agents_rule.md` と README 移行案内の主観表現を客観的な文言に整理した。Sanitize CI に再発防止パターンを追加した。

### Changed
- **インストール手順のパス例を汎用化**。README パターン A と `docs/INSTALL.md` の 3 箇所で示していた Windows クローン先例を、より一般的な `%USERPROFILE%\Projects\` / `C:\Users\<username>\Projects\` 形式に整理した。
- **`config/agents_rule.md` と README 移行案内の主観表現を整理**。「筆者個人の AGENTS.md の番号体系」→「当初の AGENTS.md の番号体系」（2 箇所）。`config/agents_rule.md` は `~/.codex/AGENTS.md` に追記されるため、利用者環境にも反映される。
- **Sanitize CI のパターンに `Documents[\\/]Projects[\\/]apps` を追加**。ドキュメントの汎用化が将来の編集で後戻りしないようゲートで強制する。

### Notes
- コード変更なし。既存 81 件の pytest は全通過。
- `config/agents_rule.md` が変わるので、利用者は既存の `~/.codex/AGENTS.md` の規約ブロックを手動削除 → `install.ps1 -AppendAgentsRule` / `install.sh --append-agents-rule` を再実行 → Codex CLI 再起動で新文言に差し替え可能。v0.2.3 / v0.2.4 と同じ手順。

## [0.2.4] - 2026-04-19

現行ドキュメントを **Codex 専用**に整理する patch。本リポジトリは OpenAI Codex CLI を唯一のターゲットとし、他の AI エージェント（Claude Code 等）は前提としない方針を明確化した。歴史的記述は不変性保持のため維持している。

### Changed
- **`README.md` / `AGENTS.md` / `config/agents_rule.md` から "Claude Code" 言及を削除**（全 7 箇所）:
  - README ディレクトリ構成の `AGENTS.md` 説明を「Codex/Claude Code がこのリポで作業する時の規約」→「Codex がこのリポで作業する時の規約」
  - 暫定対策の比較基準「Claude Code 水準の日本語対応」→「日本語自然化」（README / AGENTS.md / `config/agents_rule.md` / DEPRECATION トリガー）
  - `AGENTS.md` の dogfooding 記述「Codex / Claude Code の日本語出力」→「Codex の日本語出力」
- `config/agents_rule.md` の変更で、`~/.codex/AGENTS.md` に追記される規約本文も Codex 専用の文言に更新される。

### Notes
- `CHANGELOG.md` の過去エントリ（v0.1.1 / v0.2.0 / v0.2.1）は **歴史的記録として Claude Code 言及を保持**。事実の改変ではなく現行ドキュメントの方針整理。
- `.gitignore` の `.claude/` エントリは保持。ドキュメントは Codex 専用だが、開発者が補助的に Claude Code を使った時の `.claude/` ディレクトリ誤コミットを防ぐセーフティネットとして残す。
- 既存の `~/.codex/AGENTS.md` に v0.2.3 の規約ブロックを追記済みの利用者は、v0.2.3 と同じ手順（旧ブロック手動削除 → `install.ps1 -AppendAgentsRule` 再実行 → Codex CLI 再起動）で新文言に差し替え可能。

## [0.2.3] - 2026-04-19

発火トリガー仕様漏れの bug fix。v0.2.2 までは `config/agents_rule.md` の発火トリガーが OR 条件（「500 文字超」「見出しあり」「特定パス書き込み」等）で定義されていたため、短い会話調の進捗報告（約 400 文字、見出しなし）が `finalize` をスキップして素通りしていた。品質ゲートと自称するのに漏れる状態は dogfooding として自己矛盾。

### Fixed
- **発火トリガーを opt-out 方式に変更**。日本語を含む応答は**原則全て** `mcp__jp_lint__finalize` の対象とし、**除外 4 パターンに完全一致する時のみ**呼び出しをスキップできる:
  - コードブロック / 差分単独（日本語地の文を含まない）
  - 20 文字以内の 1 行相槌
  - yes / no の二値回答
  - 日本語文字をまったく含まない応答
  - 500 文字閾値と冗長 3 条件（見出し / 進捗内容 / 体裁）は削除
- **「迷ったら呼ぶ」を原則として明記**。呼びすぎのコストは MCP 往復 1 回で実害がなく、呼び忘れのコストは品質ゲート自体の信頼失墜。前者が大幅に軽い、という非対称性を規約に反映した。

### Notes
- 既存の `~/.codex/AGENTS.md` に古い規約ブロックが追記済みの利用者は、以下で新規約に差し替えてください:
  1. `~/.codex/AGENTS.md` から「日本語技術文の品質ゲート (ja-output-harness)」セクションを手動削除
  2. 更新されたリポジトリで `install.ps1 -AppendAgentsRule` / `install.sh --append-agents-rule` を再実行
- MCP サーバー・lint ロジック (`rules.py`) には一切変更なし。既存 pytest 81 件は全通過する。

## [0.2.2] - 2026-04-19

install スクリプトが `jp-harness-tune` skill まで配置するようになった feature リリース。MCP 登録・AGENTS.md 追記・skill 配置を 1 コマンドで完了できる。

### Changed
- **`install.ps1` / `install.sh` が `jp-harness-tune` skill を自動配置するように
  なった**。v0.2.1 で同梱した `skills/jp-harness-tune/SKILL.md` を
  `~/.codex/skills/jp-harness-tune/SKILL.md` にコピーするロジックをインストーラー
  に追加。既存ファイルが bundled と SHA-256 一致なら上書き（冪等）、
  カスタム編集して差分があれば上書きをスキップして stderr に警告を出し、
  利用者の編集を保護する。opt-out フラグは `-SkipSkill` (PowerShell) /
  `--skip-skill` (bash)。
- **README の skill 配置手順を install script 前提に再構成**。「Codex Skill
  (任意)」section は「自動配置される。手動上書きの場合」に書き換え、
  パターン A の手順 3 の説明にも skill 配置が一括で行われる旨を追記。
  「インストールで変更されるユーザー環境」ツリーの skill 行を
  `(任意・手動コピー)` → `install script が自動配置` に更新。

### Notes
- v0.2.1 で手動コピーした利用者は、`install` を再実行した際に bundled と
  同一内容であれば冪等に上書きされ、カスタム編集していればスキップされる
  （既存の編集は保護される）ため、特別な作業は不要。
- `pip install ja-output-harness` のみの利用者は wheel に `skills/` が
  含まれないため、引き続き git clone + install script の経路が必要。
  wheel への同梱は v0.3 で検討する。

## [0.2.1] - 2026-04-18

v0.2.0 リリース後に発見された整合性問題を一括修正する patch リリース。機能追加はなし、ドキュメントと skill 配布形式の correctness 修正のみ。

### Fixed
- **`jp-harness-tune` skill を Codex CLI 形式に書き換え**。v0.2.0 では誤って
  Claude Code skill 形式 (`skill.md` 小文字・Claude Code frontmatter) で同梱して
  いたが、本リポジトリが Codex CLI 向けである以上、第一ターゲットは Codex に
  合わせるべき。Codex 公式仕様 (`codex-rs/core-skills/src/loader.rs`, `codex-rs/
  skills/src/assets/samples/skill-creator/SKILL.md`) を一次情報として参照し、
  以下に修正:
  - ファイル名: `skill.md` → `SKILL.md`（Codex は大文字固定）
  - frontmatter: `name` / `description` のみ（Codex 認識フィールド）。
    `argument-hint` 等は Codex 非対応のため削除
  - 配置先: `~/.codex/skills/jp-harness-tune/SKILL.md`
    （`$CODEX_HOME/skills/...`）
  - 呼び出し: `/jp-harness-tune` → `$jp-harness-tune`（Codex は `$` sigil）
  - README の install 手順・ディレクトリ構造・インストール後の
    `~/.codex/` ツリーも合わせて更新

### Changed
- **「撤去」→「アンインストール」に統一**。README / AGENTS.md /
  `config/agents_rule.md` / `docs/DEPRECATION.md` / `docs/ARCHITECTURE.md`
  の全 9 箇所。ソフトウェア文脈では「撤去」より「アンインストール」の方が
  自然で、利用者に伝わりやすい。`config/agents_rule.md` は
  `~/.codex/AGENTS.md` に追記されるため、利用者の環境にも反映される。
- **内部呼称「7.p」/「7.q」を「品質ゲート規約」に統一**。v0.1.x で使用していた
  「7.p ルール」は筆者個人の `~/.codex/AGENTS.md` 章番号（7.a〜7.o の次）に
  由来する歴史的通称で、v0.1.2 で `agents_rule.md` がスタンドアロン形式に
  刷新された時点で実体との対応は失われていた。現行ドキュメントから「7.p」/
  「7.q」呼称を削除（13 箇所、CHANGELOG の歴史的記述は不変性のため保持）。
  `config/agents_rule.md` 冒頭コメントに呼称 SSoT 宣言を追加。
- **dead reference「7.q」を完全撤去**。`agents_rule.md` 本体に「7.q」相当の
  規約は存在せず、4 箇所のドキュメント参照が空を指していた（AGENTS.md /
  docs/OPERATIONS.md / docs/DEPRECATION.md / scripts/uninstall.ps1）。
- **README に v0.2.0 以前利用者への移行案内 section を追加**。旧呼称が
  消えたことによる既存利用者の混乱を防ぐため、再インストール時の挙動を明記。

## [0.2.0] - 2026-04-18

v0.1.x からの大きな拡張。禁止語を倍増し、severity 階層で「止めるべき違反」と「参考情報」を分離し、利用者側で規則を調整できる仕組み (user-local override + `ja-output-tune` CLI + Claude Code skill) を追加した。

### Added
- **banned_terms 拡張**: 13 → 26 語。新規追加は普遍カテゴリから抽出
  (process: `merge`, `rebase`, `cherry-pick`; concepts: `fingerprint`,
  `fallback`, `fixture`, `payload`, `helper`, `wrapper`; state:
  `pending`, `idle`; review: `verdict`, `blocker`)。
- **severity 三段階**: `ERROR` / `WARNING` / `INFO`。`finalize` は ERROR
  が 0 件なら `ok: true` を返し、WARNING/INFO は `advisories` で通知する。
  ERROR が 1 件でも残れば `ok: false`。修正は MUST。
- **banned_terms.yaml schema v2**: 各エントリに `severity`, `category`,
  `katakana_form` フィールドを追加。後方互換のため省略時はデフォルト値
  (`severity=ERROR`, `category=other`, `katakana_form=""`)。
- `Violation` データクラスに `severity` と `category` フィールド追加。
- **User-local override**: `~/.codex/jp_lint.yaml` を置くと、バンドル済み
  `banned_terms.yaml` に対して `disable` / `overrides` / `add` /
  `thresholds` を適用できる。探索優先順位は
  `$CODEX_JP_HARNESS_USER_CONFIG` → `$XDG_CONFIG_HOME/ja-output-harness/jp_lint.yaml`
  → `~/.codex/jp_lint.yaml`。存在しなければバンドル値がそのまま使われる。
- **`ja-output-tune` CLI**: ユーザー設定を対話的に編集する console script。
  サブコマンドは `path` / `show` / `disable` / `enable` / `set-severity` /
  `add` / `remove`。pyyaml のみ依存。
- **`jp-harness-tune` Claude Code skill**: `skills/jp-harness-tune/skill.md`
  を同梱。ルールを安易に緩めないよう、無効化・severity 調整・追加の前に
  必ず判断支援ステップを挟み、`ja-output-tune` を実行する。
  `~/.claude/skills/` に配置すると `/jp-harness-tune` で呼べる。
- **README「違反検出時の対処法」section**: severity 三段階の意味、
  user-local override の yaml 例、`ja-output-tune` の使い方、典型的な
  運用フローを統合。インストール直後の読者が最初につまずく
  「`ok:false` が返ったらどうするか」の導線を整備。

### Changed
- `agents_rule.md`: severity 階層の説明を追加。Codex は ERROR を必ず
  修正、WARNING は強く推奨、INFO は参考扱い。
- `finalize` の summary 文字列に severity 別件数を含める
  (例: `5件の違反を検出 (3 ERROR, 1 WARNING, 1 INFO)`)。

## [0.1.3] - 2026-04-18

配布安全性 patch。配布物に残っていた特定プロジェクト名・個人 Vault パスを匿名化し、markdown link 内 URL の誤検出も併せて修正。

### Security
- Sanitized test fixtures and documentation: removed project-specific
  identifiers (a previous downstream project name and several internal
  task IDs of the form TASK-NNN) and personal Obsidian Vault sub-paths.
  Fixtures now use generic placeholder names (`sample-core.ps1`,
  `my-app/src-tauri`, `TASK-101`〜`TASK-106`) that retain the same
  violation counts but carry no real-project context.
- Added `.mailmap` so `git log` displays the historical commit author as
  the project alias (raw commits on the remote remain unchanged).
- New CI workflow (`.github/workflows/sanitize.yml`) rejects any tracked
  file that reintroduces personal or project-specific strings.

### Fixed
- `bare_identifier` no longer flags the URL inside markdown links of the
  form `[text](url)`. The URL portion is now masked before identifier
  detection. The label portion is still scanned, so identifiers written
  as link text remain caught.

### Changed
- `config/agents_rule.md`: trigger description now refers to generic vault
  folders (`Notes/`, `Docs/`, `Articles/`) rather than personal-vault names.

## [0.1.2] - 2026-04-17

v0.1.0 / v0.1.1 で見過ごしていた 3 件のユーザビリティ修正。

### Changed
- **`config/agents_rule.md` をスタンドアロン形式に刷新**。v0.1.1 までは
  「`   p. ...`」形式で筆者のローカル `~/.codex/AGENTS.md` 構造（7.a〜7.o の
  番号付きリスト前提）に強く依存していた。他ユーザーの AGENTS.md に追記すると
  孤立した「p.」で始まる読めないブロックになっていた。
  新しい形式は `## 日本語技術文の品質ゲート` から始まる独立セクション
  (`##` + `###` 見出し構成)。フレッシュな AGENTS.md にも既存ルール群の
  末尾にも追記でき、個人情報や環境固有のパスは一切含まない。
- **README の「冪等」を平易な日本語に置換**。「冪等に動く」→「同じコマンドを
  何度実行しても結果は同じ（副作用が重複しない）」。技術者向け文書でも、
  日本語が読める人に自然に伝わる語を優先する方針。

### Added
- `config/banned_terms.yaml` に `冪等` を追加。自分のツールが自分のドキュメント
  の読みづらさも検出できるようになった（dogfooding）。suggest は
  「何度実行しても同じ結果、繰り返しても安全」。テスト 2 件追加で合計 30 件。

## [0.1.1] - 2026-04-17

v0.1.0 リリース同日の追従リリース。7.p トリガー範囲の拡張と、リポ固有の規約文書（AGENTS.md）を追加。

### Added
- Project-level `AGENTS.md` at repo root. Complements the global
  `~/.codex/AGENTS.md` with repo-specific context: stack, branch
  protection rules, dogfooding intent, deprecation trigger, release
  workflow. Codex and Claude Code read both when working here.
- README.md "ディレクトリ構成" section showing the cloned repo layout
  plus the `~/.codex/` files that install.ps1 / install.sh modify.
  Helps users understand what they get and what the installer touches.

### Changed
- AGENTS.md 7.p trigger scope widened from "progress reports" only to
  "all Japanese technical writing": learning notes, docs, design memos,
  release notes, release articles. File append case clarified: the
  appended chunk goes through finalize; existing body stays untouched.
  Motivated by observed bare-identifier violations in learning notes
  (narrow slice, parity, fail-close, regression, contract drift — all
  bare).

## [0.1.0] - 2026-04-17

初回公開リリース。Zenn 記事 [Codex の日本語を救ったのは「ずんだもん」だった](https://zenn.dev/sora_biz/articles/ja-output-harness-milestone) と同日公開。

### Documented
- Zenn writeup published at
  https://zenn.dev/sora_biz/articles/ja-output-harness-milestone
  ("Codex の日本語を救ったのは「ずんだもん」だった"). README now links
  to it as the primary narrative for the 32→0 milestone, the VOICEVOX
  register-switch hypothesis, and the prompt-layer vs runtime-layer
  tradeoffs.

### Added
- Cross-platform support. `scripts/install.sh` and `scripts/uninstall.sh`
  mirror the PowerShell scripts for macOS, Linux, and Git Bash on Windows.
  install.sh auto-converts MSYS paths to native Windows form via
  `cygpath` when running on Git Bash so Codex (non-MSYS process) can
  spawn the venv python correctly.
- README and docs/INSTALL.md now show both install paths side by side.
  pyproject.toml classifier changed to "OS Independent".
- `config/agents_rule.md` gains three post-v0.1.0 clauses to cover failure
  modes observed in a real Codex session log:
  - **Session-wide identifier rule**: code identifiers (file names, func
    names, branch names, PR numbers, task IDs, param names, commands)
    must be backtick-wrapped in every Japanese output, not only in
    report-shaped messages that trigger finalize.
  - **"Check first, then call" is banned**: Codex must call finalize
    first and fall back only on actual error. Saying "let me check if
    jp_lint is usable" is itself a forgot-to-call symptom.
  - **Ambiguous reference words are banned**: phrases like 対象テスト /
    広い確認 / 前面 / 公開面 / 一式 force the reader to guess scope.
    Replace with concrete command/module names (e.g. `cargo test -p X`).
- Test fixtures capturing the full before/after story:
  `codex_actual_output.txt` (32 violations), `codex_after_voicevox.txt`
  (4 violations), `codex_after_strengthened.txt` (0 violations).
- Sentence length rule (`sentence_too_long`): flags sentences over 80 chars
  (or 50 chars if they contain code identifiers). VOICEVOX-inspired:
  sentences that cannot be spoken aloud in one breath are usually packed
  too densely.
- AGENTS.md 7.p now includes a "imagine the user plays the response
  through VOICEVOX" directive to shift Codex's register toward natural
  speakable Japanese.
- AGENTS.md 7.p further strengthened with three enforcement clauses:
  explicit trigger condition, explicit prohibition on skipping the tool,
  and a self-check directive. This flipped Codex from 0% self-initiated
  finalize calls to a working retry loop.

### Milestone
- **32 → 0 violations** (-100%) on the same progress report prompt,
  across three progressive rule-tightening steps. No Stop hook required.
  Confirms that the prompt-layer + MCP finalize gate hybrid is sufficient
  for v0.1.0 ship.

### Fixed
- Server identity `FastMCP("jp-lint")` → `FastMCP("jp_lint")` so the
  advertised name matches the config.toml key.
- `install.ps1` now registers the repo's `.venv` python executable
  instead of relying on system `python`, which lacked `mcp[cli]` and
  `pyyaml`. The server was silently ImportError-ing on startup.

### Added
- Phase A complete: MCP server (`jp-lint`) with `finalize` tool exposing three detection rules
  - Banned term detection (12 initial terms from `banned_terms.yaml`)
  - Bare identifier detection (code-like tokens not wrapped in backticks)
  - Too-many-identifiers-per-sentence detection (default limit: 2)
  - Code blocks and inline code are excluded from detection
- `src/ja_output_harness/rules.py` — pure-function lint engine
- `src/ja_output_harness/server.py` — FastMCP server exposing `finalize(draft)`
- `config/banned_terms.yaml` — single source of truth for rules
- `tests/test_rules.py` — 24 passing unit tests
- `tests/fixtures/{bad,good}_samples.md` — real-world samples
- `scripts/install.ps1` — registers MCP server in `~/.codex/config.toml`
- `scripts/uninstall.ps1` — removes MCP server registration
- Phase 0 complete: Repository skeleton (README, LICENSE, CI, docs)
