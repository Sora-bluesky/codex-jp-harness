# Architecture

本ドキュメントは codex-jp-harness の設計判断を記録する。実装詳細は更新時に追記する。

## 全体像

```
┌────────────┐   (1) draft      ┌──────────────┐
│            │ ───────────────> │              │
│   Codex    │                  │  jp-lint     │
│    CLI     │ <──────────────  │  MCP Server  │
│            │   (2) verdict    │              │
└─────┬──────┘                  └──────────────┘
      │
      │ (3) final response (only if ok:true)
      ▼
┌────────────┐
│   User     │
└────────────┘

後方検知:
┌────────────┐   (A) turn end   ┌──────────────┐
│   Codex    │ ───────────────> │  Stop hook   │
└─────┬──────┘                  └──────┬───────┘
      │                                │ (B) log violation
      │                                ▼
      │                         ┌──────────────┐
      │                         │  violations  │
      │                         │   .jsonl     │
      │                         └──────┬───────┘
      │ (D) re-education               │ (C) read on next session
      ▼                                ▼
┌────────────────────────────────────────────┐
│  SessionStart hook injects re-education    │
└────────────────────────────────────────────┘
```

## Tier 比較（なぜ Tier 2 を選んだか）

| Tier | 手段 | 実装コスト | UX | 強制力 | Codex 機能維持 |
|---|---|---|---|---|---|
| 1 | Stop hook + 次ターン注入 | 半日 | △（違反版も見える） | 中 | 完全 |
| **2** | **MCP finalize ゲート** | **1〜2日** | **○（クリーン版のみ）** | **中〜高** | **完全** |
| 3 | 外部ラッパースクリプト | 1〜2週 | ◎（完全透過） | 高 | 部分喪失 |
| 4 | TUI プロキシ | 数週 | ◎ | 最高 | 完全 |

Tier 2 + Tier 1 のハイブリッド（本実装）: 実装 2〜3 日で違反の 95%+ を同一ターン内で自動修正できる ROI 最適点。

## 主要コンポーネント

### src/codex_jp_harness/server.py
Codex から呼ばれる MCP サーバー本体。`finalize(draft)` ツールを公開する窓口。

### src/codex_jp_harness/rules.py
Lint ロジック。文字列を受け取り違反リストを返す純関数。副作用を持たせない。

### config/banned_terms.yaml
禁止語・閾値の単一情報源（Single Source of Truth）。ここを書き換えればルール変更が完結する。

### src/codex_jp_harness/hooks/
PowerShell スクリプト（Stop, SessionStart）。Codex の hook 機構から呼ばれる。

## 設計原則

1. **単一情報源**: 禁止語定義は `banned_terms.yaml` 1箇所のみ。`SKILL.md` からも参照する
2. **疎結合**: `rules.py` は MCP プロトコルを知らない純関数
3. **Graceful degradation**: MCP サーバー停止時は自己チェックで応答継続
4. **観測可能性**: `stats.json` に呼び出し統計を自動記録、月次レビュー可能
5. **アンインストール容易性**: `docs/DEPRECATION.md` で1コマンド相当のアンインストール手順を提供

## トレードオフ

- **トークン消費 +30〜50%**: 品質担保とのトレードオフ。月100報告で +$0.50 程度で許容範囲
- **形態素解析未採用**: 依存増・起動時間増を避けるためヒューリスティックで妥協。fugashi は将来拡張
- **Windows 優先**: ユーザー環境優先。macOS/Linux は将来拡張

## 公式対応との関係

本ハーネスは暫定対策。以下の公式機能が揃った時点で不要になる:
- Codex CLI 本体での日本語自然化
- Pre-response hook 機構
- `PreSkillUse` / `PostSkillUse` hook（[Issue #17132](https://github.com/openai/codex/issues/17132)）

詳細は [`DEPRECATION.md`](DEPRECATION.md) 参照。
