# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
  1. `~/.codex/AGENTS.md` から「日本語技術文の品質ゲート (codex-jp-harness)」セクションを手動削除
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
- `pip install codex-jp-harness` のみの利用者は wheel に `skills/` が
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

v0.1.x からの大きな拡張。禁止語を倍増し、severity 階層で「止めるべき違反」と「参考情報」を分離し、利用者側で規則を調整できる仕組み (user-local override + `codex-jp-tune` CLI + Claude Code skill) を追加した。

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
  `$CODEX_JP_HARNESS_USER_CONFIG` → `$XDG_CONFIG_HOME/codex-jp-harness/jp_lint.yaml`
  → `~/.codex/jp_lint.yaml`。存在しなければバンドル値がそのまま使われる。
- **`codex-jp-tune` CLI**: ユーザー設定を対話的に編集する console script。
  サブコマンドは `path` / `show` / `disable` / `enable` / `set-severity` /
  `add` / `remove`。pyyaml のみ依存。
- **`jp-harness-tune` Claude Code skill**: `skills/jp-harness-tune/skill.md`
  を同梱。ルールを安易に緩めないよう、無効化・severity 調整・追加の前に
  必ず判断支援ステップを挟み、`codex-jp-tune` を実行する。
  `~/.claude/skills/` に配置すると `/jp-harness-tune` で呼べる。
- **README「違反検出時の対処法」section**: severity 三段階の意味、
  user-local override の yaml 例、`codex-jp-tune` の使い方、典型的な
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

初回公開リリース。Zenn 記事 [Codex の日本語を救ったのは「ずんだもん」だった](https://zenn.dev/sora_biz/articles/codex-jp-harness-milestone) と同日公開。

### Documented
- Zenn writeup published at
  https://zenn.dev/sora_biz/articles/codex-jp-harness-milestone
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
- `src/codex_jp_harness/rules.py` — pure-function lint engine
- `src/codex_jp_harness/server.py` — FastMCP server exposing `finalize(draft)`
- `config/banned_terms.yaml` — single source of truth for rules
- `tests/test_rules.py` — 24 passing unit tests
- `tests/fixtures/{bad,good}_samples.md` — real-world samples
- `scripts/install.ps1` — registers MCP server in `~/.codex/config.toml`
- `scripts/uninstall.ps1` — removes MCP server registration
- Phase 0 complete: Repository skeleton (README, LICENSE, CI, docs)
