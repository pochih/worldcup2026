#!/usr/bin/env python3
"""Fetch official FIFA 2026 World Cup 26-man squads with confirmed shirt numbers.

Strategy: iterate schedule.json for each unique team, hit FIFA live/football
endpoint for one match featuring that team to read HomeTeam/AwayTeam.Players
(26 entries each with ShirtNumber, Position, Captain, PictureUrl). Merge with
existing rosters.json preserving handcrafted nameZh translations where available.

Position codes from FIFA API:
  0 = GK
  1 = DEF (CB/LB/RB)
  2 = MID (DM/CM/AM)
  3 = FWD (LW/RW/ST)
"""
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LIVE_URL = (
    "https://api.fifa.com/api/v3/live/football/17/285023/{stage}/{match}?language=en"
)

POS_LABEL = {0: "GK", 1: "DEF", 2: "MID", 3: "FWD"}


def pick_en(loc_list):
    if not loc_list:
        return ""
    for x in loc_list:
        if x.get("Locale", "").startswith("en"):
            return (x.get("Description") or "").strip()
    return (loc_list[0].get("Description") or "").strip()


def fetch_live(stage_id, match_id):
    url = LIVE_URL.format(stage=stage_id, match=match_id)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 wc2026-site"})
    with urlopen(req, timeout=25) as r:
        return json.load(r)


def main():
    schedule = json.loads((DATA / "schedule.json").read_text(encoding="utf-8"))
    fifa_raw = json.loads((DATA / "fifa_raw.json").read_text(encoding="utf-8"))

    # Build IdMatch -> IdStage map from fifa_raw
    raw_matches = fifa_raw.get("Results", []) if isinstance(fifa_raw, dict) else fifa_raw
    if isinstance(raw_matches, dict):
        raw_matches = raw_matches.get("Results", [])
    stage_by_match = {m.get("IdMatch"): m.get("IdStage") for m in raw_matches}

    # Pick one match per team (prefer earliest played match for stable squad)
    seen_teams = {}  # code -> (id_team, id_match, id_stage)
    for m in schedule.get("matches", []):
        for side in ("home", "away"):
            t = m.get(side, {})
            code = t.get("code")
            if not code or code in seen_teams:
                continue
            stage_id = stage_by_match.get(m["id"])
            if not stage_id:
                continue
            seen_teams[code] = (t.get("id"), m["id"], stage_id)

    print(f"Found {len(seen_teams)} unique teams to fetch", file=sys.stderr)

    # Starter seed: handcrafted 11-man starting lineups from before squad
    # expansion. Used to mark `starter: true` on the FIFA 26-man roster so the
    # UI can pick real starters (e.g. Mbappé #10 ST) instead of the
    # lowest-shirt-number player at each position (e.g. Thuram #9 FWD).
    seed_path = DATA / "starters_seed.json"
    starter_seed = {}
    if seed_path.exists():
        seed = json.loads(seed_path.read_text(encoding="utf-8"))
        for code, payload in seed.items():
            if code == "_note" or not isinstance(payload, dict):
                continue
            starter_seed[code] = set()
            for p in payload.get("players", []):
                # store by FIFA shirt number for an unambiguous, name-agnostic mark
                if p.get("shirt") is not None:
                    starter_seed[code].add(p["shirt"])

    # Load existing rosters for nameZh preservation
    existing = json.loads((DATA / "rosters.json").read_text(encoding="utf-8"))
    nameZh_by_team = {}
    pos_by_team = {}
    formation_by_team = {}

    def _key(name):
        """Match by (first-letter-of-first-name, UPPERCASE-surname).
        Prevents NEVES collision between Joao Neves and Ruben Neves, or
        SILVA collision between Bernardo and Rui Silva."""
        parts = (name or "").strip().split()
        if not parts:
            return ("", "")
        surname = parts[-1].upper()
        first_initial = parts[0][0].upper() if parts[0] else ""
        return (first_initial, surname)

    for code, payload in existing.items():
        if code == "_note" or not isinstance(payload, dict):
            continue
        nameZh_by_team[code] = {}
        pos_by_team[code] = {}
        formation_by_team[code] = payload.get("formation")
        for p in payload.get("players", []):
            k = _key(p.get("name"))
            if k != ("", ""):
                nameZh_by_team[code][k] = p.get("nameZh", "")
                pos_by_team[code][k] = p.get("pos", "")

    # Fetch each squad
    squads = {}
    for i, (code, (id_team, id_match, id_stage)) in enumerate(seen_teams.items(), 1):
        try:
            data = fetch_live(id_stage, id_match)
        except Exception as e:
            print(f"  [{i}/{len(seen_teams)}] {code}: FETCH FAIL {e}", file=sys.stderr)
            continue
        # Find the team in HomeTeam/AwayTeam
        team_obj = None
        for side in ("HomeTeam", "AwayTeam"):
            t = data.get(side, {})
            if str(t.get("IdTeam")) == str(id_team):
                team_obj = t
                break
        if not team_obj:
            print(f"  [{i}/{len(seen_teams)}] {code}: team_obj not found", file=sys.stderr)
            continue
        players_raw = team_obj.get("Players") or []
        if not players_raw:
            print(f"  [{i}/{len(seen_teams)}] {code}: no players", file=sys.stderr)
            continue

        nz = nameZh_by_team.get(code, {})
        pz = pos_by_team.get(code, {})
        starters = starter_seed.get(code, set())
        squad_players = []
        for p in players_raw:
            name = pick_en(p.get("PlayerName"))
            short = pick_en(p.get("ShortName")) or name
            k = _key(name)
            shirt = p.get("ShirtNumber")
            entry = {
                "shirt": shirt,
                "name": name,
                "nameZh": nz.get(k, ""),
                "pos": pz.get(k, POS_LABEL.get(p.get("Position"), "")),
                "captain": bool(p.get("Captain")),
                "id": p.get("IdPlayer"),
            }
            # Mark starter if shirt number is in seed lineup or player is captain
            if shirt in starters or entry["captain"]:
                entry["starter"] = True
            pic = p.get("PlayerPicture") or {}
            if pic.get("PictureUrl"):
                entry["picture"] = pic["PictureUrl"]
            squad_players.append(entry)
        # Sort by shirt number for stability
        squad_players.sort(key=lambda x: (x["shirt"] if x["shirt"] is not None else 99))

        squads[code] = {
            "formation": formation_by_team.get(code),
            "players": squad_players,
        }
        # Drop formation key when None to keep JSON clean
        if squads[code]["formation"] is None:
            del squads[code]["formation"]
        print(
            f"  [{i}/{len(seen_teams)}] {code}: {len(squad_players)} players ✓",
            file=sys.stderr,
        )
        time.sleep(0.4)  # be polite to FIFA API

    out = {
        "_note": (
            "Official FIFA 2026 World Cup 26-man squads scraped from "
            "api.fifa.com/api/v3/live/football. ShirtNumber + Position + Captain "
            "are authoritative. nameZh / pos (e.g. CB/LW) preserved from previous "
            "handcrafted rosters when surname matches; otherwise pos falls back to "
            "GK/DEF/MID/FWD from FIFA Position field."
        ),
        **squads,
    }
    (DATA / "rosters.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nWrote {len(squads)} teams to rosters.json", file=sys.stderr)


if __name__ == "__main__":
    main()
