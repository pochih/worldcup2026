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
let SELECTED_DAY = null;        // ISO date string yyyy-mm-dd in Taipei time
let CAL_MONTH = null;           // {y, m} in Taipei
let FILTER_TW = false;
let ADV_FILTER = "all";

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
    const matches = (byDay[ds] || []).filter(mm => !FILTER_TW || mm.twBroadcast.some(b => b.includes("公視")));
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
    const tw = mm.twBroadcast.length ? `<span class="badge tw">📺 ${mm.twBroadcast.join("／")}</span>` : "";
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

function renderStandings() {
  const grid = document.getElementById("standings-grid");
  const groups = Object.keys(DATA.standings).sort();
  grid.innerHTML = groups.map(g => {
    const rows = DATA.standings[g];
    const rowsHtml = rows.map((r, i) => {
      const cls = i < 2 ? "qualified" : (i === 2 ? "third" : "");
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
  const size = 200, cx = size / 2, cy = size / 2 + 4;
  const radius = 68;
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

  // Labels with values
  const labels = RADAR_AXES.map((axis, i) => {
    const [lx, ly] = point(i, radius + 16);
    const v = stats[axis];
    const anchor = Math.abs(lx - cx) < 1 ? "middle" : (lx > cx ? "start" : "end");
    return `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="${anchor}" dy="0.35em"
      font-size="10" fill="var(--text-dim)" font-weight="600">
      ${RADAR_LABELS[axis]} <tspan fill="var(--accent)" font-weight="700">${v}</tspan>
    </text>`;
  }).join("");

  return `<svg class="radar" viewBox="0 0 ${size} ${size + 8}" xmlns="http://www.w3.org/2000/svg">
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

// ---------- tabs ----------

function setView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById(`view-${name}`).classList.add("active");
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("active", b.dataset.view === name));
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
  document.getElementById("refresh").onclick = async () => { await loadData(); renderCalendar(); renderStandings(); renderBracket(); renderTeams(); renderAnalysis(); };
}

init();
