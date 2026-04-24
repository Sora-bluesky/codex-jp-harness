# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `ja-output-toggle off --full` / `on --full`: `jp-harness-mode` の切替に加えて `~/.codex/AGENTS.md` の管理ブロックを `.bak-toggle` に退避／復元する。素の `GPT-5.5` のような生モデルと比較する A/B 検証で必要だった
- `ja-output-stats scan-sessions`: `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` を走査して `role=assistant` の日本語応答を後付け検品する。`--since` / `--until`（`YYYY-MM-DD` 指定時は UTC 全日を含むよう `--until` を end-of-day 解釈）、`--include-archived`、`--output-jsonl` をサポート
- `ja-output-stats ab-report --source-path PATH`: 既定の lite / metrics jsonl の代わりに任意 jsonl を A/B バケットに使う。`scan-sessions --output-jsonl` の出力を直接 `ab-report` に流せる

### Changed
- README と `docs/OPERATIONS.md` に「素のモデル vs ハーネスあり」の A/B 手順を追加
- `ja-output-toggle status` が `AGENTS.md` 管理ブロックの有無と `.bak-toggle` の存在も表示するようになった

### Fixed
- `ja-output-toggle off --full` を 2 回目以降に実行したとき、`.bak-toggle` が既にあっても `AGENTS.md` に再挿入された管理ブロックを除去するようになった（再インストールで block が戻るシナリオのカバー）

## [0.5.0] - 2026-04-24

### Added
- `ja-output-toggle` CLI（`on` / `off` / `status` / `set` サブコマンド）— アンインストールせずにハーネスを切り替えて A/B 比較できるようにした
- `jp-harness-mode` に `off` 値を追加。両 OS の `Stop` / `SessionStart` hook が冒頭で即 `exit 0` する
- Codex App 利用時の切替用プロンプト例（`README.md` / `docs/INSTALL.md`）

### Changed
- ドキュメント主軸を `strict` モードから既定の `strict-lite` に切り替え（`docs/ARCHITECTURE.md` / `docs/HOOKS.md` / `docs/INSTALL.md` / `docs/OPERATIONS.md` / `AGENTS.md`）
- Codex `v0.124.0` で `codex_hooks` が GA 化された事実を反映（`docs/HOOKS.md` / `docs/INSTALL.md`）。`[features]` 宣言は `0.124+` で冗長だが本スクリプトは後方互換のため残す
- `README.md` の「+15%」を実測レンジ（`+0` 〜 `+60%`）に更新
- `docs/DEPRECATION.md` の uninstall 自動化済み項目の記述を `v0.3.4` 実装済みに整合

## [0.4.2] - 2026-04-22

`jp-harness-lite.jsonl` への append を Stop hook（`Add-Content` / 直接 `open('a')`）から外し、`metrics.record_lite` 経由で `_rotate_lock` 保護下に集約。Windows で `O_APPEND` が atomic でない問題に対する予防策（gpt-5.4 review 2 ラウンドでクリア）。

### Fixed
- Stop hook の lite jsonl append が Windows で非アトミックになり得る race を、`metrics.record_lite` への集約で解消
- `ja-output-stats --source lite` が rotated archive (`.1.jsonl`) を読まなかったのを修正
- hook の rules_cli 引数を `--session=<value>` / `--mode=<value>` 形式に変更（`-` 始まりの session id 誤認防止）

### Added
- `metrics.record_lite()` — `_rotate_lock` + `_maybe_rotate` を再利用する lite jsonl 専用書き込み関数（lock 取得失敗時は drop、`record()` の best-effort と意図的に divergence）
- `rules_cli --append-lite STATE_FILE --session ID --mode MODE` — hook が一度の呼び出しで lint と append を済ませるための optional フラグ群
- 並行 append レーステスト（N=32）と CLI 統合テスト

## [0.4.1] - 2026-04-22

v0.4.0 の実測 dogfood（n=21、ok 率 23.8%、Wilson 95% CI [10.6%, 45.1%]）を受け、default を `lite` から `strict-lite` に変更。README をエンドユーザー向けに簡素化し、開発者向け内容は `DEVELOPERS.md` へ分離。

### Changed
- install 自動判定の既定を `strict-lite` に変更（ERROR 時に Codex が continuation で自己修正、追加 output token は基本 0）
- README をエンドユーザー向けに全面刷新
- `DEVELOPERS.md` を新設し、モード比較・アーキテクチャ・dogfood 手順を集約
- 過去リリースの CHANGELOG エントリを簡素化

## [0.4.0] - 2026-04-21

MCP `finalize` gate（output 3× overhead）を opt-in に降格し、Stop hook による事後検品を中心とした 3 モード体制に再設計。

### Added
- 3 インストールモード: `lite`（Stop hook で検品のみ）/ `strict-lite`（ERROR 時に continuation で自己修正）/ `strict`（v0.3.x 互換の MCP gate）
- `ja-output-stats ab-report` サブコマンド（Wilson 95% CI による A/B 比較）
- SessionStart hook が lite 違反も再教育対象にするよう拡張
- 消費カーソル `jp-harness-cursor.json`（atomic rename で race 回避）
- install スクリプトの `--mode` / `-Mode` 指定と Codex CLI 検出による自動判定

### Fixed
- Codex 0.122 の feature gate に対応（install で `codex features enable codex_hooks` を実行）
- SessionStart hook の tail 切り捨てと race 消失を cursor ベースで解消
- strict-lite の continuation 無限ループを `stop_hook_active` ガードで防止
- install / uninstall の AGENTS.md ブロック置換を BEGIN/END マーカー付きに

### Known Issues
- Codex App では `lite` / `strict-lite` の hook が発火しない場合あり（Codex 側の experimental feature allowlist 制約）。App 単独環境では install が自動で `strict` を選択

## [0.3.0] - 2026-04-21

**Breaking**: 商標非依存の名称にリネーム。

### Changed
- リポ: `codex-jp-harness` → `ja-output-harness`
- Python パッケージ: `codex_jp_harness` → `ja_output_harness`
- CLI: `codex-jp-tune` → `ja-output-tune`、`codex-jp-stats` → `ja-output-stats`
- README 先頭に非公式ツールであることを明記する disclaimer を追加

### Notes
- 移行手順: 旧パッケージをアンインストール → `uv sync` で新パッケージ導入 → install スクリプト再実行 → Codex 再起動

## [0.3.1 - 0.3.8] - 2026-04-21

外部レビュー（gpt-5.4）指摘の修正パッチ群。

### Added
- metrics schema v2（`rule_counts` フィールド）
- `ja-output-stats show` のルール分布と fast-path miss 診断
- `pr_issue_number` 検出ルール（`PR #123` の裸書き）
- `JA_OUTPUT_HARNESS_USER_CONFIG` 環境変数（旧名称は後方互換）
- rules cache と metrics rotation の排他制御

### Fixed
- `discover --file` の cp932 ログ対応
- `install.sh --enable-hooks` の Python 解決を複数候補化
- uninstall の安全性（絶対パス判定、条件付き `codex_hooks` 削除）
- `set-severity` の user-added term 反映漏れと atomic write
- Stop hook の tool 名判定を完全一致に
- README / docs の実装乖離を一括整合

## [0.2.x] - 2026-04-18 〜 2026-04-21

fast-path 拡張と discover / tune 周辺の UX 改善。

### Added
- `ja-output-tune` CLI（add / remove / disable / set-severity / discover）と user-local override（0.2.0）
- `rules.apply_backtick_fix`: 裸識別子を fast-path で自動バッククォート化（0.2.22）
- `ja-output-stats overhead` サブコマンド
- `discover.DEFAULT_ALLOWLIST` に標準技術語 25 語を追加（`stdin` / `pester` / `grep` 等）

### Changed
- fast-path 対応範囲を `banned_term` のみから `bare_identifier` / `too_many_identifiers` / `sentence_too_long` まで拡大
- `jp-harness-tune` スキルの対話フローを 8 ステップ walkthrough に整備

## [0.1.x] - 2026-04-17

初版。MCP `finalize` server、基本的な禁止語 / 識別子検出ルール、install / uninstall スクリプト。
