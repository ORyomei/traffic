# traffic

GitHub の Traffic API（views / clones / referrers / paths）は直近 14 日分しか保持されないため、
GitHub Actions で毎日取得して JSON で蓄積し、GitHub Pages でグラフを公開する。
Slack を設定すれば、前日分の数字と直近 30 日のグラフ画像も通知する。
（このリポジトリと Pages は public なので、収集した数字は誰でも見られる）

```
scripts/fetch_traffic.py   Traffic API を取得して data/ にマージ（標準ライブラリのみ）
scripts/traffic_chart.py   リポジトリごとの直近 30 日のグラフを縦に並べた PNG を作成（matplotlib）
scripts/notify_slack.py    前日（UTC）の views/clones の集計とグラフ画像・失敗を Slack に通知（Bot トークン）
data/index.json            対象リポジトリ一覧と最終更新時刻（data/ は data ブランチに保存）
data/repos/<repo>.json     日別 views/clones（日付キー）+ referrers/paths の日次スナップショット
                           + release アセットの累計ダウンロード数の日次スナップショット（release がある場合のみ）
site/                      可視化ページ（Chart.js、ビルド不要）
.github/workflows/traffic.yml  毎日 00:17 UTC に取得 → data ブランチにコミット → Pages に公開 → グラフ作成 → Slack に通知
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
4. （任意）**Slack の Bot トークンを発行**: https://api.slack.com/apps → Create New App → Blank app
   → OAuth & Permissions → Bot Token Scopes に `chat:write` と `files:write` を追加
   → Install to Workspace → Bot User OAuth Token（`xoxb-...`）をコピー
   → 通知先チャンネルで `/invite @<App 名>` し、チャンネル詳細の一番下からチャンネル ID（`C0...`）を控える
5. このリポジトリに登録（Settings → Secrets and variables → Actions）
   - Variable `APP_CLIENT_ID`: Client ID
   - Secret `APP_PRIVATE_KEY`: `.pem` の中身すべて（登録後 `.pem` は削除してよい）
   - Secret `SLACK_BOT_TOKEN`: Bot User OAuth Token（未登録なら通知せずログに出すだけ）
   - Variable `SLACK_CHANNEL_ID`: 通知先チャンネル ID
   - Settings → Pages → Source を **GitHub Actions** にする
6. 必要なら Variables を設定
   | 変数 | 既定値 | 説明 |
   |---|---|---|
   | `TRAFFIC_OWNER` | リポジトリの owner | 集計対象の org / user |
   | `TRAFFIC_REPOS` | （全リポジトリ） | カンマ区切りで対象を限定 |
   | `INCLUDE_PRIVATE` | `false` | `true` で private リポジトリも含める（**Pages で公開されるので注意**） |
   | `INCLUDE_FORKS` | `true` | `false` で fork リポジトリを除外 |
7. Actions から `Collect traffic` を手動実行（workflow_dispatch）

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
pip install -r requirements.txt
python3 scripts/traffic_chart.py data chart.png
python3 scripts/notify_slack.py summary chart.png   # SLACK_BOT_TOKEN 未設定なら内容を表示するだけ
```

## メモ

- 収集データは main ではなく `data` ブランチに保存する（毎日の bot コミットで main の履歴や
  Slack の commits 通知が埋まらないように）。初回実行時に自動で作成される。
- グラフ画像の作成に失敗した日は、数字だけを通知する（本文にその旨が出る）。
- 毎日の Slack 通知は生存確認も兼ねる。通知が来なければ workflow が止まっている。
  13 日以内に再開すれば Traffic API の 14 日分から欠けた日も埋まる。
- 日別の値は毎回上書きする（取得時点の当日分は集計途中のため）。通知した前日分も、GitHub 側の
  集計遅れで翌日の取得時に少し増えることがある。
- 日付はすべて UTC（GitHub の traffic が UTC の日単位で集計されるため）。
- Unique 数の合計は日別・リポジトリ別ユニークの単純合計で、重複排除はされない。
- referrers / paths は 14 日間の集計値で加算できないため、取得日ごとのスナップショットとして保存し、ページには最新のものを表示する。
