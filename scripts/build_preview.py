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
    "CB": "DEF", "LB": "DEF", "RB": "DEF",
    "DM": "MID", "CM": "MID", "LM": "MID", "RM": "MID",
    "AM": "AM",
    "LW": "FW", "RW": "FW", "ST": "FW", "CF": "FW",
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


def make_lineup(code, team_meta, stars, templates, mirror=False):
    """Produce 11 player dicts. Star roster fills 4 slots by position bucket;
    rest are placeholders like '#7 RW'."""
    meta = team_meta.get(code, {})
    formation = meta.get("formation", "4-3-3")
    template = templates.get(formation, templates["4-3-3"])

    star_list = list(stars.get(code, []))
    # Group stars by bucket
    star_by_bucket = {}
    for s in star_list:
        b = POS_BUCKET.get(s.get("pos", ""), "MID")
        star_by_bucket.setdefault(b, []).append(s)

    used_stars = set()
    lineup = []
    for i, slot in enumerate(template):
        bucket = POS_BUCKET.get(slot["pos"], "MID")
        # Try exact-bucket star, then adjacent buckets
        candidates = []
        if bucket in star_by_bucket:
            candidates.extend(star_by_bucket[bucket])
        if bucket == "FW" and "AM" in star_by_bucket:
            candidates.extend(star_by_bucket["AM"])
        if bucket == "AM" and "FW" in star_by_bucket:
            candidates.extend(star_by_bucket["FW"])
        if bucket == "MID" and "AM" in star_by_bucket:
            candidates.extend(star_by_bucket["AM"])

        chosen = None
        for c in candidates:
            cid = id(c)
            if cid in used_stars: continue
            chosen = c
            used_stars.add(cid)
            break

        x = (100 - slot["x"]) if mirror else slot["x"]
        if chosen:
            n = chosen.get("shirt") or (i + 1)
            name = short_name(chosen.get("nameZh") or chosen.get("name") or "")
        else:
            n = i + 1
            name = slot["pos"]

        lineup.append({"n": n, "name": name, "pos": slot["pos"], "x": x, "y": slot["y"]})
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
    """Synthetic 8-event arc keyed off predicted score."""
    h, a = predict["score"].split("-")
    h, a = int(h), int(a)
    fav = "home" if predict["winner"] == "home" else "away"
    events = [{"min": 5, "side": fav, "type": "control",
               "text": "開場掌控節奏，逐步建立攻勢"}]

    # Distribute home goals across first half / late, away similarly
    goal_min = []
    if h >= 1: goal_min.append((35, "home", "open"))
    if h >= 2: goal_min.append((68, "home", "second"))
    if h >= 3: goal_min.append((85, "home", "third"))
    if a >= 1: goal_min.append((52, "away", "open"))
    if a >= 2: goal_min.append((78, "away", "second"))
    if a >= 3: goal_min.append((88, "away", "third"))
    goal_min.sort()

    # Build running score
    running = [0, 0]
    home_idx, away_idx = 0, 1
    for m, side, _ in goal_min:
        if side == "home": running[0] += 1
        else: running[1] += 1
        events.append({
            "min": m, "side": side, "type": "goal",
            "text": "破門，比分擴大" if side == fav else "扳回一城",
            "score": f"{running[0]}-{running[1]}",
        })

    # Add halftime + chance + fulltime
    events.append({"min": 45, "side": "neutral", "type": "halftime",
                   "text": f"半場：{h_code} {running[0]}-{running[1]} {a_code} (中場時)"
                   if any(g[0] < 45 for g in goal_min) else f"半場：0-0"})
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


def gen_match_preview(m, analysis, stars, team_meta, templates):
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

    h_lineup, h_form = make_lineup(h_code, team_meta, stars, templates, mirror=False)
    a_lineup, a_form = make_lineup(a_code, team_meta, stars, templates, mirror=True)
    h_arrows = make_arrows(h_form, mirror=False)
    a_arrows = make_arrows(a_form, mirror=True)

    predict = predict_score(h_stats, a_stats)
    timeline = make_timeline(predict, h_code, a_code)
    duels = key_duels(h_code, a_code, stars, h_lineup, a_lineup)

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
            "stats": a_stats,
        },
        "timeline": timeline,
        "referee": default_referee(),
        "keyDuels": duels,
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


def build_preview(schedule, analysis, stars, team_meta, templates):
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
            matches_out.append(gen_match_preview(m, analysis, stars, team_meta, templates))

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

    preview = build_preview(schedule, analysis, stars, team_meta, templates)
    out = DATA / "preview.json"
    out.write_text(json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8")
    auto = sum(1 for m in preview["matches"] if m.get("_auto"))
    manual = len(preview["matches"]) - auto
    print(f"Wrote {out} ({len(preview['matches'])} matches: {manual} manual, {auto} auto)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
