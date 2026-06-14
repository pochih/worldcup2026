#!/usr/bin/env python3
"""Fetch FIFA 2026 World Cup data and build site JSON.

Run daily via GitHub Actions to refresh live scores, then commit.
"""
import csv
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

FIFA_URL = (
    "https://api.fifa.com/api/v3/calendar/matches"
    "?idCompetition=17&idSeason=285023&count=200&language=en"
)

# Taiwan broadcasters (best-known sources as of 2026). Update as confirmed.
# Elta Sports holds Taiwan rights; PTS shows selected matches free-to-air.
DEFAULT_TW_BROADCAST = ["愛爾達體育台"]
PTS_FREE_MATCHES = {1, 39, 73, 97, 101, 102, 103, 104}  # opener, TWN-relevant slots, knockouts


def pick(loc_list, default=""):
    """Pull English description from FIFA's localized array."""
    if not loc_list:
        return default
    raw = None
    for x in loc_list:
        if x.get("Locale", "").startswith("en"):
            raw = x.get("Description") or ""
            break
    if raw is None:
        raw = loc_list[0].get("Description") or ""
    # FIFA pads some strings with U+0080 (control char). Strip non-printable.
    cleaned = "".join(c for c in raw if c.isprintable() or c.isspace())
    return cleaned.strip() or default


def fetch_fifa():
    req = Request(FIFA_URL, headers={"User-Agent": "Mozilla/5.0 wc2026-site"})
    with urlopen(req, timeout=30) as r:
        return json.load(r)


def load_stadiums():
    """Parse openfootball stadiums CSV → dict keyed by city name."""
    out = {}
    path = DATA / "stadiums.csv"
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("city,"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 5:
                continue
            city, tz, cc, name, cap = parts[0], parts[1], parts[2], parts[3], parts[4]
            out[name] = {"city": city, "tz": tz, "country": cc.upper(), "capacity": cap}
    return out


# Group letter from FIFA IdGroup (289275=A … 289286=L for season 285023)
GROUP_ID_TO_LETTER = {
    "289275": "A", "289276": "B", "289277": "C", "289278": "D",
    "289279": "E", "289280": "F", "289281": "G", "289282": "H",
    "289283": "I", "289284": "J", "289285": "K", "289286": "L",
}


def stage_kind(stage_desc, group_desc):
    s = (stage_desc or "").lower()
    if group_desc:
        return "group"
    if "round of 32" in s or "1/16" in s:
        return "r32"
    if "round of 16" in s or "1/8" in s:
        return "r16"
    if "quarter" in s:
        return "qf"
    if "semi" in s:
        return "sf"
    if "third" in s or "play-off for third" in s:
        return "third"
    if "final" in s:
        return "final"
    return "group"


def transform(raw, stadiums):
    matches = []
    teams = {}
    for m in raw.get("Results", []):
        home = m.get("Home") or {}
        away = m.get("Away") or {}
        stage = pick(m.get("StageName"))
        grp_desc = pick(m.get("GroupName"))
        group = grp_desc.replace("Group ", "").strip() if grp_desc else GROUP_ID_TO_LETTER.get(str(m.get("IdGroup") or ""), "")
        st_name = pick((m.get("Stadium") or {}).get("Name") or [])
        city = pick((m.get("Stadium") or {}).get("CityName") or [])
        meta = stadiums.get(st_name, {})

        match_no = m.get("MatchNumber") or 0
        tw_broadcast = list(DEFAULT_TW_BROADCAST)
        if match_no in PTS_FREE_MATCHES:
            tw_broadcast.append("公視（無線轉播）")

        rec = {
            "id": m.get("IdMatch"),
            "no": match_no,
            "stage": stage_kind(stage, grp_desc),
            "stageLabel": stage,
            "group": group,
            "utc": m.get("Date"),
            "localKick": m.get("LocalDate"),
            "status": m.get("MatchStatus"),  # FIFA: 0=played(final), 1=scheduled, 3=live (approx)
            "resultType": m.get("ResultType"),
            "venue": st_name,
            "city": city or meta.get("city", ""),
            "tz": meta.get("tz", ""),
            "country": (m.get("Stadium") or {}).get("IdCountry"),
            "placeholderHome": m.get("PlaceHolderA"),
            "placeholderAway": m.get("PlaceHolderB"),
            "home": {
                "id": home.get("IdTeam"),
                "code": home.get("Abbreviation"),
                "name": pick(home.get("TeamName")) or home.get("ShortClubName"),
                "flag": (home.get("PictureUrl") or "").replace("{format}", "sq").replace("{size}", "4"),
                "score": m.get("HomeTeamScore"),
                "pen": m.get("HomeTeamPenaltyScore"),
            },
            "away": {
                "id": away.get("IdTeam"),
                "code": away.get("Abbreviation"),
                "name": pick(away.get("TeamName")) or away.get("ShortClubName"),
                "flag": (away.get("PictureUrl") or "").replace("{format}", "sq").replace("{size}", "4"),
                "score": m.get("AwayTeamScore"),
                "pen": m.get("AwayTeamPenaltyScore"),
            },
            "winner": m.get("Winner"),
            "attendance": m.get("Attendance"),
            "twBroadcast": tw_broadcast,
        }
        matches.append(rec)

        for side in (home, away):
            tid = side.get("IdTeam")
            if tid and tid not in teams:
                teams[tid] = {
                    "id": tid,
                    "code": side.get("Abbreviation"),
                    "name": pick(side.get("TeamName")) or side.get("ShortClubName"),
                    "flag": (side.get("PictureUrl") or "").replace("{format}", "sq").replace("{size}", "4"),
                    "country": side.get("IdCountry"),
                }

    matches.sort(key=lambda x: (x["no"] or 0))
    return matches, teams


def build_standings(matches):
    """Compute 12 group standings: W/D/L/GF/GA/GD/Pts."""
    table = {}  # group → {teamId: row}
    for m in matches:
        if m["stage"] != "group":
            continue
        g = m["group"]
        if not g:
            continue
        h, a = m["home"], m["away"]
        if not (h["id"] and a["id"]):
            continue
        table.setdefault(g, {})
        for t in (h, a):
            table[g].setdefault(
                t["id"],
                {"id": t["id"], "code": t["code"], "name": t["name"],
                 "flag": t["flag"], "P": 0, "W": 0, "D": 0, "L": 0,
                 "GF": 0, "GA": 0, "GD": 0, "Pts": 0},
            )
        # Match is final when score is present AND ResultType is set (1=normal time decided)
        played = (
            h["score"] is not None and a["score"] is not None
            and m.get("resultType") is not None
        )
        if not played:
            continue
        hr, ar = table[g][h["id"]], table[g][a["id"]]
        hs, as_ = h["score"], a["score"]
        hr["P"] += 1; ar["P"] += 1
        hr["GF"] += hs; hr["GA"] += as_; hr["GD"] = hr["GF"] - hr["GA"]
        ar["GF"] += as_; ar["GA"] += hs; ar["GD"] = ar["GF"] - ar["GA"]
        if hs > as_:
            hr["W"] += 1; hr["Pts"] += 3; ar["L"] += 1
        elif hs < as_:
            ar["W"] += 1; ar["Pts"] += 3; hr["L"] += 1
        else:
            hr["D"] += 1; ar["D"] += 1; hr["Pts"] += 1; ar["Pts"] += 1

    standings = {}
    for g, rows in table.items():
        sorted_rows = sorted(
            rows.values(),
            key=lambda r: (-r["Pts"], -r["GD"], -r["GF"], r["name"]),
        )
        standings[g] = sorted_rows
    return standings


def main():
    raw = fetch_fifa()
    (DATA / "fifa_raw.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    stadiums = load_stadiums()
    matches, teams = transform(raw, stadiums)
    standings = build_standings(matches)

    bundle = {
        "generatedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "totalMatches": len(matches),
        "matches": matches,
        "teams": teams,
        "standings": standings,
    }
    out = DATA / "schedule.json"
    out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(matches)} matches, {len(teams)} teams)", file=sys.stderr)


if __name__ == "__main__":
    main()
