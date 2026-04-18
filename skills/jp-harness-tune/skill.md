---
name: jp-harness-tune
description: >
  codex-jp-harness の jp_lint ルールを対話的にチューニングするスキル。
  プロジェクト固有の文脈で禁止語を無効化・severity 調整・追加する判断を支援し、
  codex-jp-tune CLI 経由で `~/.codex/jp_lint.yaml` に反映する。
  「jp-harness-tune」「禁止語を無効化」「jp_lint 調整」「severity 下げて」で呼び出される。
argument-hint: "[term] (任意。操作対象の語を先に渡すと対話を省略できる)"
---

# jp-harness-tune — jp_lint ルールの対話チューニング

codex-jp-harness をインストールして運用していると、プロジェクト文脈では避けたくない語が検出される、あるいは逆に固有の禁止語を追加したい、というケースに遭遇する。このスキルは利用者の判断を対話で引き出し、結果を `codex-jp-tune` CLI で `~/.codex/jp_lint.yaml` に反映する。

**前提**: `codex-jp-harness` がインストール済みで、`codex-jp-tune` コマンドが PATH から実行できる（`uv sync` 済み環境 or `pip install -e .` 済み）。

## 入力

- `$ARGUMENTS`: 操作対象の語（例: `slice`, `handoff`）。省略時は対話でヒアリングする。

## Step 1: 現状の把握

まず `codex-jp-tune show` を実行して、いま効いているルール（バンドル + user-local override を merge した結果）を取得する。結果は利用者にそのまま見せず、件数と対象語の有無のみサマリで提示する。

```bash
codex-jp-tune show
```

`$ARGUMENTS` が与えられていれば、その語が show 結果に含まれるか、含まれる場合の severity / category を控えておく。

## Step 2: 操作意図のヒアリング

次のうちどれに該当するかを利用者に確認する（`$ARGUMENTS` で対象が決まっていても、操作内容は必ず確認する）。

1. **無効化** — バンドル済みの語を外したい（例: プロジェクト用語として常用しているので検出してほしくない）
2. **severity 調整** — 検出は続けたいが ERROR は厳しすぎる → WARNING / INFO に緩める
3. **追加** — プロジェクト固有の避けたい語をルールに追加したい
4. **削除（add の取り消し）** — 以前 add した語を外したい
5. **確認のみ** — 今の状態を見たいだけ

## Step 3: 判断の支援

操作意図が「無効化」または「追加」の場合、**本当に必要か** を一度立ち止まって確認する。ルールを緩めること自体は Codex の日本語品質を下げる方向の変更なので、安易に通さない。

判断の視点:

- **無効化**: その語は本当にプロジェクト文脈で避けられないか？ 類義の日本語表現で置き換えられないか？（例: `slice` → `時間区間` で置き換え可能なら無効化せずルール維持）
- **severity 調整**: ERROR のままだと `finalize` が `ok:false` を返し続ける。WARNING に下げても advisories で通知は残る。INFO まで下げると実質スルー
- **追加**: その語がプロジェクト内の文書で頻出しているか？ 1〜2 回の出現なら追加せず、Codex のプロンプトで都度対処する方が軽い

利用者の回答で「それでも緩めたい / 追加したい」と明確になったら Step 4 に進む。

## Step 4: 操作の実行

`codex-jp-tune` の該当サブコマンドを実行する。

```bash
# 1. 無効化
codex-jp-tune disable <term>

# 2. severity 調整
codex-jp-tune set-severity <term> <ERROR|WARNING|INFO>

# 3. 追加
codex-jp-tune add <term> --suggest "<置換ガイド>" --severity <ERROR|WARNING|INFO> [--category <label>]

# 4. 削除
codex-jp-tune remove <term>

# 無効化の取り消し（誤って disable した場合）
codex-jp-tune enable <term>
```

実行後、出力末尾に表示される override ファイルのパスを利用者に伝える（例: `~/.codex/jp_lint.yaml`）。

## Step 5: 反映確認

変更が効いているかを `codex-jp-tune show` で再確認する。操作前後の差分（件数 / 該当語の severity）を簡潔に提示する。

**Codex CLI の再起動は不要**。MCP サーバーはリクエストごとに override を読み直すため、次の `finalize` 呼び出しから反映される。

## Step 6: ロールバック方法の案内

変更を戻したい場合の方法を最後に案内する:

- `disable` の取り消し → `codex-jp-tune enable <term>`
- `set-severity` の取り消し → `codex-jp-tune set-severity <term> ERROR`（元の severity に戻す）
- `add` の取り消し → `codex-jp-tune remove <term>`
- 全てリセット → `~/.codex/jp_lint.yaml` を削除

## 呼び出し判定ルール

以下のいずれかに該当したら発動:

- 「jp-harness-tune」「codex-jp-tune」「jp_lint 調整」「ルール調整」
- 「禁止語を無効化」「severity 下げて」「警告にして」
- `finalize` で同じ語が繰り返し検出されて利用者が困っている時（提案として発動）

## やらないこと

- `config/banned_terms.yaml` 本体の編集（バンドル規則の変更は PR で行う）
- Codex CLI 本体の再起動（不要）
- 説明なしでの一括無効化（必ず Step 3 の判断支援を挟む）
