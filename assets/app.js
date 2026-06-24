// 2026 World Cup viewer — single-file vanilla JS
// Data shape: see scripts/fetch_and_build.py

const STAGE_LABEL_ZH = {
  group: "小組賽", r32: "32 強", r16: "16 強",
  qf: "8 強", sf: "4 強", third: "季軍戰", final: "決賽",
};

const TAIPEI_TZ = "Asia/Taipei";
const MONTH_ZH = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"];
const WEEKDAY_ZH = ["日","一","二","三","四","五","六"];

let DATA = null;
let ANALYSIS = null;
let STARS = null;
let PREVIEW = null;
let ROSTERS = null;
let LINEUP_TEMPLATES = null;
let TEAM_META = null;
let SELECTED_DAY = null;
let CAL_MONTH = null;
let FILTER_TW = false;
let ADV_FILTER = "all";
let STARS_FILTER = "all";
let SCORERS_MODE = "combined"; // 'combined' | 'goals' | 'assists'
let PREVIEW_MATCH_IDX = 0;

// ---------- utilities ----------

// FIFA Date field is UTC ISO; convert to Taipei {y,m,d} and HH:MM
function utcToTaipei(utcStr) {
  const d = new Date(utcStr);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: TAIPEI_TZ, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(d);
  const get = (t) => parts.find(p => p.type === t)?.value || "";
  return {
    date: `${get("year")}-${get("month")}-${get("day")}`,
    time: `${get("hour")}:${get("minute")}`,
    raw: d,
  };
}

function todayInTaipei() {
  const p = new Intl.DateTimeFormat("en-CA", {
    timeZone: TAIPEI_TZ, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const g = (t) => p.find(x => x.type === t).value;
  return `${g("year")}-${g("month")}-${g("day")}`;
}

function daysInMonth(y, m) { return new Date(y, m, 0).getDate(); }

function fmtRelativeUpdate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return "剛剛更新";
  if (diffMin < 60) return `${diffMin} 分鐘前更新`;
  if (diffMin < 1440) return `${Math.floor(diffMin/60)} 小時前更新`;
  return `${Math.floor(diffMin/1440)} 天前更新`;
}

function isPlayed(m) { return m.status === 0 && m.home.score !== null; }
function isLive(m) { return m.status === 3; }  // best-guess; FIFA may not flag in-play here

// ---------- data load ----------

async function loadData() {
  const res = await fetch(`data/schedule.json?t=${Date.now()}`);
  if (!res.ok) throw new Error("data load failed");
  DATA = await res.json();
  document.getElementById("updated").textContent =
    `📡 ${fmtRelativeUpdate(DATA.generatedAt)}`;
  // Load analysis JSON (optional — site still works without it)
  try {
    const ra = await fetch(`data/teams_analysis.json?t=${Date.now()}`);
    if (ra.ok) ANALYSIS = await ra.json();
  } catch (e) { /* ignore */ }
  try {
    const rs = await fetch(`data/stars.json?t=${Date.now()}`);
    if (rs.ok) STARS = await rs.json();
  } catch (e) { /* ignore */ }
  try {
    const rp = await fetch(`data/preview.json?t=${Date.now()}`);
    if (rp.ok) PREVIEW = await rp.json();
  } catch (e) { /* ignore */ }
  try {
    const rr = await fetch(`data/rosters.json?t=${Date.now()}`);
    if (rr.ok) ROSTERS = await rr.json();
  } catch (e) { /* ignore */ }
  try {
    const rl = await fetch(`data/lineup_templates.json?t=${Date.now()}`);
    if (rl.ok) LINEUP_TEMPLATES = await rl.json();
  } catch (e) { /* ignore */ }
  try {
    const rm = await fetch(`data/team_meta.json?t=${Date.now()}`);
    if (rm.ok) TEAM_META = await rm.json();
  } catch (e) { /* ignore */ }
}

// ---------- calendar ----------

function buildCalIndex() {
  // group matches by Taipei date
  const byDay = {};
  for (const m of DATA.matches) {
    const tp = utcToTaipei(m.utc);
    (byDay[tp.date] = byDay[tp.date] || []).push({ ...m, tpTime: tp.time });
  }
  return byDay;
}

function renderCalendar() {
  const grid = document.getElementById("cal-grid");
  const byDay = buildCalIndex();
  const { y, m } = CAL_MONTH;
  document.getElementById("cal-title").textContent = `${y}年 ${MONTH_ZH[m-1]}`;

  grid.innerHTML = "";
  // headers
  ["日","一","二","三","四","五","六"].forEach(d => {
    const h = document.createElement("div"); h.className = "cal-head"; h.textContent = d; grid.appendChild(h);
  });
  // padding
  const first = new Date(y, m - 1, 1);
  const firstDow = first.getDay();
  for (let i = 0; i < firstDow; i++) {
    const c = document.createElement("div"); c.className = "cal-cell empty"; grid.appendChild(c);
  }
  const today = todayInTaipei();
  const dim = daysInMonth(y, m);
  for (let d = 1; d <= dim; d++) {
    const ds = `${y}-${String(m).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
    const cell = document.createElement("div");
    cell.className = "cal-cell";
    const matches = (byDay[ds] || []).filter(mm => !FILTER_TW || mm.twBroadcast.some(b => b.includes("台視") || b.includes("無線")));
    if (matches.length) cell.classList.add("has-match");
    if (ds === today) cell.classList.add("today");
    if (ds === SELECTED_DAY) cell.classList.add("selected");

    const num = document.createElement("div"); num.className = "day-num"; num.textContent = d; cell.appendChild(num);
    if (matches.length) {
      const cnt = document.createElement("div"); cnt.className = "match-count"; cnt.textContent = `${matches.length} 場`; cell.appendChild(cnt);
      const pills = document.createElement("div"); pills.className = "match-pills";
      matches.slice(0, 2).forEach(mm => {
        const p = document.createElement("div");
        p.className = "match-pill" + (mm.stage !== "group" ? " knockout" : "");
        p.textContent = `${mm.home.code || "?"} vs ${mm.away.code || "?"}`;
        pills.appendChild(p);
      });
      if (matches.length > 2) {
        const p = document.createElement("div"); p.className = "match-pill"; p.textContent = `+${matches.length-2}…`; pills.appendChild(p);
      }
      cell.appendChild(pills);
      cell.onclick = () => { SELECTED_DAY = ds; renderCalendar(); renderDayDetail(); };
    }
    grid.appendChild(cell);
  }
  renderDayDetail();
}

function renderDayDetail() {
  const el = document.getElementById("day-detail");
  if (!SELECTED_DAY) {
    el.innerHTML = `<p style="color:var(--text-dim);text-align:center;padding:30px 0">點選日期查看當天賽事</p>`;
    return;
  }
  const byDay = buildCalIndex();
  const matches = (byDay[SELECTED_DAY] || []).sort((a, b) => a.tpTime.localeCompare(b.tpTime));
  const [y, m, d] = SELECTED_DAY.split("-").map(Number);
  let html = `<h3>${y}年${m}月${d}日（${MONTH_ZH[m-1]}）— ${matches.length} 場比賽</h3>`;
  if (!matches.length) {
    html += `<p style="color:var(--text-dim);text-align:center;padding:20px 0">這天沒有比賽 🛌</p>`;
    el.innerHTML = html;
    return;
  }
  for (const mm of matches) {
    const played = isPlayed(mm);
    const live = isLive(mm);
    const cls = live ? "live" : (played ? "played" : "");
    const home = mm.home, away = mm.away;
    const homeName = home.name || mm.placeholderHome || "TBD";
    const awayName = away.name || mm.placeholderAway || "TBD";
    const scoreHtml = played
      ? `<div class="score">${home.score} <span style="color:var(--text-dim)">–</span> ${away.score}${(home.pen !== null && home.pen !== undefined) ? `<span class="pen">PK ${home.pen}-${away.pen}</span>` : ""}</div>`
      : `<div class="score scheduled">${mm.tpTime}<br><span style="font-size:10px">台北</span></div>`;
    const stageBadge = mm.stage === "group"
      ? `<span class="badge group">小組 ${mm.group}</span>`
      : `<span class="badge knockout">${STAGE_LABEL_ZH[mm.stage] || mm.stageLabel}</span>`;
    const liveBadge = live ? `<span class="badge live">● 進行中</span>` : "";
    const doneBadge = played ? `<span class="badge done">已結束</span>` : "";
    const tw = (mm.twBroadcast || []).map(b => {
      const free = b.includes("台視") || b.includes("無線");
      const cable = b.includes("東森") || b.includes("第四台");
      const cls = free ? "tw tw-free" : (cable ? "tw tw-cable" : "tw");
      return `<span class="badge ${cls}">📺 ${b}</span>`;
    }).join(" ");
    const att = mm.attendance ? `<span class="badge">👥 ${Number(mm.attendance).toLocaleString()}</span>` : "";

    let goalsHtml = "";
    if (played && mm.goals && mm.goals.length) {
      const homeG = mm.goals.filter(g => g.side === "home")
        .map(g => goalRowHtml(g)).join("");
      const awayG = mm.goals.filter(g => g.side === "away")
        .map(g => goalRowHtml(g)).join("");
      goalsHtml = `<div class="goals-list">
        <div class="goal-home">${homeG || '<span style="color:var(--text-dim);font-size:11px">—</span>'}</div>
        <div class="ball">⚽</div>
        <div class="goal-away">${awayG || '<span style="color:var(--text-dim);font-size:11px">—</span>'}</div>
      </div>`;
    }

    html += `
      <div class="match-card ${cls}">
        <div class="home">
          ${home.flag ? `<img class="flag" src="${home.flag}" alt="${home.code}" loading="lazy">` : ""}
          <div>
            <div class="team-name">${homeName}</div>
            <div class="team-code">${home.code || ""}</div>
          </div>
        </div>
        ${scoreHtml}
        <div class="away">
          ${away.flag ? `<img class="flag" src="${away.flag}" alt="${away.code}" loading="lazy">` : ""}
          <div>
            <div class="team-name">${awayName}</div>
            <div class="team-code">${away.code || ""}</div>
          </div>
        </div>
        ${goalsHtml}
        <div class="match-meta">
          ${stageBadge} ${liveBadge} ${doneBadge}
          <span class="badge">🏟 ${mm.venue || "?"}${mm.city ? ` · ${mm.city}` : ""}</span>
          ${tw} ${att}
        </div>
      </div>`;
  }
  el.innerHTML = html;
}

function goalRowHtml(g) {
  const tag = g.type === "OG" ? `<span class="goal-tag og">OG</span>` :
              g.type === "PEN" ? `<span class="goal-tag pen">PEN</span>` : "";
  return `<div class="goal-row">
    <span class="goal-min">${g.minute}</span>
    <span class="goal-player">${g.player}</span>${tag}
  </div>`;
}

// ---------- standings ----------

// For each group, compute which team codes are mathematically eliminated
// from the top-2 (i.e. cannot finish 1st or 2nd in this group no matter how
// the remaining group matches play out). Returns { [group]: Set<code> }.
//
// Note: ignores the "8 best 3rd-place" path on purpose — a team eliminated
// from the top-2 may still sneak in via best-3rd, but the user asked us to
// mark them as eliminated once they can't reach the top 2 of their group.
function computeEliminatedByGroup() {
  const out = {};
  const remainingByGroup = {};
  for (const m of DATA.matches) {
    if (m.stage !== "group") continue;
    if (isPlayed(m)) continue;
    (remainingByGroup[m.group] = remainingByGroup[m.group] || []).push(m);
  }
  for (const g of Object.keys(DATA.standings)) {
    const baseRows = DATA.standings[g];
    const remaining = remainingByGroup[g] || [];
    const elim = new Set(baseRows.map(r => r.code));
    // Cap brute force: max 6 matches per group × 3 outcomes = 729 futures.
    // Once a team appears in top-2 of any future, drop it from `elim`.
    const totalFutures = Math.pow(3, remaining.length);
    for (let f = 0; f < totalFutures; f++) {
      // Apply this future's outcomes to a clone of the standings.
      const clone = baseRows.map(r => ({ ...r }));
      const byCode = Object.fromEntries(clone.map(r => [r.code, r]));
      let n = f;
      for (const m of remaining) {
        const outcome = n % 3; n = Math.floor(n / 3);
        const home = byCode[m.home.code];
        const away = byCode[m.away.code];
        if (!home || !away) continue;
        home.P++; away.P++;
        if (outcome === 0) {            // home win
          home.W++; away.L++;
          home.Pts += 3;
          home.GF++; away.GA++; home.GD++; away.GD--;
        } else if (outcome === 1) {     // draw
          home.D++; away.D++;
          home.Pts++; away.Pts++;
        } else {                         // away win
          away.W++; home.L++;
          away.Pts += 3;
          away.GF++; home.GA++; away.GD++; home.GD--;
        }
      }
      // Rank by Pts → GD → GF. With our scope-limited tiebreaker, any team
      // that ties with #2 on (Pts, GD, GF) could plausibly take a top-2 slot
      // under the full FIFA tiebreakers, so we treat them as "still alive".
      clone.sort((a, b) => b.Pts - a.Pts || b.GD - a.GD || b.GF - a.GF);
      const cutoff = clone[1];
      for (const r of clone) {
        const stillAlive =
          (r.Pts > cutoff.Pts) ||
          (r.Pts === cutoff.Pts && r.GD > cutoff.GD) ||
          (r.Pts === cutoff.Pts && r.GD === cutoff.GD && r.GF >= cutoff.GF);
        if (stillAlive) elim.delete(r.code);
      }
      if (elim.size === 0) break;
    }
    out[g] = elim;
  }
  return out;
}

function renderStandings() {
  const grid = document.getElementById("standings-grid");
  const groups = Object.keys(DATA.standings).sort();
  const eliminated = computeEliminatedByGroup();
  grid.innerHTML = groups.map(g => {
    const rows = DATA.standings[g];
    const elimSet = eliminated[g] || new Set();
    const rowsHtml = rows.map((r, i) => {
      const isOut = elimSet.has(r.code);
      const cls = isOut ? "eliminated"
                : i < 2 ? "qualified"
                : i === 2 ? "third" : "";
      return `<tr class="${cls}">
        <td><div class="team-cell">${r.flag ? `<img src="${r.flag}" alt="">` : ""}${r.name}</div></td>
        <td>${r.P}</td><td>${r.W}</td><td>${r.D}</td><td>${r.L}</td>
        <td>${r.GF}</td><td>${r.GA}</td><td>${r.GD > 0 ? "+" : ""}${r.GD}</td>
        <td><strong>${r.Pts}</strong></td>
      </tr>`;
    }).join("");
    return `<div class="group-card">
      <h3>Group ${g} <span class="badge">小組 ${g}</span></h3>
      <table>
        <thead><tr><th>球隊</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th></tr></thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>`;
  }).join("");
}

// ---------- bracket ----------

function renderBracket() {
  // Two-sided layout meeting at the final.
  // Each side has 16 teams: R32 (8) → R16 (4) → QF (2) → SF (1) → Final.
  // Match numbers per FIFA bracket:
  //   Left half  → SF #101 = W(QF#97) vs W(QF#98)
  //     QF #97 = W(R16 #89) vs W(R16 #90)
  //       R16 #89 = W74 vs W77 → R32 #74, #77
  //       R16 #90 = W73 vs W75 → R32 #73, #75
  //     QF #98 = W(R16 #93) vs W(R16 #94)
  //       R16 #93 = W83 vs W84 → R32 #83, #84
  //       R16 #94 = W81 vs W82 → R32 #81, #82
  //   Right half → SF #102 = W(QF#99) vs W(QF#100)
  //     QF #99 = W(R16 #91) vs W(R16 #92)
  //       R16 #91 = W76 vs W78 → R32 #76, #78
  //       R16 #92 = W79 vs W80 → R32 #79, #80
  //     QF #100 = W(R16 #95) vs W(R16 #96)
  //       R16 #95 = W86 vs W88 → R32 #86, #88
  //       R16 #96 = W85 vs W87 → R32 #85, #87
  const LAYOUT = {
    left: {
      r32: [74, 77, 73, 75, 83, 84, 81, 82],
      r16: [89, 90, 93, 94],
      qf:  [97, 98],
      sf:  [101],
    },
    right: {
      r32: [76, 78, 79, 80, 86, 88, 85, 87],
      r16: [91, 92, 95, 96],
      qf:  [99, 100],
      sf:  [102],
    },
  };
  const byNo = {};
  for (const m of DATA.matches) byNo[m.no] = m;

  const finalMatch = byNo[104];
  const thirdMatch = byNo[103];

  // Build columns left→right: L-R32 | L-R16 | L-QF | L-SF | FINAL | R-SF | R-QF | R-R16 | R-R32
  function colHtml(title, nums, side) {
    return `<div class="br-col br-${side || 'mid'}">
      <h4>${title}</h4>
      ${nums.map(n => bracketCardHtml(byNo[n], side)).join("")}
    </div>`;
  }

  const html = `
    ${colHtml("32 強", LAYOUT.left.r32, "left")}
    ${colHtml("16 強", LAYOUT.left.r16, "left")}
    ${colHtml("8 強", LAYOUT.left.qf,  "left")}
    ${colHtml("4 強", LAYOUT.left.sf,  "left")}
    <div class="br-col br-final-col">
      <h4>🏆 決賽</h4>
      ${bracketCardHtml(finalMatch, "final")}
      <h4 style="margin-top:18px;color:var(--gold)">🥉 季軍戰</h4>
      ${bracketCardHtml(thirdMatch, "third")}
    </div>
    ${colHtml("4 強", LAYOUT.right.sf,  "right")}
    ${colHtml("8 強", LAYOUT.right.qf,  "right")}
    ${colHtml("16 強", LAYOUT.right.r16, "right")}
    ${colHtml("32 強", LAYOUT.right.r32, "right")}
  `;
  document.getElementById("bracket").innerHTML = html;
}

function bracketCardHtml(m, side) {
  if (!m) return `<div class="bracket-match br-empty">—</div>`;
  const played = isPlayed(m);
  const home = m.home, away = m.away;
  const hName = home.name || `<span class="ph">${m.placeholderHome || "TBD"}</span>`;
  const aName = away.name || `<span class="ph">${m.placeholderAway || "TBD"}</span>`;
  const hWin = played && home.score > away.score;
  const aWin = played && away.score > home.score;
  const tp = utcToTaipei(m.utc);
  const sideCls = side ? `br-side-${side}` : "";
  return `<div class="bracket-match ${sideCls} ${m.stage === 'final' ? 'br-final' : ''}">
    <div class="row ${hWin ? "winner" : ""}">
      <div class="vs-name">${home.flag ? `<img src="${home.flag}" alt="">` : ""}<span>${hName}</span></div>
      <div class="vs-score">${played ? home.score : ""}</div>
    </div>
    <div class="row ${aWin ? "winner" : ""}">
      <div class="vs-name">${away.flag ? `<img src="${away.flag}" alt="">` : ""}<span>${aName}</span></div>
      <div class="vs-score">${played ? away.score : ""}</div>
    </div>
    <div class="meta">#${m.no} · ${tp.date.slice(5)} ${tp.time}</div>
  </div>`;
}

// ---------- teams ----------

function renderTeams() {
  const teams = Object.values(DATA.teams);
  // Find group letter for each team
  const teamGroup = {};
  for (const [g, rows] of Object.entries(DATA.standings)) {
    for (const r of rows) teamGroup[r.id] = g;
  }
  teams.sort((a, b) => (teamGroup[a.id] || "Z").localeCompare(teamGroup[b.id] || "Z") || a.name.localeCompare(b.name));
  const el = document.getElementById("teams-grid");
  el.innerHTML = teams.map(t => `
    <div class="team-card">
      ${t.flag ? `<img src="${t.flag}" alt="${t.code}">` : ""}
      <div class="name">${t.name}</div>
      <div class="group-badge">Group ${teamGroup[t.id] || "?"}</div>
    </div>`).join("");
}

// ---------- analysis ----------

const ADV_LABEL = {
  lock: "🟢 幾乎確定晉級",
  likely: "🔵 有機會晉級",
  dark: "🟡 黑馬",
  low: "🔴 機會低",
};

const RADAR_AXES = ["attack", "defense", "midfield", "fitness", "experience", "stars"];
const RADAR_LABELS = {
  attack: "進攻", defense: "防守", midfield: "中場",
  fitness: "體能", experience: "經驗", stars: "球星",
};

function radarSvg(stats) {
  // Hexagon (6 axes) radar chart, 1-10 scale.
  // viewBox is wider than tall so left/right labels ("中場 7.5") don't get clipped.
  const w = 260, h = 200;
  const cx = w / 2, cy = h / 2;
  const radius = 60;
  const n = RADAR_AXES.length;
  // Angles: start at top (12 o'clock), clockwise
  const angle = (i) => -Math.PI / 2 + (2 * Math.PI * i) / n;
  const point = (i, r) => [cx + r * Math.cos(angle(i)), cy + r * Math.sin(angle(i))];

  // Rings at 2,4,6,8,10
  const rings = [2, 4, 6, 8, 10].map(v => {
    const r = (v / 10) * radius;
    const pts = Array.from({ length: n }, (_, i) => point(i, r).join(",")).join(" ");
    return `<polygon points="${pts}" fill="none" stroke="rgba(151,163,207,0.18)" stroke-width="1"/>`;
  }).join("");

  // Axis lines
  const axes = Array.from({ length: n }, (_, i) => {
    const [x, y] = point(i, radius);
    return `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="rgba(151,163,207,0.22)" stroke-width="1"/>`;
  }).join("");

  // Data polygon
  const dataPts = RADAR_AXES.map((axis, i) => {
    const v = Math.max(0, Math.min(10, stats[axis] || 0));
    const r = (v / 10) * radius;
    return point(i, r).map(n => n.toFixed(1)).join(",");
  }).join(" ");

  // Vertex dots
  const dots = RADAR_AXES.map((axis, i) => {
    const v = Math.max(0, Math.min(10, stats[axis] || 0));
    const [x, y] = point(i, (v / 10) * radius);
    return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.5" fill="var(--accent)"/>`;
  }).join("");

  // Labels with values, positioned outside the hexagon vertex.
  // Use larger offset on sides (where labels are widest) and anchor accordingly.
  const labels = RADAR_AXES.map((axis, i) => {
    const a = angle(i);
    const isTopBottom = Math.abs(Math.cos(a)) < 0.01;     // 12 / 6 o'clock
    const offset = isTopBottom ? 14 : 12;
    const [lx, ly] = point(i, radius + offset);
    const v = stats[axis];
    const anchor = isTopBottom ? "middle" : (lx > cx ? "start" : "end");
    return `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="${anchor}" dy="0.35em"
      font-size="11" fill="var(--text-dim)" font-weight="600">
      ${RADAR_LABELS[axis]} <tspan fill="var(--accent)" font-weight="700">${v}</tspan>
    </text>`;
  }).join("");

  return `<svg class="radar" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
    ${rings}
    ${axes}
    <polygon points="${dataPts}" fill="rgba(0,212,170,0.22)" stroke="var(--accent)" stroke-width="1.8" stroke-linejoin="round"/>
    ${dots}
    ${labels}
  </svg>`;
}

function renderAnalysis() {
  const el = document.getElementById("analysis-grid");
  if (!ANALYSIS) {
    el.innerHTML = `<p style="color:var(--text-dim);text-align:center;padding:30px">戰力分析資料載入中…</p>`;
    return;
  }
  const teamGroup = {};
  for (const [g, rows] of Object.entries(DATA.standings)) {
    for (const r of rows) teamGroup[r.code] = g;
  }
  // Sort: by advance tier, then by group, then by FIFA rank
  const tierOrder = { lock: 0, likely: 1, dark: 2, low: 3 };
  const entries = Object.entries(ANALYSIS)
    .filter(([k]) => !k.startsWith("_"))
    .filter(([k, v]) => ADV_FILTER === "all" || v.advance === ADV_FILTER)
    .sort((a, b) => {
      const ta = tierOrder[a[1].advance] ?? 9, tb = tierOrder[b[1].advance] ?? 9;
      if (ta !== tb) return ta - tb;
      const ga = teamGroup[a[0]] || "Z", gb = teamGroup[b[0]] || "Z";
      if (ga !== gb) return ga.localeCompare(gb);
      return (a[1].rank || 99) - (b[1].rank || 99);
    });

  if (!entries.length) {
    el.innerHTML = `<p style="color:var(--text-dim);text-align:center;padding:30px">沒有符合此分類的隊伍</p>`;
    return;
  }

  el.innerHTML = entries.map(([code, a]) => {
    const team = Object.values(DATA.teams).find(t => t.code === code) || { name: code, flag: "" };
    const grp = teamGroup[code] || "?";
    return `<div class="analysis-card adv-${a.advance}">
      <div class="analysis-head">
        ${team.flag ? `<img src="${team.flag}" alt="${code}">` : ""}
        <div class="name">${team.name}</div>
        <span class="grp">Group ${grp}</span>
      </div>
      <div class="analysis-tags">
        <span class="pill style-${a.style}">${a.style}型</span>
        <span class="pill rank">FIFA #${a.rank}</span>
        <span class="pill adv-${a.advance}">${ADV_LABEL[a.advance] || a.advance}</span>
      </div>
      ${a.stats ? radarSvg(a.stats) : ""}
      <div class="analysis-section"><span class="lbl">💪 優點</span>${a.strength}</div>
      <div class="analysis-section"><span class="lbl">⚠️ 弱點</span>${a.weakness}</div>
      <div class="analysis-section"><span class="lbl">👀 觀賽重點</span>${a.watch}</div>
      <div class="analysis-section predict"><span class="lbl">🎯 預測</span>${a.predict}</div>
    </div>`;
  }).join("");
}

// ---------- stars ----------

const POS_GROUP = {
  GK: "守", CB: "守", LB: "守", RB: "守",
  DM: "中", CM: "中", AM: "攻",
  LW: "攻", RW: "攻", ST: "攻", CF: "攻",
};
const POS_COLOR = {
  GK: "#ffc857", CB: "#4fc3ff", LB: "#4fc3ff", RB: "#4fc3ff",
  DM: "#9c89ff", CM: "#9c89ff", AM: "#00d4aa",
  LW: "#ff4e6a", RW: "#ff4e6a", ST: "#ff4e6a", CF: "#ff4e6a",
};

function renderStars() {
  const grid = document.getElementById("stars-grid");
  const filterBar = document.getElementById("stars-filter");
  if (!STARS) {
    grid.innerHTML = `<p style="color:var(--text-dim);text-align:center;padding:30px">球星資料載入中…</p>`;
    return;
  }
  const teamCodes = Object.keys(STARS).filter(k => !k.startsWith("_"));

  // Filter buttons (one per team + all)
  filterBar.innerHTML = `<button class="sfilter ${STARS_FILTER === 'all' ? 'active' : ''}" data-f="all">全部</button>` +
    teamCodes.map(code => {
      const t = Object.values(DATA.teams).find(t => t.code === code);
      const name = t ? t.name : code;
      const flag = t && t.flag ? `<img src="${t.flag}" alt="">` : "";
      return `<button class="sfilter ${STARS_FILTER === code ? 'active' : ''}" data-f="${code}">${flag}${name}</button>`;
    }).join("");

  filterBar.onclick = (e) => {
    const b = e.target.closest("[data-f]");
    if (!b) return;
    STARS_FILTER = b.dataset.f;
    renderStars();
  };

  const teams = STARS_FILTER === "all" ? teamCodes : [STARS_FILTER];
  grid.innerHTML = teams.map(code => {
    const t = Object.values(DATA.teams).find(t => t.code === code) || { name: code, flag: "" };
    const players = STARS[code] || [];
    const pitchSvg = buildRosterPitch(code, t);
    return `<div class="stars-team">
      <div class="stars-team-head">
        ${t.flag ? `<img src="${t.flag}" alt="${code}">` : ""}
        <h3>${t.name}</h3>
        <span class="stars-count">${players.length} 位球星</span>
      </div>
      ${pitchSvg}
      <div class="stars-cards">
        ${players.map(p => starCardHtml(p)).join("")}
      </div>
    </div>`;
  }).join("");
}

function buildRosterPitch(code, teamFromData) {
  if (!ROSTERS || !LINEUP_TEMPLATES || !ROSTERS[code]) return "";
  const roster = ROSTERS[code];
  const formation = roster.formation;
  const slots = LINEUP_TEMPLATES[formation];
  if (!slots) return "";

  // Assign each roster player to a template slot. Match by exact position first;
  // fall back by position group (defenders/mids/attackers) so 4-3-3 with one
  // listed CM still fills a 4-2-3-1 DM slot etc.
  const POS_TO_GROUP = {
    GK: "GK", CB: "DEF", LB: "DEF", RB: "DEF",
    DM: "MID", CM: "MID", AM: "MID", RM: "MID", LM: "MID",
    LW: "ATK", RW: "ATK", ST: "ATK", CF: "ATK",
  };
  const remaining = roster.players.map(p => ({ ...p }));
  const assigned = [];
  for (const slot of slots) {
    // Exact match
    let idx = remaining.findIndex(p => p.pos === slot.pos);
    if (idx < 0) {
      // Group match
      const wantedGroup = POS_TO_GROUP[slot.pos];
      idx = remaining.findIndex(p => POS_TO_GROUP[p.pos] === wantedGroup);
    }
    if (idx < 0) {
      // Anyone left (shouldn't happen on 11+11)
      idx = 0;
    }
    const p = remaining.splice(idx, 1)[0];
    assigned.push({
      x: slot.x, y: slot.y, pos: slot.pos,
      n: p.shirt, name: p.name, nameZh: p.nameZh,
    });
  }

  const meta = (TEAM_META && TEAM_META[code]) || {};
  const team = {
    lineup: assigned,
    formation,
    manager: meta.manager || "",
    color: meta.color || "#00d4aa",
    flag: meta.flagEmoji || "",
    code,
    zones: [],
    arrows: [],
  };
  return `<div class="stars-pitch-wrap">${singleTeamPitch(team, "home")}</div>`;
}

// ---------- scorers leaderboard ----------

function computeScorerStats() {
  if (!DATA || !DATA.matches) return [];
  const stats = new Map(); // name → { name, g, a, team, flag }
  const teamByCode = {};
  for (const t of Object.values(DATA.teams || {})) {
    if (t.code) teamByCode[t.code] = t;
  }

  function bump(name, code, kind) {
    if (!name) return;
    const key = name;
    if (!stats.has(key)) {
      const t = teamByCode[code] || {};
      stats.set(key, { name, g: 0, a: 0, team: code || "?", flag: t.flag || "", teamName: t.name || code || "" });
    }
    const row = stats.get(key);
    if (kind === "g") row.g++;
    else if (kind === "a") row.a++;
    // First sighting captures team; later sightings don't overwrite
    if (!row.team || row.team === "?") {
      row.team = code;
      const t = teamByCode[code] || {};
      row.flag = t.flag || "";
      row.teamName = t.name || code;
    }
  }

  for (const m of DATA.matches) {
    if (m.status !== 0) continue;
    const homeCode = m.home && m.home.code;
    const awayCode = m.away && m.away.code;
    for (const g of (m.goals || [])) {
      if (!g.player) continue;
      const scoringCode = g.side === "home" ? homeCode : awayCode;
      // Own goals: do NOT credit the player as a scorer
      if (g.type !== "OG") bump(g.player, scoringCode, "g");
      if (g.assist) bump(g.assist, scoringCode, "a");
    }
  }

  return Array.from(stats.values());
}

function renderScorers() {
  const list = document.getElementById("scorers-list");
  if (!list) return;
  if (!DATA) {
    list.innerHTML = `<p style="color:var(--text-dim);text-align:center;padding:30px">資料載入中…</p>`;
    return;
  }

  // Wire tabs once
  const tabsRoot = document.querySelector(".scorers-tabs");
  if (tabsRoot && !tabsRoot.dataset.wired) {
    tabsRoot.dataset.wired = "1";
    tabsRoot.addEventListener("click", e => {
      const b = e.target.closest(".sc-tab");
      if (!b) return;
      SCORERS_MODE = b.dataset.sc;
      tabsRoot.querySelectorAll(".sc-tab").forEach(x =>
        x.classList.toggle("active", x.dataset.sc === SCORERS_MODE));
      renderScorers();
    });
  }

  const all = computeScorerStats();
  let sorted;
  if (SCORERS_MODE === "goals") {
    sorted = all.filter(r => r.g > 0).sort((a, b) =>
      b.g - a.g || b.a - a.a || a.name.localeCompare(b.name));
  } else if (SCORERS_MODE === "assists") {
    sorted = all.filter(r => r.a > 0).sort((a, b) =>
      b.a - a.a || b.g - a.g || a.name.localeCompare(b.name));
  } else {
    sorted = all.filter(r => r.g + r.a > 0).sort((a, b) =>
      (b.g + b.a) - (a.g + a.a) || b.g - a.g || a.name.localeCompare(b.name));
  }

  const top = sorted.slice(0, 50);
  if (!top.length) {
    list.innerHTML = `<p style="color:var(--text-dim);text-align:center;padding:30px">尚無資料</p>`;
    return;
  }

  const header = `<div class="scorer-row header">
    <div class="scorer-rank">#</div>
    <div></div>
    <div>球員</div>
    <div class="scorer-stat">進球</div>
    <div class="scorer-stat">助攻</div>
    <div class="scorer-stat">G+A</div>
  </div>`;

  const rows = top.map((r, i) => {
    const rank = i + 1;
    const topCls = rank <= 3 ? `top-${rank}` : "";
    return `<div class="scorer-row ${topCls}">
      <div class="scorer-rank">${rank}</div>
      <div class="scorer-flag">${r.flag ? `<img src="${r.flag}" alt="${r.team}">` : ""}</div>
      <div class="scorer-name">${r.name}<span class="scorer-team">${r.team}</span></div>
      <div class="scorer-stat scorer-stat-g">${r.g || "—"}</div>
      <div class="scorer-stat scorer-stat-a">${r.a || "—"}</div>
      <div class="scorer-stat scorer-stat-total">${r.g + r.a}</div>
    </div>`;
  }).join("");

  list.innerHTML = header + rows;
}

function starCardHtml(p) {
  const s = p.stats2526 || {};
  const posColor = POS_COLOR[p.pos] || "var(--text-dim)";
  const grp = POS_GROUP[p.pos] || "?";
  return `<div class="star-card">
    <div class="star-head">
      <div class="star-shirt" title="球衣號">${p.shirt || "?"}</div>
      <div class="star-id">
        <div class="star-name">${p.nameZh || p.name}</div>
        <div class="star-name-en">${p.name}</div>
      </div>
      <div class="star-pos" style="background:${posColor}" title="${p.pos} (${grp})">${p.pos}</div>
    </div>
    <div class="star-club">
      <span class="club-label">🏟</span>
      <span class="club-name">${p.club}</span>
      <span class="club-league">${p.league || ""}</span>
    </div>
    <div class="star-stats">
      <div class="stat"><div class="stat-num">${s.apps ?? "—"}</div><div class="stat-lbl">出場</div></div>
      <div class="stat"><div class="stat-num">${s.goals ?? "—"}</div><div class="stat-lbl">進球</div></div>
      <div class="stat"><div class="stat-num">${s.assists ?? "—"}</div><div class="stat-lbl">助攻</div></div>
    </div>
    <div class="star-note">${p.note || ""}</div>
  </div>`;
}

// ---------- preview (戰報) ----------

const POS_FILL = {
  GK: "#ffc857", CB: "#4fc3ff", LB: "#4fc3ff", RB: "#4fc3ff",
  DM: "#9c89ff", CM: "#9c89ff", AM: "#00d4aa",
  LW: "#ff4e6a", RW: "#ff4e6a", ST: "#ff4e6a", CF: "#ff4e6a",
};

const TIMELINE_ICON = {
  goal: "⚽", chance: "💥", control: "🎯", sub: "🔄",
  halftime: "⏸", fulltime: "🏁", card: "🟨",
};

const POS_ZH_JS = {
  GK: "門將", CB: "中後衛", LB: "左後衛", RB: "右後衛",
  DM: "後腰", CM: "中場", LM: "左中場", RM: "右中場",
  AM: "前腰", LW: "左翼", RW: "右翼", ST: "中鋒", CF: "前鋒",
};

// Pitch SVG: 100 (length) x 100 (width). Home attacks left→right, Away attacks right→left.
// Names go below the dot for home (left half) and above the dot for away (right half),
// so the two halves' name strips never collide near the centre line.
function shortPlayerName(name) {
  if (!name) return "";
  if (name.length <= 10) return name;
  const parts = name.split(/\s+/);
  if (parts.length >= 2) return `${parts[0][0]}. ${parts[parts.length - 1]}`.slice(0, 11);
  return name.slice(0, 9) + ".";
}

// If the player's `name` field is just a position code (e.g., "RB"), turn it
// into the Chinese label so unfilled lineups still read naturally.
function displayPlayerName(p) {
  const n = p.name || "";
  if (/^[A-Z]{1,3}$/.test(n)) return POS_ZH_JS[n] || n;
  return shortPlayerName(n);
}

function pitchSvg(home, away) {
  // Kept for backwards-compat with older preview.json. Prefer singleTeamPitch().
  return singleTeamPitch(home, "home") + singleTeamPitch(away, "away");
}

const ZONE_COLORS = {
  press:   { fill: "rgba(255, 78, 106, 0.15)",  stroke: "rgba(255, 78, 106, 0.7)",  label: "#ff4e6a" },
  create:  { fill: "rgba(0, 212, 170, 0.15)",   stroke: "rgba(0, 212, 170, 0.7)",   label: "#00d4aa" },
  wing:    { fill: "rgba(255, 140, 66, 0.15)",  stroke: "rgba(255, 140, 66, 0.7)",  label: "#ff8c42" },
  defense: { fill: "rgba(79, 195, 255, 0.15)",  stroke: "rgba(79, 195, 255, 0.7)",  label: "#4fc3ff" },
};

function singleTeamPitch(team, side) {
  // One team, full 100x100 pitch, no opponent → no overlap risk.
  const W = 100, H = 100;
  const isHome = side === "home";
  const pitchBg = `
    <defs>
      <pattern id="grass-${side}" x="0" y="0" width="10" height="100" patternUnits="userSpaceOnUse">
        <rect x="0" y="0" width="5"  height="100" fill="#0f5132"/>
        <rect x="5" y="0" width="5"  height="100" fill="#0d4429"/>
      </pattern>
      <filter id="playerShadow-${side}" x="-50%" y="-50%" width="200%" height="200%">
        <feDropShadow dx="0" dy="0.5" stdDeviation="0.6" flood-opacity="0.5"/>
      </filter>
    </defs>
    <rect x="0" y="0" width="${W}" height="${H}" fill="url(#grass-${side})"/>
    <rect x="1" y="1" width="${W-2}" height="${H-2}" fill="none" stroke="rgba(255,255,255,0.7)" stroke-width="0.4"/>
    <line x1="50" y1="1" x2="50" y2="99" stroke="rgba(255,255,255,0.7)" stroke-width="0.4"/>
    <circle cx="50" cy="50" r="9" fill="none" stroke="rgba(255,255,255,0.7)" stroke-width="0.4"/>
    <circle cx="50" cy="50" r="0.6" fill="rgba(255,255,255,0.7)"/>
    <rect x="1"    y="28" width="14" height="44" fill="none" stroke="rgba(255,255,255,0.7)" stroke-width="0.4"/>
    <rect x="1"    y="38" width="6"  height="24" fill="none" stroke="rgba(255,255,255,0.7)" stroke-width="0.4"/>
    <rect x="${W-15}" y="28" width="14" height="44" fill="none" stroke="rgba(255,255,255,0.7)" stroke-width="0.4"/>
    <rect x="${W-7}"  y="38" width="6"  height="24" fill="none" stroke="rgba(255,255,255,0.7)" stroke-width="0.4"/>
    <circle cx="11"    cy="50" r="0.6" fill="rgba(255,255,255,0.7)"/>
    <circle cx="${W-11}" cy="50" r="0.6" fill="rgba(255,255,255,0.7)"/>
  `;

  // Zones: drawn first (behind everything else)
  const zones = (team.zones || []).map((z, i) => {
    const c = ZONE_COLORS[z.kind] || ZONE_COLORS.create;
    const labelX = z.x + 1.5;
    const labelY = z.y + 4;
    return `
      <rect x="${z.x}" y="${z.y}" width="${z.w}" height="${z.h}"
            fill="${c.fill}" stroke="${c.stroke}" stroke-width="0.5"
            stroke-dasharray="1.5,1" rx="1"/>
      <text x="${labelX}" y="${labelY}" font-size="2.6" font-weight="800"
            fill="${c.label}" stroke="#0a0e27" stroke-width="0.4"
            paint-order="stroke">${z.label}</text>
    `;
  }).join("");

  // Ball routes: solid thin lines, no arrowhead — passing lanes
  const ballRoutes = (team.ballRoutes || []).map((r, i) => {
    const [x1, y1] = r.from, [x2, y2] = r.to;
    return `
      <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"
            stroke="rgba(255,255,255,0.85)" stroke-width="0.5"
            stroke-linecap="round" opacity="0.7"/>
      <circle cx="${x2}" cy="${y2}" r="0.9" fill="rgba(255,255,255,0.85)"/>
    `;
  }).join("");

  // Attack arrows: dashed team-color, with arrowhead — runs
  const arrows = (team.arrows || []).map((a, i) => {
    const id = `arrow-${side}-${i}`;
    const [x1, y1] = a.from, [x2, y2] = a.to;
    return `
      <defs>
        <marker id="${id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="4" markerHeight="4" orient="auto">
          <path d="M0,0 L10,5 L0,10 Z" fill="${team.color}"/>
        </marker>
      </defs>
      <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"
            stroke="${team.color}" stroke-width="0.8" stroke-dasharray="1.5,0.8"
            marker-end="url(#${id})" opacity="0.95"/>
    `;
  }).join("");

  // Players
  const playerCircles = team.lineup.map(p => {
    const fill = POS_FILL[p.pos] || "#97a3cf";
    const ring = team.color;
    // No opponent on the pitch → simple, consistent label placement.
    const labelY = isHome ? p.y + 6.8 : p.y - 4.6;
    return `<g filter="url(#playerShadow-${side})">
      <circle cx="${p.x}" cy="${p.y}" r="3.6" fill="${fill}" stroke="${ring}" stroke-width="0.9"/>
      <text x="${p.x}" y="${p.y}" text-anchor="middle" dy="0.35em"
            font-size="3" font-weight="800" fill="#0a0e27">${p.n}</text>
      <text x="${p.x}" y="${labelY}" text-anchor="middle"
            font-size="2.2" font-weight="700" fill="#fff" stroke="#000" stroke-width="0.45"
            paint-order="stroke" stroke-linejoin="round"
            text-rendering="geometricPrecision">${displayPlayerName(p)}</text>
    </g>`;
  }).join("");

  // Title strip + small attack-direction caption
  const dirCaption = isHome ? "進攻方向 →" : "← 進攻方向";
  const titleX = isHome ? 2 : 98;
  const titleAnchor = isHome ? "start" : "end";

  return `<svg class="pitch pitch-${side}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
    ${pitchBg}
    ${zones}
    ${ballRoutes}
    ${arrows}
    ${playerCircles}
    <text x="${titleX}" y="6" text-anchor="${titleAnchor}" font-size="4" font-weight="800"
          fill="#fff" stroke="#000" stroke-width="0.5" paint-order="stroke">
      ${team.flag} ${team.code}
    </text>
    <text x="${titleX}" y="11" text-anchor="${titleAnchor}" font-size="2.8" font-weight="700"
          fill="#fff" stroke="#000" stroke-width="0.3" paint-order="stroke">
      ${team.formation} · ${team.manager}
    </text>
    <text x="50" y="6" text-anchor="middle" font-size="2.4" font-weight="700"
          fill="rgba(255,255,255,0.7)" stroke="#000" stroke-width="0.3" paint-order="stroke">
      ${dirCaption}
    </text>
  </svg>`;
}

function arrowLegendHtml(home, away) {
  const items = [];
  (home.arrows || []).forEach(a => items.push({ side: "home", color: home.color, label: a.label }));
  (away.arrows || []).forEach(a => items.push({ side: "away", color: away.color, label: a.label }));
  if (!items.length) return "";
  return `<div class="arrow-legend">
    ${items.map(it => `<span class="arrow-chip">
      <span class="arrow-line" style="background:${it.color}"></span>
      <span class="arrow-side">${it.side === "home" ? home.code : away.code}</span>
      <span class="arrow-label">${it.label || ""}</span>
    </span>`).join("")}
  </div>`;
}

// Dual-team radar: overlay home (accent) and away (red) on the same hexagon.
function radarCompareSvg(home, away) {
  const w = 320, h = 240;
  const cx = w / 2, cy = h / 2;
  const radius = 78;
  const n = RADAR_AXES.length;
  const angle = (i) => -Math.PI / 2 + (2 * Math.PI * i) / n;
  const point = (i, r) => [cx + r * Math.cos(angle(i)), cy + r * Math.sin(angle(i))];

  const rings = [2, 4, 6, 8, 10].map(v => {
    const r = (v / 10) * radius;
    const pts = Array.from({ length: n }, (_, i) => point(i, r).join(",")).join(" ");
    return `<polygon points="${pts}" fill="none" stroke="rgba(151,163,207,0.18)" stroke-width="1"/>`;
  }).join("");

  const axes = Array.from({ length: n }, (_, i) => {
    const [x, y] = point(i, radius);
    return `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="rgba(151,163,207,0.22)" stroke-width="1"/>`;
  }).join("");

  const buildPoly = (stats, color, fillColor) => {
    const pts = RADAR_AXES.map((axis, i) => {
      const v = Math.max(0, Math.min(10, stats[axis] || 0));
      const r = (v / 10) * radius;
      return point(i, r).map(n => n.toFixed(1)).join(",");
    }).join(" ");
    const dots = RADAR_AXES.map((axis, i) => {
      const v = Math.max(0, Math.min(10, stats[axis] || 0));
      const [x, y] = point(i, (v / 10) * radius);
      return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="${color}" stroke="#0a0e27" stroke-width="1"/>`;
    }).join("");
    return `<polygon points="${pts}" fill="${fillColor}" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>${dots}`;
  };

  // Axis labels with both team values
  const labels = RADAR_AXES.map((axis, i) => {
    const a = angle(i);
    const isTopBottom = Math.abs(Math.cos(a)) < 0.01;
    const offset = isTopBottom ? 16 : 14;
    const [lx, ly] = point(i, radius + offset);
    const anchor = isTopBottom ? "middle" : (lx > cx ? "start" : "end");
    const hv = home.stats[axis], av = away.stats[axis];
    return `<g>
      <text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="${anchor}" dy="-0.4em"
        font-size="11" fill="var(--text-dim)" font-weight="600">${RADAR_LABELS[axis]}</text>
      <text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="${anchor}" dy="0.9em"
        font-size="10" font-weight="800">
        <tspan fill="var(--accent)">${hv}</tspan>
        <tspan fill="var(--text-dim)" dx="3">vs</tspan>
        <tspan fill="var(--accent-2)" dx="3">${av}</tspan>
      </text>
    </g>`;
  }).join("");

  return `<svg class="radar-compare" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
    ${rings}
    ${axes}
    ${buildPoly(away.stats, "var(--accent-2)", "rgba(255,78,106,0.18)")}
    ${buildPoly(home.stats, "var(--accent)",   "rgba(0,212,170,0.22)")}
    ${labels}
  </svg>`;
}

function timelineHtml(timeline, home, away) {
  return `<div class="timeline">
    <div class="timeline-track"></div>
    ${timeline.map(ev => {
      const sideCls = ev.side === "home" ? "tl-home" : (ev.side === "away" ? "tl-away" : "tl-neutral");
      const typeCls = `tl-${ev.type}`;
      const teamCode = ev.side === "home" ? home.code : (ev.side === "away" ? away.code : "");
      const teamFlag = ev.side === "home" ? home.flag : (ev.side === "away" ? away.flag : "");
      const scoreLabel = ev.score ? `<span class="tl-score">${ev.score}</span>` : "";
      const minPct = (ev.min / 95) * 100;
      return `<div class="tl-event ${sideCls} ${typeCls}" style="left:${minPct}%">
        <div class="tl-min">${ev.min}'</div>
        <div class="tl-marker">${TIMELINE_ICON[ev.type] || "•"}</div>
        <div class="tl-content">
          ${teamFlag ? `<span class="tl-flag">${teamFlag} ${teamCode}</span>` : ""}
          ${scoreLabel}
          <div class="tl-text">${ev.text}</div>
        </div>
      </div>`;
    }).join("")}
  </div>`;
}

function predictBarsHtml(scenarios) {
  const max = Math.max(...scenarios.map(s => s.prob));
  return `<div class="predict-bars">
    ${scenarios.map(s => `
      <div class="predict-row">
        <div class="predict-score">${s.score}</div>
        <div class="predict-bar-wrap">
          <div class="predict-bar" style="width:${(s.prob/max)*100}%"></div>
          <div class="predict-prob">${s.prob}%</div>
        </div>
        <div class="predict-desc">${s.desc}</div>
      </div>
    `).join("")}
  </div>`;
}

function renderPreview() {
  const tabsEl = document.getElementById("preview-tabs");
  const contentEl = document.getElementById("preview-content");
  if (!PREVIEW || !PREVIEW.matches) {
    contentEl.innerHTML = `<p style="color:var(--text-dim);text-align:center;padding:30px">戰報資料載入中…</p>`;
    return;
  }
  tabsEl.innerHTML = PREVIEW.matches.map((m, i) =>
    `<button class="ptab ${i === PREVIEW_MATCH_IDX ? 'active' : ''}" data-idx="${i}">
      ${m._auto ? '🤖 ' : ''}${m.shortTitle}
    </button>`
  ).join("");
  tabsEl.onclick = (e) => {
    const b = e.target.closest("[data-idx]");
    if (!b) return;
    PREVIEW_MATCH_IDX = parseInt(b.dataset.idx, 10);
    renderPreview();
  };

  const m = PREVIEW.matches[PREVIEW_MATCH_IDX];
  const winnerCode = m.predict.winner === "home" ? m.home.code : m.away.code;
  const autoBadge = m._auto
    ? `<span class="auto-badge" title="自動生成自 FIFA 排名與球星數據">🤖 自動生成戰報</span>`
    : "";
  const hypoBadge = m._hypothetical
    ? `<span class="auto-badge hypothetical" title="此對戰未在賽程中出現，為假想戰報">💭 假想對戰</span>`
    : "";
  const historyHtml = (m.history && m.history.length) ? `
      <div class="preview-section">
        <h4>📜 歷史交手</h4>
        <div class="history-list">
          ${m.history.map(h => `
            <div class="history-row">
              <span class="history-year">${h.year}</span>
              <span class="history-score">${h.score}</span>
              <span class="history-note">${h.note}</span>
            </div>
          `).join("")}
        </div>
      </div>` : "";

  contentEl.innerHTML = `
    <div class="preview-card">
      <div class="preview-header">
        <h3>${m.title}</h3>
        <p class="preview-subtitle">${m.subtitle}</p>
        <div class="preview-meta">
          <span class="badge">📍 ${m.venue}</span>
          <span class="badge">🏆 ${m.stage}</span>
          ${autoBadge}
          ${hypoBadge}
        </div>
      </div>

      <!-- Versus banner -->
      <div class="vs-banner">
        <div class="vs-team home">
          <div class="vs-flag">${m.home.flag}</div>
          <div class="vs-name">${m.home.name}</div>
          <div class="vs-formation">${m.home.formation}</div>
          <div class="vs-manager">主帥：${m.home.manager}</div>
        </div>
        <div class="vs-center">
          <div class="vs-label">VS</div>
          <div class="vs-predict">
            <div class="vs-predict-label">預測比分</div>
            <div class="vs-predict-score">${m.predict.score}</div>
            <div class="vs-predict-conf">信心 ${m.predict.confidence}%</div>
          </div>
        </div>
        <div class="vs-team away">
          <div class="vs-flag">${m.away.flag}</div>
          <div class="vs-name">${m.away.name}</div>
          <div class="vs-formation">${m.away.formation}</div>
          <div class="vs-manager">主帥：${m.away.manager}</div>
        </div>
      </div>

      <!-- Pitch tactical boards: two stacked single-team pitches -->
      <div class="preview-section">
        <h4>⚽ 戰術板 · 預測首發陣型</h4>
        <div class="pitch-wrap pitch-wrap-home">
          ${singleTeamPitch(m.home, "home")}
        </div>
        <div class="pitch-divider">
          <span class="pitch-divider-flag">${m.home.flag}</span>
          <span class="pitch-divider-vs">VS</span>
          <span class="pitch-divider-flag">${m.away.flag}</span>
        </div>
        <div class="pitch-wrap pitch-wrap-away">
          ${singleTeamPitch(m.away, "away")}
        </div>
        ${arrowLegendHtml(m.home, m.away)}
        ${m.tactics ? `
        <div class="tactics-block">
          <div class="tactics-team tactics-home">
            <h5><span class="tactics-flag">${m.home.flag}</span> ${m.home.code} 戰術重點</h5>
            <ul>${(m.tactics.home || []).map(t => `<li>${t}</li>`).join("")}</ul>
          </div>
          <div class="tactics-team tactics-away">
            <h5><span class="tactics-flag">${m.away.flag}</span> ${m.away.code} 戰術重點</h5>
            <ul>${(m.tactics.away || []).map(t => `<li>${t}</li>`).join("")}</ul>
          </div>
        </div>` : ""}
        <div class="pitch-legend">
          <span class="legend-dot" style="background:#ffc857"></span> GK 守門
          <span class="legend-dot" style="background:#4fc3ff"></span> 後衛
          <span class="legend-dot" style="background:#9c89ff"></span> 後腰
          <span class="legend-dot" style="background:#00d4aa"></span> 前腰
          <span class="legend-dot" style="background:#ff4e6a"></span> 鋒線
          &nbsp;&nbsp;
          <span class="legend-line solid"></span> 出球路線
          <span class="legend-line dashed"></span> 進攻路徑
          <span class="legend-zone"></span> 戰術重點區
        </div>
      </div>

      ${historyHtml}

      <!-- Radar comparison -->
      <div class="preview-section">
        <h4>📐 雙方戰力雷達比較</h4>
        <div class="radar-compare-wrap">
          ${radarCompareSvg(m.home, m.away)}
          <div class="radar-legend">
            <div class="radar-legend-item">
              <span class="radar-dot" style="background:var(--accent)"></span>
              <span>${m.home.flag} ${m.home.code}</span>
            </div>
            <div class="radar-legend-item">
              <span class="radar-dot" style="background:var(--accent-2)"></span>
              <span>${m.away.flag} ${m.away.code}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Timeline -->
      <div class="preview-section">
        <h4>📊 比賽走勢預測 (0-90 分鐘)</h4>
        ${timelineHtml(m.timeline, m.home, m.away)}
      </div>

      <!-- Key duels -->
      <div class="preview-section">
        <h4>⚔️ 關鍵對位</h4>
        <div class="duels-list">
          ${m.keyDuels.map(d => `
            <div class="duel-row">
              <div class="duel-home">${m.home.flag} ${d.home}</div>
              <div class="duel-vs">VS</div>
              <div class="duel-away">${d.away} ${m.away.flag}</div>
              <div class="duel-note">${d.note}</div>
            </div>
          `).join("")}
        </div>
      </div>

      <!-- Referee -->
      <div class="preview-section">
        <h4>🧑‍⚖️ 裁判風格推測</h4>
        <div class="referee-card">
          <div class="referee-row"><span class="ref-label">風格</span><span>${m.referee.style}</span></div>
          <div class="referee-row"><span class="ref-label">傾向</span><span>${m.referee.tendency}</span></div>
          <div class="referee-row"><span class="ref-label">影響</span><span>${m.referee.impact}</span></div>
        </div>
      </div>

      <!-- Final prediction -->
      <div class="preview-section predict-section">
        <h4>🎯 最終預測</h4>
        <div class="predict-headline">
          <div class="predict-winner-flag">${m.predict.winner === "home" ? m.home.flag : m.away.flag}</div>
          <div class="predict-headline-text">
            <div class="predict-final-score">${m.predict.score}</div>
            <div class="predict-conf-bar-wrap">
              <div class="predict-conf-bar" style="width:${m.predict.confidence}%"></div>
              <span class="predict-conf-text">信心度 ${m.predict.confidence}%</span>
            </div>
          </div>
        </div>
        <p class="predict-reasoning">${m.predict.reasoning}</p>
        <h5>各情境機率分布</h5>
        ${predictBarsHtml(m.predict.scenarios)}
      </div>
    </div>
  `;
}

// ---------- tabs ----------

function setView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById(`view-${name}`).classList.add("active");
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("active", b.dataset.view === name));
  const activeBtn = document.querySelector(`#tabs button[data-view="${name}"]`);
  activeBtn?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
}

// ---------- init ----------

async function init() {
  try { await loadData(); }
  catch (e) {
    document.getElementById("app").innerHTML = `<p style="text-align:center;padding:60px;color:var(--text-dim)">資料載入失敗：${e.message}<br>請檢查 data/schedule.json 是否存在。</p>`;
    return;
  }
  // Default month: first match's month, or today
  const first = DATA.matches[0];
  const tpFirst = utcToTaipei(first.utc);
  const today = todayInTaipei();
  const useToday = today >= tpFirst.date && today <= utcToTaipei(DATA.matches[DATA.matches.length-1].utc).date;
  const startDate = useToday ? today : tpFirst.date;
  const [yy, mm, dd] = startDate.split("-").map(Number);
  CAL_MONTH = { y: yy, m: mm };
  SELECTED_DAY = startDate;

  renderCalendar();
  renderStandings();
  renderBracket();
  renderTeams();
  renderAnalysis();
  renderStars();
  renderScorers();
  renderPreview();

  // Tab nav
  document.getElementById("tabs").addEventListener("click", e => {
    if (e.target.tagName === "BUTTON") setView(e.target.dataset.view);
  });
  // Cal nav
  document.getElementById("cal-prev").onclick = () => {
    CAL_MONTH.m--; if (CAL_MONTH.m < 1) { CAL_MONTH.m = 12; CAL_MONTH.y--; }
    renderCalendar();
  };
  document.getElementById("cal-next").onclick = () => {
    CAL_MONTH.m++; if (CAL_MONTH.m > 12) { CAL_MONTH.m = 1; CAL_MONTH.y++; }
    renderCalendar();
  };
  document.getElementById("cal-today").onclick = () => {
    const t = todayInTaipei();
    const [y, m] = t.split("-").map(Number);
    CAL_MONTH = { y, m }; SELECTED_DAY = t; renderCalendar();
  };
  document.getElementById("filter-tw").onchange = (e) => { FILTER_TW = e.target.checked; renderCalendar(); };
  document.querySelectorAll('input[name="adv-filter"]').forEach(r => {
    r.onchange = (e) => { ADV_FILTER = e.target.value; renderAnalysis(); };
  });
  document.getElementById("refresh").onclick = async () => {
    await loadData();
    renderCalendar(); renderStandings(); renderBracket();
    renderTeams(); renderAnalysis(); renderStars(); renderScorers(); renderPreview();
  };
}

init();
