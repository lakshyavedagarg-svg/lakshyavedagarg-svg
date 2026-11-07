#!/usr/bin/env python3
"""Generate an animated SVG from a GitHub user's contribution calendar."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path


API_URL = "https://api.github.com/graphql"
DAY = dt.timedelta(days=1)
LEVELS = ("#16393d", "#0d6468", "#00a8a8", "#20d9c2", "#8affdf")

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { contributionCount date weekday }
        }
      }
    }
  }
}
"""


def contribution_calendar(username: str, token: str, start: dt.datetime, end: dt.datetime) -> dict:
    payload = json.dumps(
        {"query": QUERY, "variables": {"login": username, "from": start.isoformat(), "to": end.isoformat()}}
    ).encode()
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "dust-heatmap-generator",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach the GitHub GraphQL API: {error}") from error

    if data.get("errors"):
        messages = "; ".join(error["message"] for error in data["errors"])
        raise RuntimeError(f"GitHub GraphQL query failed: {messages}")
    calendar = data.get("data", {}).get("user", {}).get("contributionsCollection", {}).get("contributionCalendar")
    if not calendar:
        raise RuntimeError(f"GitHub returned no contribution calendar for '{username}'.")
    return calendar


def level(count: int) -> str:
    if count <= 0:
        return LEVELS[0]
    if count < 3:
        return LEVELS[1]
    if count < 6:
        return LEVELS[2]
    if count < 10:
        return LEVELS[3]
    return LEVELS[4]


def position_seed(day: dict) -> random.Random:
    digest = hashlib.sha256(day["date"].encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def svg(calendar: dict, username: str) -> str:
    weeks = calendar["weeks"]
    cell, gap, padding = 12, 4, 22
    width = padding * 2 + len(weeks) * (cell + gap) - gap
    grid_height = 7 * (cell + gap) - gap
    height = padding * 2 + grid_height + 34
    groups: list[str] = []

    for col, week in enumerate(weeks):
        for day in week["contributionDays"]:
            row = day["weekday"]
            x = padding + col * (cell + gap)
            y = padding + row * (cell + gap) + 26
            rng = position_seed(day)
            # Each square enters from the right, then gets swept away left.
            sx = width + 40 + rng.randint(0, 220)
            sy = rng.randint(-40, height + 40)
            ex = -60 - rng.randint(0, 220)
            ey = rng.randint(-40, height + 40)
            arrival = 0.20 + (col / max(1, len(weeks) - 1)) * 0.42 + rng.uniform(-0.035, 0.035)
            arrival = max(0.06, min(0.68, arrival))
            date = html.escape(day["date"])
            label = f"{day['contributionCount']} contributions on {date}"
            groups.append(
                f'''<g transform="translate({sx:.1f} {sy:.1f})">
  <title>{label}</title>
  <rect width="{cell}" height="{cell}" rx="2" fill="{level(day['contributionCount'])}"/>
  <animateTransform attributeName="transform" type="translate" dur="12s" repeatCount="indefinite"
    values="{sx:.1f} {sy:.1f};{x} {y};{x} {y};{ex:.1f} {ey:.1f};{sx:.1f} {sy:.1f}"
    keyTimes="0;{arrival:.3f};0.740;0.955;1" calcMode="spline"
    keySplines="0.16 0.84 0.25 1;0 0 1 1;0.55 0 0.84 0.16;0 0 1 1"/>
</g>'''
            )

    total = calendar["totalContributions"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">{html.escape(username)}'s animated contribution heatmap</title>
  <desc id="desc">{total} contributions in the last year. Teal heatmap squares assemble from dust and then scatter away.</desc>
  <rect width="{width}" height="{height}" rx="14" fill="#0d1117"/>
  <text x="{padding}" y="25" fill="#c9d1d9" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="13">{total} contributions in the last year</text>
  {''.join(groups)}
</svg>
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--output", default="assets/dust-heatmap.svg")
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("Set GITHUB_TOKEN (or GH_TOKEN) before running this script.")

    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=365)
    calendar = contribution_calendar(args.username, token, start, end)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(svg(calendar, args.username), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
