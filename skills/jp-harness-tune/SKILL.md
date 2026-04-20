---
name: jp-harness-tune
description: codex-jp-harness の jp_lint ルールを対話的にチューニングする。利用者が違反に対して無効化・severity 調整・独自禁止語の追加を判断したい時に、安易に緩めないよう判断支援を挟んでから codex-jp-tune CLI を実行する。
---

# jp-harness-tune — jp_lint ルールの対話チューニング

codex-jp-harness を運用していると「プロジェクト文脈では避けたくない語が検出される」「逆に固有の避けたい語が検出されない」というケースに遭遇する。このスキルは利用者の判断を対話で引き出し、結果を `codex-jp-tune` CLI で `~/.codex/jp_lint.yaml` に反映する。

**前提**: `codex-jp-harness` がインストール済みで、`codex-jp-tune` が PATH から実行できる（`uv sync` 済み、または `pip install -e .` 済み）。

## 呼び出し方

Codex（CLI / App）の入力欄で `$` を押してスキル一覧を開き、`$jp-harness-tune` を選択する。対象語がある場合は後続に自然文で記述する（例: `$jp-harness-tune slice を無効化したい`）。

## Step 1: 現状の把握

`codex-jp-tune show` を実行し、バンドル規則とユーザー override を merge した後の有効ルールを確認する。件数と、利用者が気にしている語の現在の severity だけを簡潔に示す。

```bash
codex-jp-tune show
```

## Step 2: 操作意図のヒアリング

次のうちどれかを確認する（対象語が先に提示されていても、操作内容は必ず確認する）:

1. **無効化** — バンドル済みの語を検出対象から外したい
2. **severity 調整** — 検出は続けたいが ERROR は厳しい → WARNING / INFO に緩めたい
3. **追加** — プロジェクト固有の避けたい語をルールに追加したい
4. **削除（add の取り消し）** — 以前 add した語を外したい
5. **確認のみ** — 今の状態を見たいだけ

## Step 3: 判断の支援

操作意図が「無効化」または「追加」の場合、**本当に必要か** を一度立ち止まって確認する。ルールを緩めることは Codex の日本語品質を下げる方向の変更なので安易に通さない。

判断の視点:

- **無効化**: その語は本当にプロジェクト文脈で避けられないか。類義の日本語表現で置き換えられないか（例: `slice` → `時間区間` で置き換え可能なら無効化せずルール維持）
- **severity 調整**: ERROR のままだと `finalize` が `ok: false` を返し続ける。WARNING に下げても advisories で通知は残る。INFO まで下げると実質スルー
- **追加**: その語がプロジェクト内の文書で頻出しているか。1〜2 回の出現なら追加せず、都度対処の方が軽い

利用者が「それでも緩めたい / 追加したい」と明確に意思表示したら Step 4 に進む。

## Step 4: 操作の実行

`codex-jp-tune` の該当サブコマンドを実行する:

```bash
codex-jp-tune disable <term>
codex-jp-tune enable <term>
codex-jp-tune set-severity <term> <ERROR|WARNING|INFO>
codex-jp-tune add <term> --suggest "<置換ガイド>" --severity <ERROR|WARNING|INFO> [--category <label>]
codex-jp-tune remove <term>
```

実行後、出力末尾に表示される override ファイルのパス（例: `~/.codex/jp_lint.yaml`）を利用者に伝える。

## Step 5: 反映確認

`codex-jp-tune show` を再度走らせ、操作前後の差分（件数 / 対象語の severity）を簡潔に示す。

**Codex の再起動は不要**（CLI / App どちらでも）。MCP サーバーはリクエストごとに override を読み直すため、次の `finalize` 呼び出しから反映される。

## Step 6: ロールバック方法の案内

変更を戻す手段を最後に伝える:

- `disable` の取り消し: `codex-jp-tune enable <term>`
- `set-severity` の取り消し: `codex-jp-tune set-severity <term> ERROR`
- `add` の取り消し: `codex-jp-tune remove <term>`
- 全てリセット: `~/.codex/jp_lint.yaml` を削除

## やらないこと

- `config/banned_terms.yaml` 本体の編集（バンドル規則の変更は PR で行う）
- Codex 本体（CLI / App）の再起動を促すこと（不要）
- 説明なしでの一括無効化（必ず Step 3 の判断支援を挟む）
