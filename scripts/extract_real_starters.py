"""Extract real starting lineups for JPN/BRA from FIFA timeline events.

For each played match, identify players who:
- Have no 'sub_in_minute' (never came on as a sub)
- Have at least 1 event (actually played, not on bench)

Sort by first_minute (early appearance = starter). Take first 11.
Count how often each player started across matches.
"""
import json
import re
import ssl
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

JPN_ID = "43819"
BRA_ID = "43924"

# match_id, stage_id, label
GROUP_MATCHES = [
    ("400021456", 289273, "BRA-MAR"),
    ("400021470", 289273, "NED-JPN"),
    ("400021457", 289273, "BRA-HAI"),
    ("400021475", 289273, "TUN-JPN"),
    ("400021455", 289273, "SCO-BRA"),
    ("400021471", 289273, "JPN-SWE"),
]


def parse_minute(s):
    if not s:
        return 999
    s = s.replace("'", "")
    if "+" in s:
        a, _, b = s.partition("+")
        try:
            return int(a) + int(b or 0)
        except ValueError:
            return 999
    try:
        return int(s)
    except ValueError:
        return 999


def fetch_timeline(stage_id, match_id):
    url = f"https://api.fifa.com/api/v3/timelines/17/285023/{stage_id}/{match_id}?language=en"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    r = urllib.request.urlopen(req, context=CTX, timeout=15)
    return json.loads(r.read())


def collect(stage_id, match_id, label):
    data = fetch_timeline(stage_id, match_id)
    events = data.get("Event") or []
    players = defaultdict(
        lambda: {
            "first_minute": None,
            "sub_in_minute": None,
            "sub_out_minute": None,
            "name": "",
            "events": 0,
            "tid": None,
        }
    )
    for e in events:
        pid = e.get("IdPlayer")
        tid = e.get("IdTeam")
        sub_in = e.get("IdSubPlayer")
        etype = e.get("Type")
        minute = parse_minute(e.get("MatchMinute", ""))
        desc = (e.get("EventDescription") or [{}])[0].get("Description", "")

        if etype == 5 and pid and sub_in:
            players[pid]["sub_in_minute"] = minute
            players[pid]["tid"] = tid
            m = re.match(r"([\w\s\-\.]+)\s+\(in\)", desc)
            if m:
                players[pid]["name"] = m.group(1).strip()
            players[sub_in]["sub_out_minute"] = minute
            players[sub_in]["tid"] = tid

        if pid and tid:
            p = players[pid]
            p["tid"] = tid
            p["events"] += 1
            fm = p["first_minute"]
            if fm is None or minute < fm:
                p["first_minute"] = minute
            if not p["name"]:
                m = re.match(r"([\w\s\-\.]+?)\s+\(", desc)
                if m:
                    p["name"] = m.group(1).strip()
    return players


def main():
    jpn = defaultdict(lambda: {"starts": 0, "name": "", "matches": []})
    bra = defaultdict(lambda: {"starts": 0, "name": "", "matches": []})

    for match_id, stage_id, label in GROUP_MATCHES:
        try:
            players = collect(stage_id, match_id, label)
        except Exception as e:
            print(f"{label} failed: {e}", file=sys.stderr)
            continue

        # group by team
        by_team = defaultdict(list)
        for pid, info in players.items():
            if info["sub_in_minute"] is None and info["events"] > 0:
                # starter candidate
                fm = info["first_minute"] if info["first_minute"] is not None else 999
                by_team[info["tid"]].append((fm, pid, info["name"]))

        for tid, lst in by_team.items():
            if tid not in (JPN_ID, BRA_ID):
                continue
            lst.sort()
            starters = lst[:11]
            print(f"\n[{label}] team {tid}: {len(starters)} starters")
            target = jpn if tid == JPN_ID else bra
            for fm, pid, name in starters:
                target[pid]["starts"] += 1
                target[pid]["name"] = name
                target[pid]["matches"].append(label)
                print(f"  {fm:>3}'  {pid}  {name}")

        time.sleep(0.3)

    print("\n=== JPN summary (sorted by starts) ===")
    for pid, info in sorted(jpn.items(), key=lambda x: (-x[1]["starts"], x[0])):
        print(f"  {pid}  ({info['starts']}/3)  {info['name']:<25}  {info['matches']}")

    print("\n=== BRA summary (sorted by starts) ===")
    for pid, info in sorted(bra.items(), key=lambda x: (-x[1]["starts"], x[0])):
        print(f"  {pid}  ({info['starts']}/3)  {info['name']:<25}  {info['matches']}")

    out = {
        "JPN": {pid: info for pid, info in jpn.items()},
        "BRA": {pid: info for pid, info in bra.items()},
    }
    (DATA / "real_starters_jpn_bra.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nWrote data/real_starters_jpn_bra.json")


if __name__ == "__main__":
    main()
