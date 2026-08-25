# 流亡黯道2 攻略武庫 PoE 2 Build Hub

本機自用攻略聚合站。所有資料僅存放於本工作區 `data/`，每日由排程自動更新。

- 線上版：GitHub Actions 每日 UTC 00:00（台北 08:00）雲端執行 `scraper.py` → 建置靜態站 → 自動發布 GitHub Pages，並將資料 commit 回本 repo
- 本機版：cron 每天 08:00 執行 `update.sh`，Flask 服務於 `http://127.0.0.1:8766`

## 啟動網站

```bash
./start.sh          # 啟動於 http://127.0.0.1:8766
./stop.sh           # 停止
```

首次使用需先建環境：

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## 分頁功能

| 分頁 | 內容 | 資料檔 |
|------|------|--------|
| 十大 BD | 三大來源各取前 10 Build，子分頁切換：Mobalytics（站方熱門）、Maxroll（官方攻略團最新指南）、poe.ninja（現行聯盟天梯使用率前十升華） | `data/builds_{mobalytics,maxroll,poeninja}.json` |
| 熱門影片 TOP10 | YouTube 每日熱門攻略影片（依觀看數），分中文、英文、日文區 | `data/videos_hot_{zh,en,ja}.json` |
| 最新影片 | YouTube 每日最新發布攻略影片各 10 部，分中文、英文、日文區 | `data/videos_new_{zh,en,ja}.json` |
| 巴哈討論區 | 巴哈姆特流亡黯道 PoE 2 哈啦板（bsn=82273）最新 10 篇討論（已排除置頂公告） | `data/bahamut.json` |
| X 推文 | X（Twitter）上含「PoE2 / Path of Exile 2 / 流亡黯道」的相關推文與官方 @pathofexile 動態，累積式，分中文、英文、日文區 | `data/tweets_{zh,en,ja}.json` |

頂部搜尋框可跨全部內容（BD＋影片＋討論＋推文）以關鍵字搜尋。

## 每日更新

- 雲端：GitHub Actions schedule（`.github/workflows/deploy.yml`），可手動觸發：`gh workflow run deploy.yml`
- 本機：cron 已設定每天 08:00 執行 `update.sh`；手動更新：`./update.sh`

更新來源：
- Mobalytics BD：cloudscraper 解 Cloudflare 後解析 `/poe-2/builds` 列表卡
- Maxroll BD：直接 requests 解析 `/poe2/build-guides` 文章卡
- poe.ninja BD：未公開但穩定的 JSON 端點 `/poe2/api/data/build-index-state`（取第一個非 hardcore 聯盟前十升華）
- YouTube：yt-dlp（不需 API key）
- 巴哈姆特：HTML 解析
- X 推文：ddgs 站內搜尋（site:x.com）＋ syndication 官方帳號時間軸（免 API key；推文日期由 status id 直接換算）

語言分區判定：標題或摘要含假名、或網域為 .jp → 日文區；含中日韓字元 → 中文區；其餘 → 英文區。三區各自獨立累積，不會互相混雜。

## 專案結構

```
poe2/
├── app.py                     # Flask 本機伺服器（127.0.0.1:8766）
├── scraper.py                 # 每日爬蟲：三大站 BD / YouTube 熱門+最新 / 巴哈討論 / X 推文
├── build_site.py              # 彙整 data/*.json → site/ 靜態站（Pages artifact）
├── start.sh / stop.sh         # 本機網站啟停
├── update.sh                  # cron 每日更新入口（scraper + build）
├── requirements.txt
├── AGENTS.md                  # 維護規範（給 AI 助手看的工作守則，人也可參考）
├── templates/index.html       # 單頁前端
├── static/style.css, app.js   # 樣式與邏輯（搜尋在瀏覽器本地執行）
├── .github/workflows/deploy.yml  # 每日雲端爬蟲 + Pages 自動部署
└── data/
    ├── builds_mobalytics.json     # Mobalytics Top 10 BD（每日覆寫）
    ├── builds_maxroll.json        # Maxroll Top 10 BD（每日覆寫）
    ├── builds_poeninja.json       # poe.ninja 天梯前十升華（每日覆寫）
    ├── videos_hot_{zh,en,ja}.json # 熱門影片 TOP10（每日覆寫）
    ├── videos_new_{zh,en,ja}.json # 最新影片（每日覆寫）
    ├── bahamut.json               # 巴哈最新討論（每日覆寫）
    ├── tweets_{zh,en,ja}.json     # X 推文（累積式，tid 去重，每語言上限 250 筆）
    ├── meta.json                  # 各區最後更新時間
    ├── site.json                  # 前端讀取的彙整檔（build_site.py 產生）
    └── (縮圖不存放，前端直連 i.ytimg.com)
```

## 疑難排解

- **Mobalytics 抓不到**：Cloudflare 攔截升級時 cloudscraper 會失效，錯誤會記在 `logs/scraper.log`；當日該來源保留前一日資料
- **YouTube 掃不到新片**：雲端 IP 會被 YouTube 擋完整 extract，靠頻道 RSS 與本機日期快取互補，等隔天排程即可
- **push 被拒**：雲端 bot 每天會 commit 新資料，先 `git pull --rebase`；若 `data/*.json` 衝突，以本地較新資料為準（`git checkout --theirs -- data/`）再 `rebase --continue`
- **線上沒更新**：push 不會自動發布，需 `gh workflow run deploy.yml --ref main`
- **巴哈解析失敗**：scraper 會保留前一日資料並記錄於 `logs/scraper.log`，不會覆蓋成空檔

維護此專案的完整工作規範見 [AGENTS.md](AGENTS.md)。

## 日誌

- `logs/scraper.log` — scraper 完整記錄
- `logs/cron.log` — cron 執行輸出
- `logs/server.log` — 網站伺服器輸出

## 授權

本專案採用 [Apache License 2.0](LICENSE)。歡迎自由使用、修改、二次開發或商用，但需保留原始著作權聲明，並在你修改過的檔案中註明有修改；衍生專案請標明來源於此 repo。
