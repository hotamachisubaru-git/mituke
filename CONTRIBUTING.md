# コントリビューションガイド

## 開発で使う言語

開発時の自然言語は日本語を使います。
コード内の文言やログも、特別な理由がなければ日本語で統一してください。

## 開発環境の作り方

1. リポジトリをクローンします。

```bash
git clone https://github.com/098orin/mituke
```

2. `uv` をインストールします。

`uv` の導入方法は [公式ドキュメント](https://uv.run/guide/install) を参照してください。

3. 仮想環境を作ります。

```bash
uv venv
```

4. 依存関係をインストールします。

```bash
uv sync
```

## 開発フロー

基本的には、リポジトリをフォークしてからプルリクエストを送る流れで開発します。

## テスト

Discord API キーがなくても、次のコマンドで主要ロジックの回帰確認ができます。

```bash
uv run python -m unittest discover -s tests -v
```
