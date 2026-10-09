#!/usr/bin/env python3
"""Fetch GitHub Traffic API data and merge it into data/.

The Traffic API only keeps the last 14 days, so this script is meant to run
daily and accumulate history:

  data/index.json          repo list + last update time
  data/repos/<name>.json   per-repo daily views/clones (+ referrer/path snapshots,
                           cumulative release-asset download counts per fetch date)

Daily counts are keyed by date and overwritten on every run, because the most
recent days are still being counted when we fetch them.

Environment:
  GH_TOKEN          token with read access to repo traffic (required)
  TRAFFIC_OWNER     org or user whose repos are tracked (required)
  TRAFFIC_REPOS     comma-separated repo names; empty = auto-discover all
  INCLUDE_PRIVATE   "true" to include private repos (default: false)
  INCLUDE_ARCHIVED  "true" to include archived repos (default: false)
  INCLUDE_FORKS     "false" to exclude forks (default: true)
  DATA_DIR          output directory (default: data)
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN", "")
OWNER = os.environ.get("TRAFFIC_OWNER", "")
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))


def env_flag(name):
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def api_get(path, attempts=3):
    """GET a JSON resource; returns (status, body, next_url).

    Network errors and 5xx responses are retried with backoff; if they persist,
    status is the last HTTP code (or 0 for a network error).
    """
    url = path if path.startswith("http") else API + path
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "traffic-collector",
    })
    status = 0
    for attempt in range(attempts):
        if attempt:
            time.sleep(2 ** attempt)
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                body = json.load(res)
                next_url = None
                for part in res.headers.get("Link", "").split(","):
                    if 'rel="next"' in part:
                        next_url = part[part.index("<") + 1:part.index(">")]
                return res.status, body, next_url
        except urllib.error.HTTPError as e:
            status = e.code
            if status < 500:
                return status, None, None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            status = 0
            print(f"  ! {url}: {e}", file=sys.stderr)
    return status, None, None


def api_get_all(path):
    items, url = [], path
    while url:
        status, body, url = api_get(url)
        if status != 200:
            return status, None
        items.extend(body)
    return 200, items


def list_repos():
    explicit = [r.strip() for r in os.environ.get("TRAFFIC_REPOS", "").split(",") if r.strip()]
    if explicit:
        return explicit

    status, repos = api_get_all(f"/orgs/{OWNER}/repos?type=all&per_page=100")
    if status == 404:  # not an org; fall back to a user account
        status, repos = api_get_all(f"/users/{OWNER}/repos?type=owner&per_page=100")
    if status != 200:
        sys.exit(f"failed to list repos for {OWNER}: HTTP {status}")

    include_private = env_flag("INCLUDE_PRIVATE")
    include_archived = env_flag("INCLUDE_ARCHIVED")
    include_forks = os.environ.get("INCLUDE_FORKS", "true").strip().lower() not in ("0", "false", "no")
    return sorted(
        r["name"] for r in repos
        if (include_private or not r["private"])
        and (include_archived or not r["archived"])
        and (include_forks or not r["fork"])
    )


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def dump_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True) + "\n")


def merge_daily(store, entries):
    for e in entries:
        store[e["timestamp"][:10]] = {"count": e["count"], "uniques": e["uniques"]}


def release_downloads(repo):
    """Cumulative download count per release asset, keyed "<tag>/<asset>".

    The API only exposes running totals, so daily downloads are the difference
    between consecutive snapshots.
    """
    status, releases = api_get_all(f"/repos/{OWNER}/{repo}/releases?per_page=100")
    if status != 200:
        print(f"::warning::{repo}: releases -> HTTP {status}")
        return None
    return {
        f"{r['tag_name']}/{a['name']}": a["download_count"]
        for r in releases for a in r["assets"]
    }


def collect(repo, today):
    base = f"/repos/{OWNER}/{repo}/traffic"
    results = {}
    for key, path in (
        ("views", "/views?per=day"),
        ("clones", "/clones?per=day"),
        ("referrers", "/popular/referrers"),
        ("paths", "/popular/paths"),
    ):
        status, body, _ = api_get(base + path)
        if status != 200:
            print(f"::warning::{repo}: {key} -> HTTP {status}")
            return None
        results[key] = body

    path = DATA_DIR / "repos" / f"{repo}.json"
    data = load_json(path, {"repo": f"{OWNER}/{repo}", "views": {}, "clones": {}, "referrers": {}, "paths": {}})
    merge_daily(data["views"], results["views"]["views"])
    merge_daily(data["clones"], results["clones"]["clones"])
    # Referrers/paths are 14-day aggregates, not additive; keep one snapshot per fetch date.
    data["referrers"][today] = results["referrers"]
    data["paths"][today] = [
        {"path": p["path"], "title": p["title"], "count": p["count"], "uniques": p["uniques"]}
        for p in results["paths"]
    ]
    downloads = release_downloads(repo)
    if downloads:
        data.setdefault("downloads", {})[today] = downloads
    dump_json(path, data)
    return data


def main():
    if not TOKEN or not OWNER:
        sys.exit("GH_TOKEN and TRAFFIC_OWNER must be set")

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    repos = list_repos()
    print(f"collecting traffic for {len(repos)} repos of {OWNER}")

    index_path = DATA_DIR / "index.json"
    index = load_json(index_path, {"owner": OWNER, "repos": []})
    known = set(index["repos"])
    failed = []
    for repo in repos:
        if collect(repo, today) is None:
            failed.append(repo)
        else:
            known.add(repo)
            print(f"  ok {repo}")

    index.update(owner=OWNER, repos=sorted(known), updated_at=now.isoformat(timespec="seconds"))
    dump_json(index_path, index)

    if failed:
        print(f"::warning::traffic not collected for {len(failed)}/{len(repos)} repos: {', '.join(failed)}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write(f"failed={','.join(failed)}\n")
    if failed and len(failed) == len(repos):
        sys.exit("all repos failed; check that the token can read traffic (Administration: read)")


if __name__ == "__main__":
    main()
