# ja-output-harness

Codex のフック（Stop / SessionStart）を使って、チャット応答の日本語を自動で検品・修正するハーネスです。

Codex でバイブコーディングしていると、チャット応答の日本語に英単語が裸で混ざり、技術比喩が助詞に溶け込み、1 文が長すぎる — ということが頻発します。このプロジェクトはそれを機械的に封じます。インストール後の追加操作は不要です。

> [!WARNING]
> **Disclaimer**
>
> 本プロジェクトは OpenAI による支援・承認・提携を受けていない**非公式のコミュニティツール**です。「Codex」「ChatGPT」等は OpenAI の商標であり、本ハーネスが検査対象とする CLI / アプリを客観的に指す目的でのみ言及しています。

## 仕組み

Codex 0.120 以降が公開した公式の拡張ポイント（**Stop hook** と **SessionStart hook**）を使います。Codex 本体や OpenAI 側のコードは一切書き換えません。

1. **Stop hook（ターン終了時）** — Codex が日本語応答を返した瞬間、ハーネスが応答文字列を受け取り、同梱の Python ロジック（`ja_output_harness.rules_cli`）で違反を検出します。
2. **違反があれば自己修正**（strict-lite モード） — ハーネスが Codex に `{"decision": "block", "reason": "..."}` を返します。Codex は**同じターン内でもう 1 回推論を回して違反を自動的に言い直します**（Codex 側ではこの再試行が「continuation」と呼ばれます）。
3. **取りこぼしは次回に繰越** — 修正しきれなかった違反は `~/.codex/state/jp-harness-lite.jsonl` に追記され、**SessionStart hook** が次のセッション開始時に「前回こういう違反があったので気をつけて」と短い再教育プロンプトを Codex に挿入します。

検品ロジックは Codex の LLM 呼び出しの **外側** で走るため、応答トークンには 1 byte も足しません。追加の API コールも外部通信もありません。違反があって Codex が自動で言い直すとき（上の 2.）だけ、追加の推論 1 回分が発生します。違反ゼロのターンは増分ゼロ、違反ありのターンだけ `continuation` 1 回分が乗る形です。ターン平均の増分は初手の違反率に比例し、ドッグフードでの実測では `+0` 〜 `+60%` の幅に収まっています（`config/banned_terms.yaml` の調整で下がります）。

使うファイルは全てローカル。install スクリプトが触るのは `~/.codex/` 配下のみ（Codex 本体の設定と同じ場所）で、新規ファイルと、既存ファイルへの「管理ブロック追記」が混在します。

```text
~/.codex/
├── AGENTS.md                         # 既存に追記（BEGIN/END マーカーで囲まれた管理ブロック）
├── config.toml                       # 既存に追記（codex_hooks feature を有効化。strict モード時のみ [mcp_servers.jp_lint] も追加）
├── hooks.json                        # 新規、または既存の hooks 設定に Stop / SessionStart のエントリを追加
├── skills/jp-harness-tune/SKILL.md   # 新規（tune スキルの定義ファイル）
└── state/
    ├── jp-harness-mode               # 新規（現在のモード名を書いた 1 行のマーカー）
    ├── jp-harness-lite.jsonl         # 実行時に新規 → 検品結果が 1 ターンごとに追記される
    └── jp-harness-cursor.json        # 実行時に新規（SessionStart hook が消費位置を記録）
```

アンインストールは上記のうち BEGIN/END マーカーの管理ブロックと、ハーネス専用の新規ファイルだけを掃除します。手書きした他の設定には触れません。ソースは [hooks/](hooks/) と [src/ja_output_harness/](src/ja_output_harness/) で読めます。

## 誰に向いているか

- Codex（CLI または App）でバイブコーディングしている人
- チャット応答に英単語が素のまま混ざる日本語に不満を感じている人
- プロンプトで何度注意しても直らない挙動を、仕組みで封じたい人

## 必要なもの

- **Codex CLI**（`codex` コマンドが PATH 上で使えること、バージョン 0.120 以降）
  - install スクリプトが hook 機能の有効化（`codex features enable codex_hooks`）に使うため、Codex App だけを使う場合でも CLI のインストールが必要です。
  - CLI が未導入の場合、install スクリプトは MCP 経由の `strict` モード（v0.3.x 互換、追加トークンあり）に自動でフォールバックします。
- Python 3.11 以降
- [uv](https://docs.astral.sh/uv/) — Python の仮想環境とパッケージを一括管理するツール（`pip` + `venv` の高速な代替）。未導入なら [公式の install 手順](https://docs.astral.sh/uv/getting-started/installation/) で 1 コマンドで入ります
- macOS / Linux / Windows（Windows は PowerShell 7+ または Git Bash）

## クイックスタート

### 1. インストール

```bash
git clone https://github.com/Sora-bluesky/ja-output-harness.git
cd ja-output-harness
uv sync
bash scripts/install.sh --append-agents-rule
```

Windows PowerShell の場合は最後の行を次に置き換えます:

```powershell
pwsh scripts/install.ps1 -AppendAgentsRule
```

### 2. Codex を再起動

システムトレイから完全に終了 → 起動し直します（アプリはウィンドウを閉じるだけだと常駐することがあります）。

### 3. 使う

いつも通り Codex を使うだけ。日本語応答のたびに裏で検品が走り、違反があれば Codex が自己修正します。

## オン/オフの切替と比較

モデル更新（例: `GPT-5.5`）で Codex の日本語出力が改善したとき、ハーネス有りと無しを自分で比べたくなります。アンインストールせずに切替する手段が 2 つあります。

### 方法 1: CLI（ターミナルで使う場合）

```bash
ja-output-toggle status    # 現在のモード確認
ja-output-toggle off       # ハーネスを無効化（応答はそのまま通る）
ja-output-toggle on        # 再有効化（直前のモードを復元）
ja-output-toggle set lite  # モードを明示指定
```

### 方法 2: プロンプトで指示（Codex App 利用時）

Codex App はチャット欄しかないので、下記のプロンプトを貼るだけで Codex が同等のファイル操作をしてくれます。

**無効化するとき**:

````
ja-output-harness をオフにしてほしい。具体的には:
1. `~/.codex/state/jp-harness-mode` を読み、中身が `off` 以外なら
   その中身を `~/.codex/state/jp-harness-mode.bak` に保存する
2. `~/.codex/state/jp-harness-mode` に `off` の 1 行だけを書き込む
3. 完了後、現在のモードと直前のモード（もしあれば）を教えてほしい
````

![Codex App でオフ用プロンプトを貼って切り替わった例。`現在のモードは off です` / `直前のモードは strict-lite でした` という確認が返る](docs/assets/toggle-off-via-codex-app.png)

**再有効化するとき**:

````
ja-output-harness をオンに戻してほしい。具体的には:
1. `~/.codex/state/jp-harness-mode.bak` を読む（無ければ `strict-lite` を使う）
2. その中身を `~/.codex/state/jp-harness-mode` に書き込む
3. 完了後、現在のモードを教えてほしい
````

**状態だけ確認するとき**:

````
`~/.codex/state/jp-harness-mode` と `~/.codex/state/jp-harness-mode.bak` の中身をそのまま見せて。
````

### 比較の流れ

1. オフにして Codex をしばらく使う（例: 30 分）
2. オンに戻して同じ長さ使う
3. `ja-output-stats ab-report --baseline <off 期間> --test <on 期間>` で Wilson 下限付きの ok 率比較を確認する

切替は `~/.codex/state/jp-harness-mode` の 1 行ファイルの書き換えのみ。Codex の再起動は不要です（hook は毎ターン読み直します）。

## 何が違反として検出されるか

- **裸の英単語**: `parity` `slice` `pipeline` 等をバッククォート無しで書く
- **技術比喩の流用**: `fail-close` `fast-forward` `handoff` 等を助詞で使う
- **識別子過多**: 1 文に英語識別子を 3 個以上
- **長文**: 1 文 80 文字超（識別子を含む文では 50 文字超）
- **裸の PR / issue 番号**: `PR #123` `issue #42` 形式

ルールは [`config/banned_terms.yaml`](config/banned_terms.yaml) で追加・調整できます。

## よくある質問

> **Q. トークン消費は増えますか?**
>
> A. 基本は増えません。検品は Codex の外側でローカル実行されるため、応答トークンには 1 byte も足しません。違反が検出されたターンだけ、Codex が同じターン内で追加の推論を 1 回走らせます。ターン平均の増分は違反率に比例し、ドッグフードでの実測では `+0` 〜 `+60%` の幅です。

> **Q. コードや会話内容が外部に送信されたりしますか?**
>
> A. しません。検品は完全にローカルで実行されます。外部通信は一切ありません。

> **Q. 既存の AGENTS.md や config.toml に影響しますか?**
>
> A. 管理ブロックを明示的に区切って追記するだけで、既存のルールや設定には一切触れません。アンインストール時も同じブロックだけを削除します。

> **Q. 検出するルールを自分のプロジェクト向けに調整したい（誤検出されるルールを無効化したい / 追加で検出させたい単語がある）。**
>
> A. [`config/banned_terms.yaml`](config/banned_terms.yaml) を編集すれば、禁止語・バッククォートで囲むべき識別子の追加／削除、severity（ERROR / WARNING / INFO）の変更ができます。プロジェクトごとの上書きも可能です（詳細は [DEVELOPERS.md](DEVELOPERS.md)）。

> **Q. 今回の応答は検品をスキップして、Codex の出力をそのまま受け取りたい。**
>
> A. プロンプトに「検品不要」「このまま返答」などと書けば Codex がハーネスを迂回します。検品は強制ではなく、ユーザーがその場で切れる設計です。

> **Q. 動作確認はどうすれば?**
>
> A. Codex で日本語応答を 1 回もらった後、`~/.codex/state/jp-harness-lite.jsonl` に 1 行追加されていれば正常動作です。

> **Q. 自動修正が本当に機能しているか確認するには?**
>
> A. 違反が検出されると、Codex は同じターン内で自動で言い直します（strict-lite モードの挙動）。`jp-harness-lite.jsonl` の同じ `session` の連続エントリで、`ok: false` → 十数秒後に `ok: true` が続いていれば、修正ループが成立している証拠です。実例:
>
> ```jsonl
> {"ts":"2026-04-22T02:06:01Z","session":"019daea0-…","ok":false,"violation_count":2,"rule_counts":{"sentence_too_long":1,"banned_term":1},"mode":"strict-lite", ...}
> {"ts":"2026-04-22T02:06:17Z","session":"019daea0-…","ok":true,"violation_count":0,"rule_counts":{},"mode":"strict-lite", ...}
> ```
>
> 16 秒差で `ok: true` に遷移しているのは、最初の応答で違反 2 件を検出 → Codex が自動で言い直し → クリーンな応答で確定、の流れを意味します。

> **Q. Codex CLI と Codex App の両方を入れておかないといけない?**
>
> A. 普段 Codex App しか使っていない方でも、**install スクリプトの実行時に Codex CLI（`codex` コマンド）が必要** です。install 中に `codex features enable codex_hooks` を使って hook 機能を有効化するためで、有効化後は App 側でも自動で検品が走ります。CLI が PATH 上に無い場合、install スクリプトは MCP 経由の `strict` モードに自動でフォールバックします（検品は動きますが応答トークンが増えます）。

> **Q. 動かないときは?**
>
> A. Codex を完全に終了して再起動してください。config.toml や hooks.json は起動時にしか読まれません。それでもダメなら [DEVELOPERS.md](DEVELOPERS.md) のトラブルシューティングを参照してください。

## アンインストール

```bash
bash scripts/uninstall.sh
```

PowerShell は `pwsh scripts/uninstall.ps1`。既存の AGENTS.md や Codex 設定には触れません。

## リンク

- **[CHANGELOG.md](CHANGELOG.md)** — 変更履歴
- **[DEVELOPERS.md](DEVELOPERS.md)** — アーキテクチャ・モード比較・カスタマイズ・ドッグフーディング
- **[解説記事（Zenn）](https://zenn.dev/sora_biz/articles/ja-output-harness-milestone)** — 「Codex のフックだけで日本語を読みやすくするハーネスを作った」：仕組みの詳細・追加トークンの計算・実測 ok 率など（開発者向け）
- **[docs/DEPRECATION.md](docs/DEPRECATION.md)** — プロジェクトのアーカイブ条件（Codex 本体が日本語自然化を公式実装したら役目を終えます）

## License

[MIT License](LICENSE)
