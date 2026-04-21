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
6. **候補抽出（discover）** — 最近の Codex 出力を見せるので、未登録の生英語候補を抽出して追加判断したい

## Step 2b: discover フロー（意図 6 の場合）

利用者が 6 を選んだ場合のみ、このフローを回す。他の意図なら Step 3 へ進む。

### 2b-1. 入力を受け取る

次のいずれかで Codex 出力を取得する:

- **paste 方式**: 「直近の Codex 応答を貼ってください（終端は空行 2 回）」と案内し、paste 内容を一時ファイルに保存
- **file 方式**: ログや handoff メモのパスを指定してもらう（例: `.claude/local/operator-handoff.md`）

### 2b-2. 候補を抽出

```bash
codex-jp-tune discover --file <path> --top 20
# もしくは stdin 経由:
cat <path> | codex-jp-tune discover --stdin --top 20
```

出力は TSV 4 列: `count \t term \t 推奨言い換え \t 代表文脈`。

### 2b-3. 1 語ずつヒアリング

抽出された候補を上から順に提示し、1 語ずつ以下を確認する:

- **追加するか**（Y/N）。UI ラベルや製品名、固有名詞（例: `Back to Code`, `Ports`）は N が基本
- **推奨言い換え**: `suggest` 列の提案をそのまま採用するか、別案を書いてもらう。提案が空欄のケースは必ず利用者に入力を促す
- **severity**: 既定 ERROR で良いか。一般名詞の wrapper / helper 等は WARNING で十分な場合もある

1 語ごとに合意が取れた時点で次を実行:

```bash
codex-jp-tune add <term> --suggest "<言い換え>" --severity <ERROR|WARNING|INFO>
```

### 2b-4. 反映確認とロールバック案内

一括追加が終わったら `codex-jp-tune show` で反映を確認する。取り消したい語があれば `codex-jp-tune remove <term>` で戻せる旨を伝える。

Codex の再起動は不要（MCP サーバーは override を毎回読み直す）。

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
