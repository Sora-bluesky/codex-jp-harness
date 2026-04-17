# 悪い出力サンプル集

実際に Codex が生成した日本語技術報告のうち、品質ゲートで弾くべきもの。

## サンプル1: slice/parity/squash 混在

やったこと

復元を完了し、TASK-291 の PR #495 を ready 化して squash マージしました。ローカルも main に早送り同期し、旧ブランチは掃除済みです。

## サンプル2: 英語識別子過多

TASK-306 を codex/task306-stdin-parity-20260417 で開始し、prompt_transport=stdin を受け入れて pane dispatch で send-paste 経由に流す実装を入れました。変更は winsmux-core.ps1, settings.ps1, winsmux-bridge.Tests.ps1 です。

## サンプル3: done/active 切替

外部計画を更新し、TASK-291 を done、TASK-306 を active に切り替え、ROADMAP.md を再生成しました。

## サンプル4: バッククォート抜け

現在ブランチは codex/task306-stdin-parity-20260417 です。

## サンプル5: 名詞句の過連続（Phase B 対象）

DesktopDigestItem の producer parity をそのままベストプラクティスで進めました。
