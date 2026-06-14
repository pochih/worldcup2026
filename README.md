# 2026 世足觀賽指南 ⚽

> 純前端 SPA + GitHub Actions 自動更新的 2026 FIFA World Cup 賽事追蹤站，專為台灣球迷打造。

🌐 **線上版**：https://pochih.github.io/worldcup2026/

[![Deploy](https://github.com/pochih/worldcup2026/actions/workflows/deploy.yml/badge.svg)](https://github.com/pochih/worldcup2026/actions/workflows/deploy.yml)
[![Data Refresh](https://github.com/pochih/worldcup2026/actions/workflows/refresh.yml/badge.svg)](https://github.com/pochih/worldcup2026/actions/workflows/refresh.yml)

---

## 📋 目錄

- [功能特色](#-功能特色)
- [螢幕截圖預覽](#-螢幕截圖預覽)
- [架構與技術選擇](#-架構與技術選擇)
- [資料來源](#-資料來源)
- [檔案結構](#-檔案結構)
- [本機開發](#-本機開發)
- [部署到自己的 GitHub Pages](#-部署到自己的-github-pages)
- [自訂與擴充](#-自訂與擴充)
- [資料更新機制](#-資料更新機制)
- [常見問題](#-常見問題)
- [授權與免責](#-授權與免責)

---

## ✨ 功能特色

### 📅 賽程日曆
- 月曆檢視全部 **104 場比賽**，自動換算為**台北時區**
- 點任意日期看當天詳細賽事卡片
- 顯示**比分、進球時間、進球者**（含補時 `45'+5'`、自進球 OG、12 碼 PEN）
- 觀眾數、場館、比賽階段（小組賽 / 32 強 / 16 強…）
- 「只看台灣免費轉播」篩選

### 📊 小組排名
- **12 組積分表**（A–L），自動計算 W/D/L/GF/GA/GD/Pts
- 排序規則：積分 → 淨勝球 → 進球數
- 前 2 名 ✓ 綠勾標記、第 3 名 ○ 金圈（搶最佳第 3）

### 🏆 淘汰賽樹狀圖（Bracket）
- **左右兩半在中央決賽碰頭**，16 + 16 隊清楚對稱
- 9 欄一覽到底，**不需橫向捲動**（fits 1280px page width）
- 中央決賽卡金色高亮、季軍戰並列
- 右半 row 鏡像排列，國旗朝內向決賽方向

### 🌍 48 隊一覽
- 國旗、隊名、所屬小組

### 🎯 戰力分析（含六邊形雷達圖）
- 每隊一張卡，附 **6 軸 SVG 雷達圖**（1–10 分，0.5 為單位）：
  - **進攻** · 鋒線威脅、進球能力
  - **防守** · 後防穩定、失球控制
  - **中場** · 控制力、傳球組織、創造機會
  - **體能** · 跑動、節奏、耐力
  - **經驗** · 大賽歷練、教練、心理素質
  - **球星** · 個別頂級球員影響力
- 風格分類：進攻 / 防守 / 均衡 / 反擊
- 晉級 32 強預測：🟢 幾乎確定 / 🔵 有機會 / 🟡 黑馬 / 🔴 機會低
- 優點 / 弱點 / 觀賽重點 / 預測四段文字
- 按晉級機率分類篩選

### ⚡ 自動更新
- **每小時**自動從 FIFA 官方 API 抓比分（GitHub Actions cron）
- 有變動才 commit，無變動跳過
- push 觸發 Pages 自動部署

---

## 🖼 螢幕截圖預覽

| 賽程日曆 | 小組排名 |
|---|---|
| 月曆 + 當天比賽詳情、進球時間 | 12 組積分、晉級標示 |

| 淘汰賽樹狀圖 | 戰力分析 |
|---|---|
| 左右對稱 16+16 隊在中央決賽碰頭 | 六邊形雷達 + 風格 + 預測 |

> 截圖可直接到線上版瀏覽：https://pochih.github.io/worldcup2026/

---

## 🏗 架構與技術選擇

### 設計理念
**最簡可行、零後端、零相依。** 所有邏輯跑在瀏覽器、資料是純 JSON、部署到 GitHub Pages 不花錢。

### 技術棧
| 層 | 技術 | 為何選它 |
|---|---|---|
| 前端 | **vanilla HTML/CSS/JS** | 無 build step、無框架、4 個檔案就完事 |
| 圖表 | **手刻 SVG**（雷達圖） | 不引第三方 lib，~50 行 JS 搞定 |
| 資料 | **靜態 JSON** | CDN 友善、可被任何 client 讀、易 diff |
| 抓取 | **Python 3 + urllib** | 標準函式庫即可，無需 `requirements.txt` |
| 排程 | **GitHub Actions cron** | 免費、整合 git、有 audit log |
| 部署 | **GitHub Pages** | 免費、HTTPS、CDN、與 repo 同步 |

### 資料流
```
FIFA API (live)
     │
     ▼
[GitHub Actions cron, 每小時]
     │
     ▼
scripts/fetch_and_build.py
     │ (抓賽程 + 對每場已踢完比賽抓 timeline)
     ▼
data/schedule.json  (前端讀這個)
     │
     ▼
[Actions 偵測 git diff → commit → push]
     │
     ▼
[Pages 自動部署]
     │
     ▼
https://pochih.github.io/worldcup2026/
     │
     ▼
瀏覽器 fetch schedule.json + teams_analysis.json → 渲染
```

---

## 📡 資料來源

| 來源 | 用途 | 連結 |
|---|---|---|
| FIFA 官方 API | 賽程、比分、進球事件、觀眾數 | `https://api.fifa.com/api/v3/calendar/matches?idCompetition=17&idSeason=285023` |
| FIFA Timeline API | 單場進球時間、球員 | `https://api.fifa.com/api/v3/timelines/17/285023/{stage}/{match}` |
| openfootball/world-cup | 16 場館備援資料 | [github.com/openfootball/world-cup](https://github.com/openfootball/world-cup) |
| 戰力分析 | 編者主觀評估（基於 2024-2026 國際賽表現、陣容） | `data/teams_analysis.json`（可編輯） |

### FIFA API 關鍵欄位
| 欄位 | 意義 |
|---|---|
| `IdCompetition=17` | FIFA World Cup |
| `IdSeason=285023` | **2026 賽季**（Qatar 2022 是 `255711`） |
| `MatchStatus` | `0` = 已踢完、`1` = 未開賽（反直覺！） |
| `ResultType` | `1` = 正規時間決定勝負 |
| `Date` | UTC ISO timestamp，前端轉台北時區顯示 |
| Timeline `Type` | `0` = 進球、`34` = 烏龍球、`41` = 12 碼 |

---

## 📁 檔案結構

```
worldcup2026/
├── index.html                    # 單頁 SPA 入口、5 個 tab
├── assets/
│   ├── style.css                 # 樣式（深色主題、響應式）
│   └── app.js                    # 前端邏輯（無框架）
├── data/
│   ├── schedule.json             # ★ 前端主資料源（每小時更新）
│   ├── teams_analysis.json       # 48 隊戰力 + 六邊形分數（手動維護）
│   ├── fifa_raw.json             # FIFA API 原始回應（debug 用）
│   └── stadiums.csv              # 16 場館（時區、容量、座標）
├── scripts/
│   └── fetch_and_build.py        # FIFA API → schedule.json
├── .github/workflows/
│   ├── refresh.yml               # cron: 每小時抓最新資料
│   └── deploy.yml                # push: 自動部署 Pages
├── .gitignore
└── README.md
```

### `data/schedule.json` 範例
```json
{
  "generatedAt": "2026-06-14T16:02:02+00:00",
  "totalMatches": 104,
  "matches": [
    {
      "id": "400021443", "no": 1,
      "stage": "group", "stageLabel": "First Stage", "group": "A",
      "utc": "2026-06-11T19:00:00Z",
      "status": 0, "resultType": 1,
      "venue": "Mexico City Stadium", "city": "Mexico City",
      "home": {"code": "MEX", "name": "Mexico", "score": 2, "flag": "..."},
      "away": {"code": "RSA", "name": "South Africa", "score": 0, "flag": "..."},
      "attendance": "80824",
      "twBroadcast": ["愛爾達體育台（付費）"],
      "goals": [
        {"minute": "9'",  "side": "home", "player": "Julian Quinones", "type": "G"},
        {"minute": "67'", "side": "home", "player": "Raúl", "type": "G"}
      ]
    }
  ],
  "teams": { "43911": {"id": "43911", "code": "MEX", "name": "Mexico", ...} },
  "standings": {
    "A": [
      {"name": "Mexico", "P": 1, "W": 1, "D": 0, "L": 0, "GF": 2, "GA": 0, "GD": 2, "Pts": 3},
      ...
    ]
  }
}
```

---

## 💻 本機開發

需求：**Python 3.10+**（標準函式庫即可，無需 pip install）

```bash
# 1. clone
git clone https://github.com/pochih/worldcup2026.git
cd worldcup2026

# 2. 抓最新資料（會打 FIFA API，約 10–60 秒視已踢完場數）
python scripts/fetch_and_build.py

# 3. 開本機 server（避免 fetch JSON 的 CORS 問題）
python -m http.server 8000

# 4. 瀏覽 http://localhost:8000
```

### 改前端不需重抓資料
`schedule.json` 已生成的話，直接 `python -m http.server` 即可 — 改 HTML/CSS/JS 後重新整理瀏覽器就看到變化。

---

## 🚀 部署到自己的 GitHub Pages

### 方法一：Fork
1. Fork 這個 repo
2. Settings → Pages → Source 選「**GitHub Actions**」
3. Settings → Actions → General → Workflow permissions 選「**Read and write**」
4. 等 deploy.yml 跑完即可瀏覽 `https://<你的帳號>.github.io/worldcup2026/`

### 方法二：從零建立
```bash
# 1. clone 本 repo 但移除 git history
git clone https://github.com/pochih/worldcup2026.git my-wc
cd my-wc
rm -rf .git
git init

# 2. 用 gh CLI 一鍵建 repo + push
gh repo create my-wc --public --source=. --push

# 3. 啟用 Pages（API 一行搞定）
gh api -X POST repos/<你的帳號>/my-wc/pages -f build_type=workflow
```

### 部署後驗證
```bash
gh run list --limit 3              # 看 workflow 跑得如何
gh workflow run refresh.yml        # 手動觸發一次資料更新
```

---

## 🎨 自訂與擴充

### 1. 修改台灣轉播資訊
編輯 `scripts/fetch_and_build.py` 第 18 行：
```python
DEFAULT_TW_BROADCAST = ["愛爾達體育台（付費）"]
```
要區分不同場次（例如某幾場有公視轉播）：
```python
DEFAULT_TW_BROADCAST = ["愛爾達體育台"]
PTS_FREE_MATCHES = {1, 104}  # 開幕戰、決賽
# 然後在 transform() 加：
if match_no in PTS_FREE_MATCHES:
    tw_broadcast.append("公視（無線）")
```
跑 `python scripts/fetch_and_build.py` 重新生成。

### 2. 調整戰力分析評分
編輯 `data/teams_analysis.json`，每隊都有：
```json
"MEX": {
  "style": "進攻",
  "rank": 17,
  "advance": "lock",
  "stats": {
    "attack": 7.0, "defense": 6.5, "midfield": 7.0,
    "fitness": 7.5, "experience": 7.5, "stars": 6.5
  },
  "strength": "...", "weakness": "...",
  "watch": "...", "predict": "..."
}
```
- `style`：`進攻` / `防守` / `均衡` / `反擊`
- `advance`：`lock` / `likely` / `dark` / `low`
- `stats`：6 軸，1–10 分，0.5 為單位

改完直接 push，Pages 會自動部署，無需重抓資料。

### 3. 修改顏色 / 主題
編輯 `assets/style.css` 開頭的 CSS variables：
```css
:root {
  --bg: #0a0e27;          /* 深色背景 */
  --accent: #00d4aa;      /* 強調色（綠松） */
  --gold: #ffc857;        /* 冠軍 / 決賽色 */
  --tw: #ff8c42;          /* 台灣轉播 badge 色 */
  ...
}
```

### 4. 加新的 tab
1. `index.html` 加 `<button data-view="xxx">` 和 `<section id="view-xxx" class="view">`
2. `app.js` 寫 `renderXxx()` 並在 `init()` 裡呼叫

---

## ⚙️ 資料更新機制

### Cron schedule
`.github/workflows/refresh.yml`：
```yaml
on:
  schedule:
    - cron: '17 * * * *'   # 每小時的第 17 分（避開整點 API 流量峰值）
  workflow_dispatch:        # 也可手動觸發
```

### Workflow 邏輯
1. checkout repo
2. setup Python 3.12
3. 跑 `scripts/fetch_and_build.py`
   - GET FIFA API 抓 104 場
   - 對每場已踢完比賽（`HomeTeamScore != null`）GET timeline 抓進球
   - 輸出 `data/schedule.json`
4. `git diff --cached --quiet` 檢查有無變動
5. 有變動才 commit 並 push
6. push 觸發 `deploy.yml` → Pages

### 為何選每小時而非更頻繁？
- FIFA API 沒有公開頻率限制，但避免被誤判為機器人爬取
- 比賽進行中 60 分鐘內球迷可以接受
- 想更即時的話改成 `*/15 * * * *`（每 15 分鐘）

---

## ❓ 常見問題

**Q: 為何選擇 FIFA API 而非 ESPN / BBC？**
A: FIFA 是賽事主辦方、官方資料、CORS 全開（`Access-Control-Allow-Origin: *`）、不需 API key、有 timeline endpoint。其他資源要嘛收費要嘛限制 server-side。

**Q: 為何沒有用 React / Vue / Next.js？**
A: 4 個 tab、~600 行 JS、無互動式狀態管理需求。框架的 bundler / dev server / build pipeline 對這專案是 overkill，反而拖慢部署。

**Q: 為何戰力評分主觀？可信嗎？**
A: 純編者觀點，**僅供觀賽參考、不作博弈用途**。要更客觀可串接 ELO / SPI 數據（FiveThirtyEight、Football Club Elo Ratings 等），但這超出本專案範圍。

**Q: GitHub Actions cron 偶爾延遲幾分鐘正常嗎？**
A: 正常。GitHub Actions cron 在 high-load 時段可延遲 5–15 分鐘，不保證精準。對球賽追蹤足夠。

**Q: 為何台灣轉播只列愛爾達？**
A: 截至 2026 年 6 月，愛爾達是已確認的 104 場全轉播商（付費 OTT/MOD）。其他轉播商若有確認可在 `fetch_and_build.py` 補上。

**Q: 如何貢獻？**
A: PR 歡迎，特別是：
- 戰力評分校準（提供數據佐證）
- 進球者姓名翻譯（中文名）
- 額外的篩選 / 排序選項
- 球員陣容資料整合

---

## 📜 授權與免責

### 程式碼
MIT License — 隨便用、隨便改、隨便部署自己的。

### 資料
- FIFA 賽程資料：屬 FIFA，本站僅做技術性彙整與呈現
- 場館資料：來自 openfootball（CC0-1.0）
- 戰力分析：本站原創，可自由引用

### 免責
- 本站為**球迷自製、非官方**
- 比分、進球資料來自 FIFA API，**少數 edge case 可能有延遲或誤差**，賽事認定以 FIFA 官方為準
- 轉播資訊以各轉播商官方公告為準
- 戰力評分為編者主觀判斷，**不構成任何博弈建議**

---

## 🙏 致謝

- **FIFA** — 開放官方 API
- **openfootball** — 場館與賽程備援資料
- **GitHub Actions + Pages** — 免費 cron + 免費 hosting
- **每一位現場與螢幕前的球迷** ⚽

---

<p align="center">
  <b>⚽ 享受 2026 世足！</b><br>
  <a href="https://pochih.github.io/worldcup2026/">前往線上版 →</a>
</p>
