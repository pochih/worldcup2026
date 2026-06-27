#!/usr/bin/env python3
"""Build data/preview.json from schedule + analysis + stars + overrides.

Includes every knockout match where both teams are confirmed, plus group
matches where the two teams' FIFA ranks are close enough to be marquee.

Hand-written entries in data/preview_overrides/{HOME}_{AWAY}.json
(alphabetized) win over auto-generated ones. Auto entries are flagged
with `_auto: true` so the UI can show a tag.
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OVERRIDE_DIR = DATA / "preview_overrides"

# Close-rank group match thresholds (one place to tune).
RANK_GAP_MAX = 8     # |rank_h - rank_a| ≤ this
RANK_BEST_MAX = 25   # AND min(rank_h, rank_a) ≤ this — both reasonably strong

STAGE_LABEL_ZH = {
    "group": "小組賽 · 強強對決",
    "r32": "32 強淘汰賽",
    "r16": "16 強淘汰賽",
    "qf": "8 強",
    "sf": "4 強",
    "third": "季軍戰",
    "final": "🏆 決賽",
}

ZH = {
    "ALG": "阿爾及利亞", "ARG": "阿根廷", "AUS": "澳洲", "AUT": "奧地利",
    "BEL": "比利時", "BIH": "波赫", "BRA": "巴西", "CAN": "加拿大",
    "CIV": "象牙海岸", "COD": "剛果民主共和國", "COL": "哥倫比亞", "CPV": "維德角",
    "CRO": "克羅埃西亞", "CUW": "庫拉索", "CZE": "捷克", "ECU": "厄瓜多",
    "EGY": "埃及", "ENG": "英格蘭", "ESP": "西班牙", "FRA": "法國",
    "GER": "德國", "GHA": "迦納", "HAI": "海地", "IRN": "伊朗",
    "IRQ": "伊拉克", "JOR": "約旦", "JPN": "日本", "KOR": "南韓",
    "KSA": "沙烏地阿拉伯", "MAR": "摩洛哥", "MEX": "墨西哥", "NED": "荷蘭",
    "NOR": "挪威", "NZL": "紐西蘭", "PAN": "巴拿馬", "PAR": "巴拉圭",
    "POR": "葡萄牙", "QAT": "卡達", "RSA": "南非", "SCO": "蘇格蘭",
    "SEN": "塞內加爾", "SUI": "瑞士", "SWE": "瑞典", "TUN": "突尼西亞",
    "TUR": "土耳其", "URU": "烏拉圭", "USA": "美國", "UZB": "烏茲別克",
}

# Map star pos to a lineup slot bucket (FW / AM / MID / DEF / GK).
POS_BUCKET = {
    "GK": "GK",
    "CB": "DEF", "LB": "DEF", "RB": "DEF", "DEF": "DEF",
    "DM": "MID", "CM": "MID", "LM": "MID", "RM": "MID", "MID": "MID",
    "AM": "AM",
    "LW": "FW", "RW": "FW", "ST": "FW", "CF": "FW", "FW": "FW", "FWD": "FW",
}

# Chinese labels for unfilled slots so non-curated teams still read naturally.
POS_ZH = {
    "GK": "門將", "CB": "中後衛", "LB": "左後衛", "RB": "右後衛",
    "DM": "後腰", "CM": "中場", "LM": "左中場", "RM": "右中場",
    "AM": "前腰", "LW": "左翼", "RW": "右翼", "ST": "中鋒", "CF": "前鋒",
}


def match_key(code_a, code_b):
    return "_".join(sorted([code_a.upper(), code_b.upper()]))


def team_is_confirmed(side):
    if not side: return False
    code = side.get("code")
    if not code: return False
    # Reject obvious placeholders ("W74", "Winner", numeric only)
    if str(code).startswith("W") and str(code)[1:].isdigit(): return False
    return True


def is_marquee_group_match(h_code, a_code, analysis):
    h, a = analysis.get(h_code), analysis.get(a_code)
    if not (h and a): return False
    rank_h, rank_a = h.get("rank", 99), a.get("rank", 99)
    return abs(rank_h - rank_a) <= RANK_GAP_MAX and min(rank_h, rank_a) <= RANK_BEST_MAX


def short_name(name):
    """Truncate long names to fit on a small pitch dot."""
    if not name: return ""
    if len(name) <= 10: return name
    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[0][0]}. {parts[-1]}"[:11]
    return name[:9] + "."


def make_lineup(code, team_meta, stars, templates, mirror=False, rosters=None):
    """Produce 11 player dicts. Priority for filling each slot:
       1) rosters.json (full curated 11-man squad, exact pos match preferred)
       2) stars.json (4-name star roster, bucket-matched)
       3) Chinese position label fallback (e.g., '右後衛').
    Always returns 11 entries in template order."""
    rosters = rosters or {}
    meta = team_meta.get(code, {})
    formation = meta.get("formation", "4-3-3")
    # If rosters specifies a formation for this team, prefer it (more accurate)
    roster_entry = rosters.get(code)
    if roster_entry and roster_entry.get("formation"):
        formation = roster_entry["formation"]
    template = templates.get(formation, templates["4-3-3"])

    # Bucket roster players by exact pos (for first-pass fill)
    roster_by_pos = {}
    if roster_entry:
        for p in roster_entry.get("players", []):
            roster_by_pos.setdefault(p.get("pos", ""), []).append(p)

    # Bucket stars
    star_by_bucket = {}
    for s in stars.get(code, []):
        b = POS_BUCKET.get(s.get("pos", ""), "MID")
        star_by_bucket.setdefault(b, []).append(s)

    # Build a set of star names (English) so we can prioritize stars when
    # the same player appears in both rosters and stars (e.g., Mbappé is
    # FW in rosters.json #10 AND a star in stars.json — without this, the
    # rosters' alphabetic order may push him out of the 11 in favour of
    # secondary FWs like Thuram).
    import unicodedata
    def _norm(s):
        if not s: return ""
        # NFKD normalize → strip combining marks (é → e)
        return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()

    star_names_lower = set()
    for s in stars.get(code, []):
        nm = _norm(s.get("name") or "")
        if nm: star_names_lower.add(nm)

    def _is_star_player(p):
        nm = _norm(p.get("name") or "")
        # exact normalized name match
        if nm in star_names_lower: return True
        # Surname fallback: check if any star's surname appears in roster name
        for sn in star_names_lower:
            tokens = sn.split()
            if tokens and tokens[-1] in nm:
                return True
        return False

    # Sort each roster pos bucket so star players come first
    for pos_key in roster_by_pos:
        roster_by_pos[pos_key].sort(key=lambda p: 0 if _is_star_player(p) else 1)

    used_roster = set()
    used_stars = set()
    lineup = []
    for i, slot in enumerate(template):
        slot_pos = slot["pos"]
        bucket = POS_BUCKET.get(slot_pos, "MID")
        chosen = None
        chosen_source = None

        # 1. Try roster exact-pos match
        for p in roster_by_pos.get(slot_pos, []):
            pid = id(p)
            if pid in used_roster: continue
            chosen = p
            chosen_source = "roster"
            used_roster.add(pid)
            break

        # 2. Try roster same-bucket match (e.g., slot=DM, roster has CM)
        if not chosen:
            for pos_key, plist in roster_by_pos.items():
                if POS_BUCKET.get(pos_key) != bucket: continue
                for p in plist:
                    pid = id(p)
                    if pid in used_roster: continue
                    chosen = p
                    chosen_source = "roster"
                    used_roster.add(pid)
                    break
                if chosen: break

        # 2b. Try roster adjacent-bucket match (e.g., slot=CM, roster has AM —
        # happens when team_meta formation differs from roster's "natural" formation,
        # so a 4-3-3 template with no AM slot still places an AM-listed playmaker).
        if not chosen:
            adj_buckets = []
            if bucket == "MID": adj_buckets = ["AM"]
            elif bucket == "AM": adj_buckets = ["MID", "FW"]
            elif bucket == "FW": adj_buckets = ["AM"]
            for pos_key, plist in roster_by_pos.items():
                if POS_BUCKET.get(pos_key) not in adj_buckets: continue
                for p in plist:
                    pid = id(p)
                    if pid in used_roster: continue
                    chosen = p
                    chosen_source = "roster"
                    used_roster.add(pid)
                    break
                if chosen: break

        # 3. Try stars (bucket + adjacent)
        if not chosen:
            candidates = []
            if bucket in star_by_bucket: candidates.extend(star_by_bucket[bucket])
            if bucket == "FW" and "AM" in star_by_bucket: candidates.extend(star_by_bucket["AM"])
            if bucket == "AM" and "FW" in star_by_bucket: candidates.extend(star_by_bucket["FW"])
            if bucket == "MID" and "AM" in star_by_bucket: candidates.extend(star_by_bucket["AM"])
            for c in candidates:
                cid = id(c)
                if cid in used_stars: continue
                chosen = c
                chosen_source = "star"
                used_stars.add(cid)
                break

        x = (100 - slot["x"]) if mirror else slot["x"]
        if chosen:
            n = chosen.get("shirt") or (i + 1)
            name = short_name(chosen.get("nameZh") or chosen.get("name") or "")
        else:
            # 4. Final fallback: Chinese position label
            n = i + 1
            name = POS_ZH.get(slot_pos, slot_pos)

        lineup.append({"n": n, "name": name, "pos": slot_pos, "x": x, "y": slot["y"]})
    return lineup, formation


def make_arrows(formation, mirror=False):
    """Generic 2-arrow tactical hints based on formation. No text labels —
    legend handled separately by UI."""
    arrows_by_form = {
        "4-3-3":   [([60, 18], [78, 38]), ([68, 50], [85, 50])],
        "4-2-3-1": [([56, 18], [78, 32]), ([56, 50], [72, 42])],
        "4-4-2":   [([42, 18], [62, 38]), ([65, 38], [82, 50])],
        "3-5-2":   [([42, 50], [60, 38]), ([65, 38], [82, 45])],
        "5-3-2":   [([42, 30], [60, 40]), ([65, 38], [82, 45])],
        "3-4-3":   [([62, 22], [80, 35]), ([68, 50], [85, 50])],
    }
    labels = {
        "4-3-3":   ["邊路內切", "鋒線中路衝擊"],
        "4-2-3-1": ["邊鋒突破", "前腰直塞"],
        "4-4-2":   ["邊路傳中", "雙鋒搶點"],
        "3-5-2":   ["翼衛壓上", "前場聯動"],
        "5-3-2":   ["反擊長傳", "雙鋒前壓"],
        "3-4-3":   ["邊鋒爆破", "中鋒接應"],
    }
    base = arrows_by_form.get(formation, arrows_by_form["4-3-3"])
    lab = labels.get(formation, labels["4-3-3"])
    out = []
    for (frm, to), label in zip(base, lab):
        fx, fy = frm
        tx, ty = to
        if mirror:
            fx, tx = 100 - fx, 100 - tx
        out.append({"from": [fx, fy], "to": [tx, ty], "label": label})
    return out


def make_ball_routes(formation, mirror=False):
    """Generic passing-lane routes for the team's intended build-up.
    Solid lines (no arrowhead) drawn behind the players showing where
    the ball is meant to go. 2-3 routes per team, mirrored for away."""
    routes_by_form = {
        "4-3-3":   [([38, 50], [56, 50], "後腰→前場"),
                    ([56, 18], [70, 50], "右翼→中鋒"),
                    ([56, 82], [70, 50], "左翼→中鋒")],
        "4-2-3-1": [([38, 38], [56, 50], "後腰→前腰"),
                    ([56, 50], [70, 50], "前腰→中鋒"),
                    ([22, 18], [56, 18], "右後衛長傳右翼")],
        "4-4-2":   [([42, 40], [65, 38], "中場→中鋒"),
                    ([42, 18], [65, 38], "右中→中鋒"),
                    ([42, 82], [65, 62], "左中→中鋒")],
        "3-5-2":   [([42, 50], [65, 50], "中場→雙鋒"),
                    ([38, 14], [65, 38], "右翼衛→中鋒"),
                    ([38, 86], [65, 62], "左翼衛→中鋒")],
        "5-3-2":   [([42, 50], [65, 50], "中場→雙鋒"),
                    ([22, 14], [65, 38], "右後衛長傳"),
                    ([22, 86], [65, 62], "左後衛長傳")],
        "3-4-3":   [([42, 38], [62, 22], "中場→右翼"),
                    ([42, 62], [62, 78], "中場→左翼"),
                    ([42, 50], [68, 50], "中場→中鋒")],
    }
    base = routes_by_form.get(formation, routes_by_form["4-3-3"])
    out = []
    for frm, to, label in base:
        fx, fy = frm
        tx, ty = to
        if mirror:
            fx, tx = 100 - fx, 100 - tx
        out.append({"from": [fx, fy], "to": [tx, ty], "label": label})
    return out


def make_zones(formation, style, mirror=False):
    """1-2 highlighted zones describing where the team focuses its play.
    kind drives the color: press / create / wing / defense."""
    # Coordinates in home orientation (attacking left→right). Mirror for away.
    zones_by_form_style = {
        ("4-3-3", "進攻"):  [(35, 8, 28, 84, "高位逼搶區", "press"),
                             (52, 30, 22, 40, "創造區", "create")],
        ("4-3-3", "技術"):  [(28, 18, 32, 64, "控球區", "create"),
                             (50, 28, 28, 44, "滲透區", "create")],
        ("4-3-3", "均衡"):  [(50, 8, 26, 22, "右路衝擊", "wing"),
                             (50, 70, 26, 22, "左路衝擊", "wing")],
        ("4-3-3", "防守"):  [(8, 18, 28, 64, "後場屏障", "defense"),
                             (60, 30, 24, 40, "反擊起點", "press")],
        ("4-2-3-1", "進攻"): [(32, 8, 30, 84, "高位逼搶區", "press"),
                              (50, 30, 24, 40, "前腰串聯區", "create")],
        ("4-2-3-1", "技術"): [(30, 25, 34, 50, "控球節奏區", "create"),
                              (50, 8, 22, 22, "右路套邊", "wing")],
        ("4-2-3-1", "均衡"): [(48, 30, 26, 40, "前腰活動區", "create"),
                              (50, 8, 24, 22, "右翼壓上", "wing")],
        ("4-2-3-1", "防守"): [(8, 18, 26, 64, "雙後腰屏障", "defense"),
                              (58, 28, 28, 44, "反擊出球區", "press")],
        ("4-4-2", "進攻"):  [(35, 8, 30, 22, "右路傳中區", "wing"),
                             (35, 70, 30, 22, "左路傳中區", "wing")],
        ("4-4-2", "技術"):  [(28, 22, 36, 56, "中場控制區", "create")],
        ("4-4-2", "均衡"):  [(40, 30, 30, 40, "中前場壓迫", "press")],
        ("4-4-2", "防守"):  [(8, 18, 28, 64, "後場 4-4 屏障", "defense")],
        ("3-5-2", "進攻"):  [(28, 8, 22, 22, "右翼衛壓上", "wing"),
                             (28, 70, 22, 22, "左翼衛壓上", "wing")],
        ("3-5-2", "技術"):  [(28, 25, 36, 50, "中場控制區", "create")],
        ("3-5-2", "均衡"):  [(50, 30, 28, 40, "前場聯動區", "create")],
        ("3-5-2", "防守"):  [(8, 18, 28, 64, "三中衛 + 雙後腰", "defense")],
        ("5-3-2", "進攻"):  [(48, 30, 28, 40, "雙鋒前壓區", "press")],
        ("5-3-2", "技術"):  [(28, 25, 36, 50, "中場控制區", "create")],
        ("5-3-2", "均衡"):  [(8, 14, 32, 72, "五人後場", "defense")],
        ("5-3-2", "防守"):  [(8, 14, 32, 72, "五人後場屏障", "defense"),
                             (60, 30, 22, 40, "反擊起點", "press")],
        ("3-4-3", "進攻"):  [(50, 8, 28, 22, "右翼爆破", "wing"),
                             (50, 70, 28, 22, "左翼爆破", "wing")],
        ("3-4-3", "技術"):  [(28, 22, 36, 56, "三中衛出球", "create")],
        ("3-4-3", "均衡"):  [(50, 30, 26, 40, "三鋒線中路", "press")],
        ("3-4-3", "防守"):  [(8, 18, 30, 64, "三後衛 + 雙翼衛", "defense")],
    }
    base = zones_by_form_style.get((formation, style)) \
        or zones_by_form_style.get((formation, "均衡")) \
        or [(28, 30, 36, 40, "戰術核心區", "create")]

    out = []
    for x, y, w, h, label, kind in base:
        if mirror:
            # Mirror x: the rect's right edge becomes (100 - x), so new x = 100 - x - w
            x = 100 - x - w
        out.append({"x": x, "y": y, "w": w, "h": h, "label": label, "kind": kind})
    return out


def predict_score(home_stats, away_stats):
    """Rule-based prediction. Returns dict with score / confidence / winner /
    reasoning / scenarios."""
    weights = {"attack": 0.35, "midfield": 0.25, "defense": 0.25,
               "stars": 0.10, "experience": 0.05}
    diff = sum(weights[k] * (home_stats.get(k, 5) - away_stats.get(k, 5))
               for k in weights)
    # Map diff (~ -5..+5) → expected goals delta
    base_h = 1.4 + max(-1, min(1.5, diff * 0.6))
    base_a = 1.4 - max(-1, min(1.5, diff * 0.6))
    h_goals = max(0, round(base_h))
    a_goals = max(0, round(base_a))
    # Prevent 0-0 draws — bump the stronger side
    if h_goals == 0 and a_goals == 0:
        if diff >= 0: h_goals = 1
        else: a_goals = 1

    if h_goals > a_goals:
        winner = "home"
    elif a_goals > h_goals:
        winner = "away"
    else:
        winner = "draw"

    confidence = int(min(85, 50 + 8 * abs(diff)))

    # Reasoning: top 2 axis differences
    axis_zh = {"attack": "進攻", "midfield": "中場控制",
               "defense": "防守", "stars": "球星", "experience": "經驗",
               "fitness": "體能"}
    axis_diffs = sorted(
        [(k, home_stats.get(k, 5) - away_stats.get(k, 5))
         for k in ["attack", "midfield", "defense", "stars", "experience", "fitness"]],
        key=lambda x: -abs(x[1])
    )
    top = axis_diffs[:2]
    reason_parts = []
    for k, d in top:
        if abs(d) < 0.3: continue
        side = "主隊" if d > 0 else "客隊"
        reason_parts.append(f"{side}在{axis_zh[k]}佔優 ({abs(d):.1f})")
    if not reason_parts:
        reason_parts.append("雙方實力極為接近")
    reasoning = "；".join(reason_parts) + (
        "，預期主隊取勝。" if winner == "home" else
        "，預期客隊取勝。" if winner == "away" else
        "，預期勢均力敵。"
    )

    # Scenarios: build 5 likely outcomes around the prediction
    pred = (h_goals, a_goals)
    candidates = [pred]
    for dh in (-1, 0, 1):
        for da in (-1, 0, 1):
            cand = (max(0, h_goals + dh), max(0, a_goals + da))
            if cand not in candidates:
                candidates.append(cand)
    candidates = candidates[:5]
    # Probabilities: predicted outcome biggest, others taper off
    probs = [30, 22, 18, 16, 14][:len(candidates)]
    # Normalize to 100
    total = sum(probs)
    probs = [int(round(p * 100 / total)) for p in probs]
    diff_total = 100 - sum(probs)
    probs[0] += diff_total

    scenarios = []
    for (h, a), p in zip(candidates, probs):
        scenarios.append({
            "score": f"{h}-{a}",
            "prob": p,
            "desc": "預測比分" if (h, a) == pred else "可能情境",
        })

    return {
        "score": f"{h_goals}-{a_goals}",
        "confidence": confidence,
        "winner": winner if winner != "draw" else "home",
        "reasoning": reasoning,
        "scenarios": scenarios,
    }


def make_timeline(predict, h_code, a_code):
    """Synthetic timeline keyed off predicted score.
    Goal text reflects the running score at the time of that goal."""
    h, a = predict["score"].split("-")
    h, a = int(h), int(a)
    fav = "home" if predict["winner"] == "home" else "away"
    events = [{"min": 5, "side": fav, "type": "control",
               "text": "開場掌控節奏，逐步建立攻勢"}]

    # Distribute goals across the match (earlier = open, later = clincher)
    goal_min = []
    if h >= 1: goal_min.append((35, "home"))
    if h >= 2: goal_min.append((68, "home"))
    if h >= 3: goal_min.append((85, "home"))
    if a >= 1: goal_min.append((52, "away"))
    if a >= 2: goal_min.append((78, "away"))
    if a >= 3: goal_min.append((88, "away"))
    goal_min.sort()

    # Build running score + situation-aware text per goal
    rh, ra = 0, 0
    for m, side in goal_min:
        # Pre-goal state to decide text
        before_h, before_a = rh, ra
        if side == "home":
            rh += 1
            my_before, opp_before = before_h, before_a
        else:
            ra += 1
            my_before, opp_before = before_a, before_h

        if my_before == 0 and opp_before == 0:
            text = "率先破門，取得領先"
        elif my_before == opp_before:
            text = "反超比分，奪回領先" if m >= 60 else "再下一城，取得領先"
        elif my_before < opp_before:
            # was trailing
            text = "扳平比分" if my_before + 1 == opp_before else "扳回一城"
        else:
            # was already leading
            text = "鎖定勝局" if m >= 80 else "擴大領先"

        if m >= 88:
            text = ("絕殺破門！" if my_before <= opp_before else "終場前再下一城") + "（" + text + "）"

        events.append({
            "min": m, "side": side, "type": "goal",
            "text": text,
            "score": f"{rh}-{ra}",
        })

    # Halftime score = state at minute 45 (only goals with min < 45)
    half_h = sum(1 for m, s in goal_min if m < 45 and s == "home")
    half_a = sum(1 for m, s in goal_min if m < 45 and s == "away")
    half_text = (f"半場：{h_code} {half_h}-{half_a} {a_code}"
                 if (half_h + half_a) > 0 else f"半場：{h_code} 0-0 {a_code}")
    events.append({"min": 45, "side": "neutral", "type": "halftime", "text": half_text})
    events.append({"min": 90, "side": "neutral", "type": "fulltime",
                   "text": f"全場：{h_code} {h}-{a} {a_code}"})

    events.sort(key=lambda e: e["min"])
    return events


def key_duels(home_code, away_code, stars, h_lineup, a_lineup):
    """Pick 3 key matchups: top FW vs CB, top AM vs DM, top star (any) vs counterpart.
    Falls back to lineup positions when stars data is missing."""
    h_stars = stars.get(home_code, [])
    a_stars = stars.get(away_code, [])
    duels = []

    def first_by_pos(slist, positions):
        for s in slist:
            if s.get("pos") in positions:
                return s
        return None

    def lineup_first(lineup, positions):
        for p in lineup:
            if p["pos"] in positions:
                return p
        return None

    def name_or_pos(star, fallback_lineup, positions, side_code):
        if star:
            return star.get("nameZh") or star.get("name") or "—"
        lp = lineup_first(fallback_lineup, positions)
        if lp:
            return f"{side_code} #{lp['n']} ({lp['pos']})"
        return f"{side_code} 核心"

    h_fw = first_by_pos(h_stars, {"ST", "CF", "LW", "RW"})
    a_cb = first_by_pos(a_stars, {"CB"})
    duels.append({
        "home": name_or_pos(h_fw, h_lineup, {"ST", "CF", "LW", "RW"}, home_code),
        "away": name_or_pos(a_cb, a_lineup, {"CB"}, away_code),
        "note": "鋒線 vs 後衛 — 禁區內的關鍵對抗",
    })

    a_fw = first_by_pos(a_stars, {"ST", "CF", "LW", "RW"})
    h_cb = first_by_pos(h_stars, {"CB"})
    duels.append({
        "home": name_or_pos(h_cb, h_lineup, {"CB"}, home_code),
        "away": name_or_pos(a_fw, a_lineup, {"ST", "CF", "LW", "RW"}, away_code),
        "note": "防守 vs 進攻 — 客隊鋒線能否突破",
    })

    h_mid = first_by_pos(h_stars, {"AM", "CM", "DM"})
    a_mid = first_by_pos(a_stars, {"AM", "CM", "DM"})
    duels.append({
        "home": name_or_pos(h_mid, h_lineup, {"AM", "CM", "DM"}, home_code),
        "away": name_or_pos(a_mid, a_lineup, {"AM", "CM", "DM"}, away_code),
        "note": "中場控制 — 誰主導節奏誰勝",
    })

    return duels[:3]


def default_referee():
    return {
        "style": "待定",
        "tendency": "FIFA 將在比賽前公布主裁判，依據裁判執法風格再行分析",
        "impact": "暫無資料",
    }


# Tactics templates keyed by (formation, primary_style). Each returns 3 short bullets
# describing how the team will likely play. Style values come from teams_analysis.json.
TACTICS_TEMPLATES = {
    ("4-3-3", "進攻"):  ["雙翼速度衝擊邊路", "中場三人組高位逼搶", "鋒線中路接應內切"],
    ("4-3-3", "技術"):  ["短傳滲透打開空間", "中場控球節奏壓制", "邊鋒內收創造肋部"],
    ("4-3-3", "均衡"):  ["邊路傳中找中鋒搶點", "中場輪轉支援防守", "邊後衛伺機壓上助攻"],
    ("4-3-3", "防守"):  ["雙邊鋒回防組成 4-5-1", "後腰拖後保護後衛線", "反擊找中鋒長傳"],
    ("4-2-3-1", "進攻"): ["邊鋒突破到底線傳中", "前腰直塞中鋒身後", "雙後腰其一壓上助攻"],
    ("4-2-3-1", "技術"): ["前腰拉邊串聯三線", "雙後腰其一前插製造人數", "中鋒回撤拉開空間"],
    ("4-2-3-1", "均衡"): ["邊路傳中與中路滲透並進", "雙後腰一攻一守", "定位球是重要得分手段"],
    ("4-2-3-1", "防守"): ["低位防守等待反擊", "邊鋒快速轉移找中鋒", "前腰回撤組成 4-5-1"],
    ("4-4-2", "進攻"):  ["雙鋒搶點配合邊路傳中", "邊前衛提速插上", "中前場壓迫對方出球"],
    ("4-4-2", "技術"):  ["中場四人組維持控球", "兩前鋒一回撤一搶點", "兩翼適時內收"],
    ("4-4-2", "均衡"):  ["緊湊 4-4 兩線間距防守", "兩翼快速轉移", "雙鋒前後距離配合"],
    ("4-4-2", "防守"):  ["低位密集防守", "雙鋒留前等待長傳反擊", "邊前衛回防補位"],
    ("3-5-2", "進攻"):  ["雙翼衛全力壓上製造寬度", "雙鋒前壓拉扯後衛線", "後腰送威脅球"],
    ("3-5-2", "技術"):  ["三後衛短傳出球建立節奏", "翼衛伺機助攻", "中場三角形傳遞"],
    ("3-5-2", "均衡"):  ["翼衛攻守兼備", "三中衛保護中路", "雙鋒交替回撤接應"],
    ("3-5-2", "防守"):  ["五人後場退守 (3+2)", "等待長傳找雙鋒反擊", "中場全員回防"],
    ("5-3-2", "進攻"):  ["翼衛伺機壓上製造邊路寬度", "三中場前插支援", "雙鋒拉扯後衛線"],
    ("5-3-2", "技術"):  ["五後衛擴張邊路", "中場三人組短傳推進", "鋒線回撤接應"],
    ("5-3-2", "均衡"):  ["五人後場保證防線厚度", "中場穩定推進", "雙鋒一搶點一回撤"],
    ("5-3-2", "防守"):  ["低位密集防守 5 後衛保護中路", "雙鋒反擊轉移", "翼衛伺機壓上肋部"],
    ("3-4-3", "進攻"):  ["三鋒線拉開寬度", "雙後腰前壓支援", "邊翼衛快速套邊"],
    ("3-4-3", "技術"):  ["三中衛出球建立節奏", "中前場形成菱形傳遞", "邊鋒內收肋部"],
    ("3-4-3", "均衡"):  ["三後衛 + 雙翼衛 5 人防守", "三鋒線中路 + 兩肋", "中場搶斷後快速分邊"],
    ("3-4-3", "防守"):  ["三後衛 + 雙翼衛回收 5-4-1", "鋒線回防為三中場", "等待反擊長傳"],
}

# Strength keyword → bonus tactical bullet. Allows fine-tuning beyond the template.
STRENGTH_KEYWORD_BULLETS = {
    "邊路速度": "邊鋒/邊後衛速度爆破將是進攻關鍵",
    "邊路": "邊路傳中與套邊配合密集",
    "定位球": "角球與任意球是重要得分手段",
    "高位逼搶": "前場高位壓迫切斷對手出球",
    "反擊": "防守反擊轉換速度極快",
    "中場": "中場控制是壓制比賽的核心",
    "後防": "後防穩固，難以被打穿",
    "鋒線": "鋒線終結效率極高",
    "球星": "球星個人能力可以解決僵局",
    "經驗": "大賽經驗豐富，關鍵時刻不慌",
}


def make_tactics(code, team_meta, analysis):
    """Return list of 3 short tactical bullets for the given team."""
    meta = team_meta.get(code, {})
    formation = meta.get("formation", "4-3-3")
    info = analysis.get(code, {}) or {}
    style = info.get("style", "均衡")
    strength = info.get("strength", "")

    base = TACTICS_TEMPLATES.get((formation, style)) or TACTICS_TEMPLATES.get((formation, "均衡"))
    if not base:
        base = ["陣型內球員按位置責任分工", "中場負責節奏與控制", "鋒線伺機完成攻勢"]

    bullets = list(base)
    # If a strength keyword matches, replace the third bullet with a more specific one
    for kw, bullet in STRENGTH_KEYWORD_BULLETS.items():
        if kw in strength:
            if bullet not in bullets:
                bullets[-1] = bullet
            break
    return bullets[:3]


def gen_match_preview(m, analysis, stars, team_meta, templates, rosters=None):
    """Auto-generate preview entry for one match."""
    h_code = m["home"]["code"].upper()
    a_code = m["away"]["code"].upper()
    h_meta = team_meta.get(h_code, {"formation": "4-3-3", "manager": "—",
                                     "flagEmoji": "🏳", "color": "#888888"})
    a_meta = team_meta.get(a_code, {"formation": "4-3-3", "manager": "—",
                                     "flagEmoji": "🏳", "color": "#888888"})
    h_an = analysis.get(h_code, {})
    a_an = analysis.get(a_code, {})
    h_stats = h_an.get("stats") or {"attack": 5, "defense": 5, "midfield": 5,
                                     "fitness": 5, "experience": 5, "stars": 5}
    a_stats = a_an.get("stats") or {"attack": 5, "defense": 5, "midfield": 5,
                                     "fitness": 5, "experience": 5, "stars": 5}

    h_lineup, h_form = make_lineup(h_code, team_meta, stars, templates, mirror=False, rosters=rosters)
    a_lineup, a_form = make_lineup(a_code, team_meta, stars, templates, mirror=True, rosters=rosters)
    h_arrows = make_arrows(h_form, mirror=False)
    a_arrows = make_arrows(a_form, mirror=True)
    h_routes = make_ball_routes(h_form, mirror=False)
    a_routes = make_ball_routes(a_form, mirror=True)
    h_style = (h_an.get("style") or "均衡")
    a_style = (a_an.get("style") or "均衡")
    h_zones = make_zones(h_form, h_style, mirror=False)
    a_zones = make_zones(a_form, a_style, mirror=True)

    predict = predict_score(h_stats, a_stats)
    timeline = make_timeline(predict, h_code, a_code)
    duels = key_duels(h_code, a_code, stars, h_lineup, a_lineup)
    tactics = {
        "home": make_tactics(h_code, team_meta, analysis),
        "away": make_tactics(a_code, team_meta, analysis),
    }

    h_zh = ZH.get(h_code, m["home"].get("name", h_code))
    a_zh = ZH.get(a_code, m["away"].get("name", a_code))
    h_flag = h_meta.get("flagEmoji", "🏳")
    a_flag = a_meta.get("flagEmoji", "🏳")

    return {
        "id": f"{h_code}_{a_code}_{m.get('no', 0)}",
        "_auto": True,
        "_kickoffUtc": m.get("utc", ""),
        "_matchNo": m.get("no", 0),
        "title": f"{h_zh} {h_flag} vs {a_flag} {a_zh}",
        "shortTitle": f"{h_code} vs {a_code}",
        "subtitle": f"FIFA 排名 #{h_an.get('rank','?')} vs #{a_an.get('rank','?')}",
        "stage": STAGE_LABEL_ZH.get(m.get("stage", "group"), m.get("stage", "")),
        "venue": f"{m.get('venue', '?')} ({m.get('city', '')})".strip().rstrip("()").strip(),
        "history": [],
        "home": {
            "code": h_code, "name": h_zh, "flag": h_flag,
            "color": h_meta.get("color", "#ffffff"),
            "colorAlt": h_meta.get("color", "#ffffff"),
            "manager": h_meta.get("manager", "—"),
            "formation": h_form,
            "lineup": h_lineup,
            "arrows": h_arrows,
            "ballRoutes": h_routes,
            "zones": h_zones,
            "stats": h_stats,
        },
        "away": {
            "code": a_code, "name": a_zh, "flag": a_flag,
            "color": a_meta.get("color", "#cccccc"),
            "colorAlt": a_meta.get("color", "#cccccc"),
            "manager": a_meta.get("manager", "—"),
            "formation": a_form,
            "lineup": a_lineup,
            "arrows": a_arrows,
            "ballRoutes": a_routes,
            "zones": a_zones,
            "stats": a_stats,
        },
        "timeline": timeline,
        "referee": default_referee(),
        "keyDuels": duels,
        "tactics": tactics,
        "predict": predict,
    }


def load_overrides():
    out = {}
    if not OVERRIDE_DIR.exists(): return out
    for p in OVERRIDE_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out[p.stem] = data
        except Exception as e:
            print(f"override load failed {p}: {e}", file=sys.stderr)
    return out


def build_preview(schedule, analysis, stars, team_meta, templates, rosters=None):
    overrides = load_overrides()
    seen_keys = set()
    used_override_keys = set()
    matches_out = []

    for m in schedule.get("matches", []):
        if not (team_is_confirmed(m.get("home")) and team_is_confirmed(m.get("away"))):
            continue
        h_code = m["home"]["code"].upper()
        a_code = m["away"]["code"].upper()
        stage = m.get("stage", "group")

        # Group: only marquee close-rank matches
        if stage == "group" and not is_marquee_group_match(h_code, a_code, analysis):
            continue
        # Knockout: include all confirmed matches

        key = match_key(h_code, a_code)
        # Knockout pairings can repeat group-stage matchups; differentiate by match #
        unique_key = f"{key}_{m.get('no', 0)}"
        if unique_key in seen_keys: continue
        seen_keys.add(unique_key)

        if key in overrides:
            entry = dict(overrides[key])
            entry.setdefault("_auto", False)
            entry["_kickoffUtc"] = m.get("utc", "")
            entry["_matchNo"] = m.get("no", 0)
            used_override_keys.add(key)
            # Update stage if needed (overrides may say group, but match is now r32)
            if "stage" not in entry or not entry.get("stage"):
                entry["stage"] = STAGE_LABEL_ZH.get(stage, stage)
            matches_out.append(entry)
        else:
            matches_out.append(gen_match_preview(m, analysis, stars, team_meta, templates, rosters=rosters))

    matches_out.sort(key=lambda x: (x.get("_kickoffUtc") or "", x.get("_matchNo", 0)))

    # Append unmatched hand-written overrides at the end (hypothetical previews
    # the user wrote that don't correspond to a scheduled match yet).
    for key, entry in sorted(overrides.items()):
        if key in used_override_keys: continue
        e = dict(entry)
        e.setdefault("_auto", False)
        e.setdefault("_kickoffUtc", "")
        e.setdefault("_matchNo", 9999)
        e["_hypothetical"] = True
        matches_out.append(e)

    return {
        "_generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "_note": (
            "戰報前瞻：淘汰賽全部、小組賽強強對決 (FIFA 排名差距 ≤ "
            f"{RANK_GAP_MAX} 且最佳排名 ≤ {RANK_BEST_MAX}) 自動生成。"
            "手寫戰報優先於自動生成。"
        ),
        "matches": matches_out,
    }


def main():
    schedule = json.loads((DATA / "schedule.json").read_text(encoding="utf-8"))
    analysis = json.loads((DATA / "teams_analysis.json").read_text(encoding="utf-8"))
    stars = json.loads((DATA / "stars.json").read_text(encoding="utf-8"))
    team_meta = json.loads((DATA / "team_meta.json").read_text(encoding="utf-8"))
    templates = json.loads((DATA / "lineup_templates.json").read_text(encoding="utf-8"))
    rosters_path = DATA / "rosters.json"
    rosters = json.loads(rosters_path.read_text(encoding="utf-8")) if rosters_path.exists() else {}

    preview = build_preview(schedule, analysis, stars, team_meta, templates, rosters=rosters)
    out = DATA / "preview.json"
    out.write_text(json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8")
    auto = sum(1 for m in preview["matches"] if m.get("_auto"))
    manual = len(preview["matches"]) - auto
    print(f"Wrote {out} ({len(preview['matches'])} matches: {manual} manual, {auto} auto)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
