#!/usr/bin/env python3
"""Post traffic notifications to Slack with a bot token.

  notify_slack.py summary [chart.png]   yesterday's (UTC) views/clones per repo, read from data/;
                                        the chart is uploaded with the text when the file exists
  notify_slack.py failure               the workflow run failed

Environment:
  SLACK_BOT_TOKEN    bot token with chat:write and files:write; when empty, nothing is posted
  SLACK_CHANNEL_ID   channel to post to (the bot must be a member)
  DATA_DIR           data directory written by fetch_traffic.py (default: data)
  FAILED_REPOS       comma-separated repos whose traffic could not be fetched
  GITHUB_SERVER_URL, GITHUB_REPOSITORY, GITHUB_RUN_ID  set by Actions; used for the run link
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
CHANNEL = os.environ.get("SLACK_CHANNEL_ID", "")
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))


def run_url():
    env = os.environ
    if not env.get("GITHUB_RUN_ID"):
        return None
    return f"{env['GITHUB_SERVER_URL']}/{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}"


def slack(method, params):
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=urllib.parse.urlencode(params).encode(),
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        body = json.load(res)
    if not body.get("ok"):
        sys.exit(f"Slack {method} failed: {body.get('error')}")
    return body


def post(text, image=None):
    if not TOKEN or not CHANNEL:
        print("SLACK_BOT_TOKEN / SLACK_CHANNEL_ID not set; skipping notification:\n" + text)
        return
    if image is None:
        slack("chat.postMessage", {"channel": CHANNEL, "text": text})
        return
    # files.upload is retired; upload to a presigned URL, then share it with the text.
    content = image.read_bytes()
    up = slack("files.getUploadURLExternal", {"filename": image.name, "length": len(content)})
    req = urllib.request.Request(up["upload_url"], data=content, headers={"Content-Type": "image/png"})
    with urllib.request.urlopen(req, timeout=60) as res:
        res.read()
    slack("files.completeUploadExternal", {
        "files": json.dumps([{"id": up["file_id"], "title": image.stem}]),
        "channel_id": CHANNEL,
        "initial_comment": text,
    })


def summary(chart):
    index = json.loads((DATA_DIR / "index.json").read_text())
    day = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    rows = []
    for name in index["repos"]:
        path = DATA_DIR / "repos" / f"{name}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        zero = {"count": 0, "uniques": 0}
        v, c = data["views"].get(day, zero), data["clones"].get(day, zero)
        rows.append((name, v, c))

    total = lambda kind, key: sum(r[1 if kind == "views" else 2][key] for r in rows)
    lines = [
        f"*{index['owner']} traffic — {day} (UTC)*",
        f"Views *{total('views', 'count')}* (unique {total('views', 'uniques')})"
        f"   Clones *{total('clones', 'count')}* (unique {total('clones', 'uniques')})",
    ]

    active = sorted(
        (r for r in rows if r[1]["count"] or r[2]["count"]),
        key=lambda r: (-(r[1]["count"] + r[2]["count"]), r[0]),
    )
    if active:
        width = max(len(r[0]) for r in active)
        table = [
            f"{name:<{width}}  views {v['count']:>3} ({v['uniques']})   clones {c['count']:>3} ({c['uniques']})"
            for name, v, c in active
        ]
        lines.append("```" + "\n".join(table) + "```")
        if len(active) < len(rows):
            lines.append(f"ほか {len(rows) - len(active)} リポジトリは 0")
    else:
        lines.append("全リポジトリで動きなし")

    failed = [r for r in os.environ.get("FAILED_REPOS", "").split(",") if r]
    if failed:
        url = run_url()
        lines.append(f":warning: 取得失敗 {len(failed)} 件: {', '.join(failed)}" + (f" (<{url}|ログ>)" if url else ""))
    if chart is not None and not chart.exists():
        lines.append(":warning: グラフ画像を作れなかったため、数字のみ送信")
        chart = None
    post("\n".join(lines), chart)


def failure():
    url = run_url()
    post(":x: traffic の収集 workflow が失敗しました" + (f"\n<{url}|実行ログを開く>" if url else ""))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "summary":
        summary(Path(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif mode == "failure":
        failure()
    else:
        sys.exit("usage: notify_slack.py summary [chart.png] | failure")
