#!/usr/bin/env python3
"""KO autoupdate: 每 15 分鐘跑,for each KO match,在 T-60 / T+60 / T+120 / T+180
窗口觸發對應更新並 commit+push。

窗口:
  T-60 ±15 min  → lineup 抓取 (extract_real_starters 模式 — 不過 KO 賽前無 timeline,
                              所以也許只能依賴 starters_seed 預設值 + FIFA squad endpoint)
  T+60 ±15 min  → 上半場比分 + 進球 (fetch_and_build refresh)
  T+120 ±15 min → 全場比分 + 進球
  T+180 ±15 min → 加時+PK 場最終比分

維護 .ko_autoupdate_state.json 紀錄已觸發窗口,避免重複 fire。
跑完若有實質變動,自動 git add + commit + push。
"""
import json
import re
import ssl
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATE = ROOT / ".ko_autoupdate_state.json"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

WINDOW_MIN = 15  # ± minutes around each anchor

# Anchors (relative to kickoff): label → minutes offset
ANCHORS = [
    ("lineup",   -60),
    ("half",      60),
    ("full",     120),
    ("extra_pk", 180),
]


def now_utc():
    return datetime.now(timezone.utc)


def parse_iso(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def save_state(s):
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def in_window(now, kickoff, offset_min):
    target = kickoff + timedelta(minutes=offset_min)
    delta = abs((now - target).total_seconds() / 60)
    return delta <= WINDOW_MIN


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 wc2026-ko"})
    with urllib.request.urlopen(req, context=CTX, timeout=timeout) as r:
        return json.loads(r.read())


def extract_starters_for_match(match_id, stage_id):
    """For one match, fetch timeline events and return starters by team:
       {tid: [{name, pid}, ...]}.
       Starter = no sub_in_minute + has events. Take first 11 by first event minute."""
    url = f"https://api.fifa.com/api/v3/timelines/17/285023/{stage_id}/{match_id}?language=en"
    try:
        data = fetch_json(url)
    except Exception as e:
        print(f"  timeline {match_id} failed: {e}", file=sys.stderr)
        return {}

    events = data.get("Event") or []
    if not events:
        return {}

    def parse_min(s):
        if not s: return 999
        s = s.replace("'", "")
        if "+" in s:
            a, _, b = s.partition("+")
            try: return int(a) + int(b or 0)
            except: return 999
        try: return int(s)
        except: return 999

    players = defaultdict(lambda: {"first_minute": None, "sub_in_minute": None,
                                    "name": "", "events": 0, "tid": None})
    for e in events:
        pid = e.get("IdPlayer")
        tid = e.get("IdTeam")
        sub_in = e.get("IdSubPlayer")
        etype = e.get("Type")
        minute = parse_min(e.get("MatchMinute", ""))
        desc = (e.get("EventDescription") or [{}])[0].get("Description", "")

        if etype == 5 and pid and sub_in:
            players[pid]["sub_in_minute"] = minute
            players[pid]["tid"] = tid
            m = re.match(r"([\w\s\-\.]+)\s+\(in\)", desc)
            if m:
                players[pid]["name"] = m.group(1).strip()
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

    by_team = defaultdict(list)
    for pid, info in players.items():
        if info["sub_in_minute"] is None and info["events"] > 0:
            fm = info["first_minute"] if info["first_minute"] is not None else 999
            by_team[info["tid"]].append({"first_minute": fm, "pid": pid, "name": info["name"]})

    out = {}
    for tid, lst in by_team.items():
        lst.sort(key=lambda x: x["first_minute"])
        out[tid] = lst[:11]
    return out


def update_lineup_for_match(match):
    """T-60 anchor: 賽前 60 分鐘 lineup 更新。

    FIFA timeline 在『未開賽』時沒有 event,無法從這場本身抓首發。
    但 build_preview.py 透過 compute_confirmed_starters 會從**已完成比賽** timeline
    (group + 之前的 KO) 取得每隊真實上場過的球員清單,用來在 make_lineup
    時優先選有實戰紀錄的球員。

    所以 T-60 階段做的事:
      1. 跑 fetch_and_build.py 刷新 fifa_raw + schedule.json (含最新進球資料)
      2. 接下來 rebuild_preview 會自動帶入最新 confirmed_starters

    Returns True 代表有觸發 refresh (讓上層知道要 rebuild_preview)。
    """
    h = match["home"].get("code")
    a = match["away"].get("code")
    print(f"  [lineup] {h} vs {a}: 觸發 fetch_and_build 刷新 confirmed_starters",
          file=sys.stderr)
    return True  # signal that schedule/preview need refresh


def update_scores_for_all():
    """T+60/+120/+180 anchor: full refresh from fetch_and_build.
    Reuses existing main(). Returns True if schedule.json changed."""
    before = (DATA / "schedule.json").read_bytes()
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts/fetch_and_build.py")],
        capture_output=True, text=True, encoding="utf-8"
    )
    if r.returncode != 0:
        print(f"  fetch_and_build failed: {r.stderr[:500]}", file=sys.stderr)
        return False
    after = (DATA / "schedule.json").read_bytes()
    return before != after


def promote_winners():
    """For each finished R32 match, write the winner code into any R16
    placeholder that references it (e.g., W74, W77 etc).
    The placeholder string format from FIFA is like 'W74' meaning winner of match 74.
    """
    s = json.loads((DATA / "schedule.json").read_text(encoding="utf-8"))
    matches = s["matches"]
    # winners_by_no: match_no → winning_code
    winners = {}
    for m in matches:
        if m.get("stage") not in ("r32", "r16", "qf", "sf"):
            continue
        no = m.get("no")
        h_score = m["home"].get("score")
        a_score = m["away"].get("score")
        if h_score is None or a_score is None:
            continue
        # decide winner
        if h_score > a_score:
            winners[no] = m["home"].get("code")
        elif h_score < a_score:
            winners[no] = m["away"].get("code")
        else:
            # penalty shootout
            hp = m["home"].get("pen")
            ap = m["away"].get("pen")
            if hp is not None and ap is not None:
                if hp > ap:
                    winners[no] = m["home"].get("code")
                elif ap > hp:
                    winners[no] = m["away"].get("code")

    # Patch placeholders. Format e.g. 'W74' or 'W 74'
    changed = False
    for m in matches:
        if m.get("stage") == "group":
            continue
        for side in ("home", "away"):
            cur_code = m[side].get("code")
            if cur_code:
                continue  # already filled (FIFA gave us the team)
            ph = m.get(f"placeholder{side.title()}") or ""
            num_match = re.search(r"W\s*(\d+)", ph)
            if not num_match:
                continue
            win_no = int(num_match.group(1))
            wcode = winners.get(win_no)
            if wcode:
                # find the winning team's data
                for src in matches:
                    if src["home"].get("code") == wcode:
                        m[side] = dict(src["home"])
                        m[side].pop("score", None)
                        m[side].pop("pen", None)
                        m[side]["score"] = None
                        m[side]["pen"] = None
                        changed = True
                        break
                    if src["away"].get("code") == wcode:
                        m[side] = dict(src["away"])
                        m[side].pop("score", None)
                        m[side].pop("pen", None)
                        m[side]["score"] = None
                        m[side]["pen"] = None
                        changed = True
                        break

    if changed:
        (DATA / "schedule.json").write_text(
            json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return changed


def rebuild_preview():
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_preview.py")],
        capture_output=True, text=True, encoding="utf-8"
    )
    return r.returncode == 0


def git_commit_and_push(msg):
    subprocess.run(["git", "-C", str(ROOT), "add", "-A"], check=False)
    diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--quiet"], check=False)
    if diff.returncode == 0:
        return False  # nothing to commit
    subprocess.run(
        ["git", "-C", str(ROOT), "pull", "--rebase", "origin", "master"],
        check=False, capture_output=True
    )
    subprocess.run(["git", "-C", str(ROOT), "add", "-A"], check=False)
    subprocess.run(["git", "-C", str(ROOT), "commit", "-m", msg], check=False)
    push = subprocess.run(
        ["git", "-C", str(ROOT), "push", "origin", "master"],
        capture_output=True, text=True
    )
    if push.returncode != 0:
        print(f"  push failed: {push.stderr[:300]}", file=sys.stderr)
        return False
    return True


def main():
    now = now_utc()
    print(f"[ko_autoupdate] {now.isoformat()}", file=sys.stderr)

    schedule = json.loads((DATA / "schedule.json").read_text(encoding="utf-8"))
    state = load_state()

    # Limit to KO matches with known kickoff
    ko = [m for m in schedule["matches"] if m.get("stage") != "group" and m.get("utc")]

    triggered = []
    needs_score_refresh = False
    needs_promote = False
    needs_preview = False

    for m in ko:
        mid = str(m["id"])
        kickoff = parse_iso(m["utc"])
        if not kickoff:
            continue
        for label, offset_min in ANCHORS:
            if not in_window(now, kickoff, offset_min):
                continue
            key = f"{mid}:{label}"
            if state.get(key):
                continue  # already fired
            triggered.append((mid, m, label, offset_min))
            state[key] = now.isoformat()

    if not triggered:
        print("  no anchors in window — sleeping", file=sys.stderr)
        return 0

    print(f"  triggered {len(triggered)} anchors", file=sys.stderr)
    msg_parts = []
    for mid, m, label, off in triggered:
        h = m["home"].get("code") or "?"
        a = m["away"].get("code") or "?"
        print(f"    [{label}] {h} vs {a} (T{off:+d})", file=sys.stderr)
        msg_parts.append(f"{h}-{a} {label}")
        if label == "lineup":
            update_lineup_for_match(m)
            needs_score_refresh = True  # also pull latest goals/sched changes
            needs_preview = True
        elif label in ("half", "full", "extra_pk"):
            needs_score_refresh = True

    if needs_score_refresh:
        print("  → refreshing FIFA scores…", file=sys.stderr)
        if update_scores_for_all():
            needs_promote = True
            needs_preview = True

    if needs_promote:
        print("  → promoting KO winners…", file=sys.stderr)
        if promote_winners():
            needs_preview = True

    if needs_preview:
        print("  → rebuilding preview…", file=sys.stderr)
        rebuild_preview()

    save_state(state)

    pushed = git_commit_and_push(
        f"chore: KO autoupdate {now.strftime('%Y-%m-%d %H:%M UTC')} — " + " / ".join(msg_parts)
    )
    print(f"  push: {pushed}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
