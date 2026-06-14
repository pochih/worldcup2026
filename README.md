# 2026 世足觀賽指南

純前端 + GitHub Actions 自動更新的 2026 FIFA World Cup 賽事追蹤站。

## 功能
- 📅 **賽程日曆** — 月曆檢視 104 場比賽，台北時間，點日期看當天所有比賽
- 📊 **小組排名** — 12 組積分表，自動計算 W/D/L/GF/GA/GD/Pts
- 🏆 **淘汰賽 Bracket** — 32→16→8→4→決賽（季軍戰）
- 🌍 **48 隊一覽**
- 📺 台灣轉播資訊（愛爾達體育、公視等）
- ⚡ 每小時自動從 FIFA 官方 API 抓最新比分（GitHub Actions）

## 資料來源
- 比賽 / 比分 / 進球：[FIFA 官方 API](https://api.fifa.com/api/v3/calendar/matches?idCompetition=17&idSeason=285023)
- 場館資訊：[openfootball/world-cup](https://github.com/openfootball/world-cup)

## 本機開發
```bash
python scripts/fetch_and_build.py     # 抓取最新資料
python -m http.server 8000             # 開站
# 瀏覽 http://localhost:8000
```

## 部署到 GitHub Pages
1. 建立 GitHub repo（建議名稱 `worldcup2026`）
2. `git init && git add . && git commit -m "init" && git remote add origin <repo-url> && git push -u origin main`
3. Settings → Pages → Source 設為「GitHub Actions」
4. 完成。Actions 會每小時自動更新資料，每次 push 自動部署

## 檔案結構
```
.
├── index.html                    # 主頁
├── assets/
│   ├── style.css                 # 樣式
│   └── app.js                    # 前端邏輯
├── data/
│   ├── schedule.json             # 正規化後的比賽資料（前端讀這個）
│   ├── fifa_raw.json             # FIFA API 原始回應
│   └── stadiums.csv              # 場館參考資料
├── scripts/
│   └── fetch_and_build.py        # 抓取 + 轉換 script
└── .github/workflows/
    ├── refresh.yml               # 每小時更新資料
    └── deploy.yml                # push 時自動部署
```

## 自訂台灣轉播資訊
編輯 `scripts/fetch_and_build.py` 裡的 `DEFAULT_TW_BROADCAST` 和 `PTS_FREE_MATCHES`，重新執行即可。
