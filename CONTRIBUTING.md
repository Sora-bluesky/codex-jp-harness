# Contributing

本プロジェクトへのコントリビュートを歓迎します。

## 前提

本ハーネスは**暫定対策**です。OpenAI 公式が Codex CLI の日本語対応を実装した時点で archive されます。大規模な機能追加（形態素解析ベースの高精度検出など）の提案は、公式対応の進捗状況と照らして判断させてください。

## バグ報告

1. [Issues](https://github.com/sora-bluesky/codex-jp-harness/issues) を開く
2. `bug_report` テンプレートに従って記述
3. 再現手順、期待動作、実際の動作、環境情報（OS, Python version, Codex version）を含める

## 機能提案

1. [Issues](https://github.com/sora-bluesky/codex-jp-harness/issues) で `feature_request` テンプレートを使用
2. なぜその機能が必要か（Why）を明確に
3. 代替案の検討結果も記載

## Pull Request

1. Fork してトピックブランチを切る
2. テストを追加（`tests/` に fixture ベースで）
3. `uv run pytest` がすべて通ることを確認
4. コミットメッセージは英語で、[Conventional Commits](https://www.conventionalcommits.org/) に沿う
5. PR を作成、`PULL_REQUEST_TEMPLATE` に従って記述

## 開発環境セットアップ

```powershell
git clone https://github.com/sora-bluesky/codex-jp-harness.git
cd codex-jp-harness
uv sync
uv run pytest
```

## 禁止語リストの追加

新しい禁止語を提案する場合は、以下を PR に含める:
- 追加する語と suggest（言い換え候補）
- その語がなぜ日本語として読みづらいかの根拠
- 誤検知の可能性の検討

## ライセンス

コントリビュートされたコードは MIT License で公開されることに同意するものとします。
