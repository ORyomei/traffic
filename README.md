# traffic

GitHub の Traffic API（views / clones / referrers / paths）は直近 14 日分しか保持されないため、
GitHub Actions で毎日取得して JSON で蓄積し、GitHub Pages でグラフを公開する。
（このリポジトリと Pages は public なので、収集した数字は誰でも見られる）

```
scripts/fetch_traffic.py   Traffic API を取得して data/ にマージ（標準ライブラリのみ）
data/index.json            対象リポジトリ一覧と最終更新時刻（data/ は data ブランチに保存）
data/repos/<repo>.json     日別 views/clones（日付キー）+ referrers/paths の日次スナップショット
                           + release アセットの累計ダウンロード数の日次スナップショット（release がある場合のみ）
site/                      可視化ページ（Chart.js、ビルド不要）
.github/workflows/traffic.yml  毎日 00:17 UTC に取得 → data ブランチにコミット → Pages に公開
```

## セットアップ

Traffic API の読み取りには GitHub App を使う（個人に紐づかず、期限切れもない）。
workflow が実行ごとに App の秘密鍵から 1 時間有効のトークンを発行する。

1. **GitHub App を作成**: 個人の Settings → Developer settings → GitHub Apps → New GitHub App
   - Homepage URL: このリポジトリの URL（任意の URL でよい）
   - Webhook: Active のチェックを外す
   - Repository permissions: **Administration: Read-only**（Traffic API に必要。Metadata は自動付与）
   - Where can this GitHub App be installed?: **Only on this account**
2. 作成後の画面で **Client ID** を控え、**Generate a private key** で `.pem` をダウンロード
3. 左メニュー Install App → 自分のアカウントに **All repositories** でインストール
4. このリポジトリに登録（Settings → Secrets and variables → Actions）
   - Variable `APP_CLIENT_ID`: Client ID
   - Secret `APP_PRIVATE_KEY`: `.pem` の中身すべて（登録後 `.pem` は削除してよい）
   - Settings → Pages → Source を **GitHub Actions** にする
5. 必要なら Variables を設定
   | 変数 | 既定値 | 説明 |
   |---|---|---|
   | `TRAFFIC_OWNER` | リポジトリの owner | 集計対象の org / user |
   | `TRAFFIC_REPOS` | （全リポジトリ） | カンマ区切りで対象を限定 |
   | `INCLUDE_PRIVATE` | `false` | `true` で private リポジトリも含める（**Pages で公開されるので注意**） |
   | `INCLUDE_FORKS` | `true` | `false` で fork リポジトリを除外 |
6. Actions から `Collect traffic` を手動実行（workflow_dispatch）

## グラフを見る

Pages（`https://<user>.github.io/traffic/`）で見られる。ローカルで見る場合:

```sh
git fetch origin data
rm -rf _site && mkdir -p _site && cp -r site/. _site/
git archive origin/data data | tar -x -C _site
python3 -m http.server -d _site   # → http://localhost:8000/
```

## ローカルで取得を試す

```sh
GH_TOKEN=$(gh auth token) TRAFFIC_OWNER=<user> python3 scripts/fetch_traffic.py
```

## メモ

- 収集データは main ではなく `data` ブランチに保存する（毎日の bot コミットで main の履歴が埋まらないように）。初回実行時に自動で作成される。
- workflow が失敗すると GitHub から通知メールが届く。止まっていても
  13 日以内に再開すれば Traffic API の 14 日分から欠けた日も埋まる。
- 日別の値は毎回上書きする（取得時点の当日分は集計途中で、前日分も GitHub 側の集計遅れで少し増えることがあるため）。
- 日付はすべて UTC（GitHub の traffic が UTC の日単位で集計されるため）。
- Unique 数の合計は日別・リポジトリ別ユニークの単純合計で、重複排除はされない。
- referrers / paths は 14 日間の集計値で加算できないため、取得日ごとのスナップショットとして保存し、ページには最新のものを表示する。
- public リポジトリの schedule は 60 日間動きがないと自動で無効になるため、実行のたびに workflow を有効化し直している。
