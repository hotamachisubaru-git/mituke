# CONTRIBUTING.md

## Language for development (開発の為の自然言語)

We use Japanese. 私たちは日本語を使います。

Only log messages should be in English. ログメッセージのみ、英語で書いてください。

## Start development (開発環境を構築する)

- 1. Clone the repository (リポジトリをクローンする)
```bash
git clone https://github.com/098orin/mituke
```

- 2. Install uv (uv をインストールする)
  - uv のインストール方法は [公式ドキュメント](https://uv.run/guide/install) を参照してください。

- 3. Create a virtual environment (仮想環境を作成する)
```bash
uv venv
```

- 4. Install dependencies (依存関係をインストールする)
```bash
uv sync
```

## mitukeの開発フローについて

- 基本的にリポジトリをフォーク、プルリクエストを送信するというスタイルで開発します。
