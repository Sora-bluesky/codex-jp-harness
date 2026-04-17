# codex-jp-harness 引き継ぎメモ (`HANDOFF.md`)

> **最終更新**: 2026-04-17（v0.1.2 リリース直後）
> **次セッション起動位置**: `C:\Users\komei\Documents\Projects\apps\codex-jp-harness`
> **公開 URL**: https://github.com/Sora-bluesky/codex-jp-harness
> **解説記事**: [Codex の日本語を救ったのは「ずんだもん」だった](https://zenn.dev/sora_biz/articles/codex-jp-harness-milestone)

## プロジェクト概要

Codex CLI の日本語出力を MCP 検品ゲート (`mcp__jp_lint__finalize`) で品質担保する**暫定ハーネス**。OpenAI が Codex CLI に Claude Code 水準の日本語対応を公式実装するまでの繋ぎ。公式対応が出揃った時点で archive する前提で設計されている。

## 現在のバージョン

- **最新リリース**: [v0.1.2](https://github.com/Sora-bluesky/codex-jp-harness/releases/tag/v0.1.2) (2026-04-17)
- **main ブランチ**: 保護済み（PR 必須、CI 5 チェック必須、linear history、force push 禁止）

### リリース履歴

| バージョン | 内容 |
|---|---|
| v0.1.0 | 初回公開（MCP finalize サーバー + 4 検出ルール + 2 インストーラー） |
| v0.1.1 | 7.p トリガー範囲拡張（学習ノート・ドキュメント対応）+ リポ直下 `AGENTS.md` + README ディレクトリツリー |
| v0.1.2 | `agents_rule.md` 汎用化（スタンドアロン形式に刷新）+ `冪等` を banned_terms に追加 + README の平易化 |

## 完了した実装

### Phase 0: リポジトリ初期化

- `README.md` / `LICENSE` (MIT) / `CHANGELOG.md` / `CONTRIBUTING.md` / `pyproject.toml`
- `.gitattributes` / `.gitignore` / `.gitleaksignore`
- GitHub Actions: pytest matrix (Win/Linux × Py 3.11/3.12) + gitleaks
- Issue / PR テンプレート
- docs/ (ARCHITECTURE / INSTALL / OPERATIONS / DEPRECATION)
- リポ直下 `AGENTS.md`（Codex・Claude Code の dogfooding 用）

### Phase A: 基本検出実装

- **MCP サーバー** (`src/codex_jp_harness/server.py`) — FastMCP, `finalize(draft)` ツール公開
- **Lint エンジン** (`src/codex_jp_harness/rules.py`) — 純関数
- **検出ルール 4 種**:

| ルール | 対象 | 閾値 |
|---|---|---|
| `banned_term` | 禁止語検出 | 13 語 |
| `bare_identifier` | バッククォート抜けコード識別子 | `._/-` を含むトークン |
| `too_many_identifiers` | 1 文あたり識別子過多 | 2 個超で違反 |
| `sentence_too_long` | 文の長さ超過 | 80 文字超（識別子含む場合 50 文字超） |

- **禁止語 13 語**: `slice`, `parity`, `done`, `active`, `ready`, `squash`, `dispatch`, `handoff`, `regression`, `fail-close`, `fast-forward`, `contract drift`, `冪等`
- **単一情報源**: `config/banned_terms.yaml` + `config/agents_rule.md`
- **インストーラー**: `scripts/install.{ps1,sh}` + `scripts/uninstall.{ps1,sh}`
  - `-AppendAgentsRule` / `--append-agents-rule` で `~/.codex/AGENTS.md` 自動追記
  - Git Bash の MSYS パスを `cygpath` で自動変換
- **テスト**: 30 件（all passing）
- **fixture**: 実 Codex 出力の 3 段階（32 / 4 / 0 違反）

### 公開物

- Zenn 記事公開（v0.1.0 と同日）
- X 紹介ポスト（ツリー型、リプで Zenn + GitHub URL）

## 未実装 / v0.2.0 候補

### Phase C: 呼び忘れ検知 + 再教育ループ（優先度 中）

**目的**: Codex が `mcp__jp_lint__finalize` を呼び忘れた場合の runtime 後方検知。現状はプロンプト層だけで 100% 達成できているため、**保険的役割**。

**仕組み**:

1. Codex がターン終了 → Stop hook 発火
2. 直近 assistant メッセージを session log から取得
3. 日本語技術文パターンを検出 + 同ターン内の `finalize` 呼び出しを照合
4. 呼び忘れ検出時:
   - `~/.codex/.jp-lint-violations.jsonl` に記録
   - stderr に赤字警告
5. 次セッション起動時、SessionStart hook がログ読取
6. 過去 24 時間以内の違反があれば再教育プロンプトを system context に注入

**実装場所（予定）**:

- `src/codex_jp_harness/hooks/jp_lint_stop.ps1`
- `src/codex_jp_harness/hooks/jp_lint_sessionstart.ps1`
- `config/hooks.example.json`
- `scripts/install.{ps1,sh}` に hook 登録処理を追加

**既知の制約**:

- [Issue #17532](https://github.com/openai/codex/issues/17532): Codex の hook は repo-local `config.toml` で動かない。グローバル `~/.codex/config.toml` にのみ登録する
- Codex CLI のバージョンアップで hook 仕様が変わる可能性

**実装判断**: 現状のプロンプト層だけで十分機能しているため、優先度は下がった。ただし他ユーザー環境では筆者の 7.a〜7.o 相当のルールがなく効果が劣化する可能性があるため、そちらを補強する手段として有用。

### Phase B: 名詞句過連続検出（優先度 中）

**目的**: 「A の B の C の D」のような名詞連鎖をヒューリスティックで検出。

**検出パターン 3 種**:

1. **の-chain**: 「の」が 3 回以上連続
2. **英語識別子連鎖**: 英語識別子が句読点・動詞なしで 3 つ以上連結
3. **カタカナ長連鎖**: カタカナ語が 3 つ以上連結

**実装場所（予定）**:

- `config/banned_terms.yaml` に `noun_chain:` セクション追加
- `src/codex_jp_harness/rules.py` に `detect_noun_chain()` 追加
- `noun_chain_allowlist` 機能（固有名詞の長い名前を除外）

**精度向上オプション**:

- `fugashi` (MeCab Python) を追加導入し、連続名詞トークン数ベースで高精度化
- 現状のヒューリスティックで誤検知率 10% 超になったら検討

**実装判断**: 現状の出力では名詞句過連続のパターンがほぼ出ていない（VOICEVOX directive が既に抑制している）。とはいえ Codex の挙動変化に備えて preventive に実装する価値はある。

### その他 v0.2.0 候補

| 項目 | 優先度 | 備考 |
|---|---|---|
| 曖昧参照語の `banned_terms.yaml` 化 | 中 | 「対象テスト」「広い確認」等。false positive 設計要検討 |
| 日本語スタイルルール同梱 | 中 | 筆者の 7.a〜7.o 相当を汎用化した `config/jp_style_rules.md` を新設。`--append-full-rules` フラグで opt-in |
| URL / markdown link の誤検出修正 | 中 | 既知問題: markdown リンク `[text](url)` 内 URL が bare_identifier と誤検知。Zenn 記事 lint 時に発覚 |
| 統計収集 | 低 | `stats.json` の自動更新。呼び出し回数 / retry 率 / 違反種別頻度 |
| Python エントリーポイント | 低 | `pyproject.toml` に `[project.scripts] codex-jp-harness-server = "..."` 追加 |
| 他 AI CLI 対応 | 低 | Claude Code への移植検討 |
| 自動更新通知 | 低 | インストール済みユーザーに新版通知する仕組み |

## 撤去トリガー（archive 条件）

以下のいずれかが公式リリースされた時点で本ハーネスは役目を終える:

1. Codex CLI 本体が日本語 register 切替を標準装備
2. Pre-response hook（出力前 postprocess）の公式機構
3. `PreSkillUse` / `PostSkillUse` hook ([Issue #17132](https://github.com/openai/codex/issues/17132))

### 観測方法（月 1 回）

```bash
gh search issues --repo openai/codex "japanese OR i18n OR 日本語"
gh issue view 17132 --repo openai/codex
gh release list --repo openai/codex --limit 5
```

撤去手順は [`docs/DEPRECATION.md`](docs/DEPRECATION.md) を参照。

## 重要ファイル

```
codex-jp-harness/
├── AGENTS.md                      リポ作業用規約（dogfooding 明記）
├── HANDOFF.md                     このファイル
├── CHANGELOG.md                   リリース履歴
├── README.md                      導入 2 パターン + ディレクトリ構成
├── pyproject.toml                 version = "0.1.2"
├── src/codex_jp_harness/
│   ├── __init__.py                __version__
│   ├── server.py                  FastMCP, finalize ツール定義
│   └── rules.py                   純関数 lint エンジン
├── config/
│   ├── banned_terms.yaml          禁止語 13 + 閾値（単一情報源）
│   └── agents_rule.md             ユーザーの AGENTS.md に追記されるルール本文
│                                  (v0.1.2 でスタンドアロン形式に刷新)
├── scripts/
│   ├── install.{ps1,sh}           -AppendAgentsRule / --append-agents-rule
│   └── uninstall.{ps1,sh}
├── tests/
│   ├── test_rules.py              30 件
│   └── fixtures/
│       ├── codex_actual_output.txt       32 violations (baseline)
│       ├── codex_after_voicevox.txt       4 violations
│       ├── codex_after_strengthened.txt   0 violations
│       └── bad_samples.md / good_samples.md
└── docs/
    ├── ARCHITECTURE.md            設計判断・Tier 比較
    ├── INSTALL.md                 パターン A（Codex 丸投げ）/ B（手動）
    ├── OPERATIONS.md              運用監視 + 公式対応の観測
    └── DEPRECATION.md             撤去手順
```

## 運用のポイント

### リリースフロー

1. 機能追加は feature branch で PR
2. CI 全通過後 `squash merge`
3. リリース時:
   1. `release/vX.Y.Z` ブランチ作成
   2. CHANGELOG の `[Unreleased]` → `[X.Y.Z] - YYYY-MM-DD`
   3. `pyproject.toml` + `src/codex_jp_harness/__init__.py` の version 更新
   4. PR → merge
   5. `gh release create vX.Y.Z --target main --notes-file <notes>`

### ブランチ保護の事実

- `main` は保護済み、直 push 不可
- 必須 CI: `test (ubuntu-latest, 3.11)`, `test (ubuntu-latest, 3.12)`, `test (windows-latest, 3.11)`, `test (windows-latest, 3.12)`, `scan`（計 5）
- PR 必須（approval 0 でも merge 可）
- Linear history 必須
- force push / 削除禁止
- admin は緊急時 bypass 可

### dogfooding

このリポ自身で作業する Codex / Claude Code は、このツールの lint ルールに従う。グローバル `~/.codex/AGENTS.md` + リポ直下 `AGENTS.md` の両方が適用される。

## 次セッション起動時のチェックリスト

1. `git status` で未コミット変更の有無確認
2. `git log --oneline -5` で最新コミット確認
3. `gh pr list` で open PR 確認
4. `gh release view v0.1.2` で最新リリース確認
5. `CHANGELOG.md` の `[Unreleased]` セクション確認
6. この `HANDOFF.md` を読んで背景把握

### 次の一手の候補（優先度順）

1. **URL / markdown link の誤検出修正** — dogfooding で発覚済みの既知問題。影響小さいがアクセシブル
2. **Phase B（名詞句検出）** — ヒューリスティック 3 パターン + fugashi 検討
3. **曖昧参照語の自動検出** — false positive 設計込み
4. **Phase C（Stop hook）** — プロンプト層で既に十分なので保険的
5. **日本語スタイルルール同梱** — 他ユーザーが full 構成で使えるように

## 関連リンク

- GitHub: https://github.com/Sora-bluesky/codex-jp-harness
- Zenn 記事: https://zenn.dev/sora_biz/articles/codex-jp-harness-milestone
- OpenAI Codex CLI: https://github.com/openai/codex
- 関連 Issue:
  - [#17132](https://github.com/openai/codex/issues/17132) — `PreSkillUse` / `PostSkillUse` hooks（未実装、Phase C 関連）
  - [#17532](https://github.com/openai/codex/issues/17532) — hook が repo-local config で動かない
  - [#18189](https://github.com/openai/codex/issues/18189) — AGENTS.md マージ動作の不明確性
