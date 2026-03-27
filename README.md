# mituke

Discord の VC で話した内容を文字起こしして、指定したテキストチャンネルへ順次投稿する Bot です。

## できること

- 話し始めを検知したら、文字起こし用のメッセージを作ります。
- 話している途中は、同じメッセージを編集して文字起こしを更新します。
- 話し終わったら、そのメッセージを確定版の内容に整えます。
- VC に Bot 以外がいなくなったら、自動で退出します。

## 必要なもの

- Python 3.12 以上
- Discord Bot のトークン
- 日本語向けの Vosk モデル
- 必要に応じて Opus ライブラリ

## 事前準備

1. 依存関係を入れます。

```bash
uv sync
```

2. `.env` を作り、最低限次の値を設定します。

```env
DISCORD_TOKEN=あなたのBotトークン
VOSK_MODEL_PATH=.\models\vosk-model-ja
```

3. Windows で Opus の自動読込に失敗する場合だけ、`DISCORD_OPUS_PATH` も設定します。

```env
DISCORD_OPUS_PATH=C:\path\to\libopus-0.dll
```

## 起動方法

```bash
uv run python src/main.py
```

## 使い方

1. Bot を使いたいサーバーのテキストチャンネルで `!join` を実行します。
2. コマンドを実行した人が入っている VC に Bot が参加します。
3. 文字起こし結果は、そのコマンドを打ったテキストチャンネルへ投稿されます。
4. 停止したいときは `!leave` を実行します。

## 環境変数

- `DISCORD_TOKEN`: Discord Bot のトークン
- `VOSK_MODEL_PATH`: Vosk モデルのフォルダパス
- `MODEL_PATH`: 以前の設定名です。`VOSK_MODEL_PATH` が未設定のときだけ使われます
- `DISCORD_OPUS_PATH`: Windows で Opus を明示指定したいときの DLL パス
