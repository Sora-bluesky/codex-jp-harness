# Deprecation

本ハーネスは**暫定対策**として設計されている。以下の条件が満たされた時点で役目を終え、archive する。

## アンインストールトリガー

以下のいずれかが公式にリリースされ、stable 運用可能と判断された場合:

1. **Codex 本体（CLI / App 共通）での日本語自然化**
   - 英語語順直訳の解消
   - 禁止すべき英語比喩の自動言い換え
   - バッククォートの自動補完

2. **Pre-response hook（出力前書き換え）の公式機構**
   - ユーザー側で任意の postprocess を挟める hook

3. **`PreSkillUse` / `PostSkillUse` hook の実装**
   - [Issue #17132](https://github.com/openai/codex/issues/17132)

4. **その他、本ハーネスと同等以上の品質担保を提供する公式機能**

## アンインストール手順

### 1. Codex 側の登録を削除

```powershell
pwsh scripts\uninstall.ps1
```

`uninstall.ps1` / `uninstall.sh` は以下を自動実行:
- `~/.codex/config.toml` から `[mcp_servers.jp_lint]` ブロックを削除
- 削除前に `~/.codex/config.toml.bak` にバックアップを保存

以下は **現在は手動**（実装は GitHub Issue #50 で追跡中）:
- `~/.codex/hooks.json` の Stop / SessionStart 登録解除
- `~/.codex/config.toml` の `[features] codex_hooks = true` 解除
- `~/.codex/AGENTS.md` の品質ゲート規約ブロック削除（ユーザーが他ルールを追記している可能性があるため、最終削除は目視で行う）

### 2. リポジトリのアーカイブ

```powershell
gh repo archive sora-bluesky/ja-output-harness
```

README.md の冒頭に以下を追記:

```markdown
# ⚠️ ARCHIVED

このリポジトリは役目を終えました。OpenAI が Codex（CLI / App）に <機能名> を公式実装したため、本ハーネスは不要になりました。

- 公式機能のリリース: YYYY-MM-DD
- 関連リンク: <公式アナウンス URL>
- アンインストール手順は [`docs/DEPRECATION.md`](docs/DEPRECATION.md) 参照

過去の実装は歴史的記録として参照可能ですが、新規インストールは推奨しません。
```

### 3. Zenn 記事の更新

関連 Zenn 記事の冒頭に「役目を終えた」追記を入れ、公式機能へのリンクを張る。

## アンインストール判断の保留

公式機能がリリースされても、以下のケースでは即時アンインストールせず保留する:

- **β 版・実験的機能**の場合 → stable 化を待つ
- **部分的解決**のみ（例: 日本語自然化は入ったが hook は未対応）→ 部分アンインストールで段階対応
- **OSS コミュニティで代替実装**が優勢 → そちらへの誘導を検討

## 判断記録

アンインストールを検討した日付と判断内容をここに追記していく:

- YYYY-MM-DD: TBD

## コントリビュータへ

本ハーネスが archive された後も、過去のコミット・issue・PR は歴史的記録として残す。

新規機能の追加は archive 前に限定する。archive 後に重大なセキュリティ問題が発生した場合のみ、fix を提供する可能性がある。
