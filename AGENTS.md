# poe2 專案規範

流亡黯道2（Path of Exile 2）攻略聚合站。Flask 本機版 + GitHub Pages 線上版共用同一套前端與資料。
架構複製自同類專案 `../nioh3`（仁王3 版），全域規範見 `~/.codex/AGENTS.md`，本檔只列專案特有規則。

## 語言

一律使用繁體中文回覆。程式碼、指令、變數名稱維持英文。

## 架構與資料流

```
scraper.py ──> data/*.json ──> build_site.py ──> site/（靜態站，Pages artifact）
                     │
                     └──> app.py（Flask 本機版，直接讀 data/）
```

- `data/*.json` 是唯一資料來源，所有內容只能存放在本工作區
- `site/` 是建置產物，已列入 `.gitignore`，**絕不 commit**；Pages 用 `actions/upload-pages-artifact` 上傳
- 三大站 BD 區（`builds_*.json`）是每日覆寫快照；影片區同為每日覆寫；巴哈區每日覆寫；X 推文區（`tweets_*.json`）累積式、每語言上限 250 筆（超出裁最舊）
- `meta.json` 記錄各區最後更新時間，`_last_run` 是完整掃描時間
- 本機埠 **8766**（nioh3 佔 8765，兩站可並存）

## 語言分區規則（不可破壞）

三區 zh / en / ja 由 `detect_lang()` 判定：

1. 標題或摘要含**平/片假名** → ja
2. 網域以 `.jp` 結尾 → ja
3. 含 CJK 字元 → zh
4. 其餘 → en

影片區的 `keep()` 過濾同邏輯：ja 要有假名；zh 必須「含 CJK 且**無**假名」。

## 各來源已知陷阱

### Mobalytics BD
- 全站在 Cloudflare 後面：requests / Googlebot UA 一律 403，**必須用 cloudscraper**（requirements 已含）。若 Cloudflare 升級導致 cloudscraper 失效，當日保留舊資料即可，不要硬繞
- **不要解析 HTML**（2026-09-05 改）：`/poe-2/builds` 的列表是 client-rendered，SSR 只嵌 5 筆主列表 + 4 筆 Featured，去重後湊不滿 10 筆
- 正解是前端自己用的 GraphQL 端點 `POST https://mobalytics.gg/api/poe-2/v1/graphql/query`（見頁面 `POE_2_GQL_HTTP_URL`）。**introspection 已關，但接受自訂 query**，不必用 persisted query。要先 GET 一次 `/poe-2/builds` 拿 Cloudflare clearance cookie 再 POST
- 查詢用 `userGeneratedDocuments(input, page)`；篩選條件寫在 `MOBA_FILTER_TAGS`，跟站上預設一致（見頁面 SSR 的 `discovery.initialState`）：`build-type=end-game-type`、`vefified=expert-verification`（注意官方就是拼成 `vefified`）、`patch=defaultValue`、`sortBy=TRENDING`、`publishedTimeframe=ALL`
- **patch 一定要用 `defaultValue` 不要寫死版本 slug**（現行是 `0-5-rota`），這樣新賽季開了不必改程式
- **BD 連結要用 `featured.slug`，不是 `slugifiedName`**：實測 `/poe-2/builds/{slugifiedName}` 會 404

### Maxroll BD
- 直接 requests 可抓，伺服器端渲染完整 HTML；文章卡用 `article` + `a[href^="/poe2/build-guides/"]` 定位
- 不帶任何 query string 就是站上預設檢視（職業 All、Endgame/Leveling/Twink Leveling 皆 All、Ascendancy All），列表已依 Last Updated 新到舊排，前 10 篇即最新 10 篇——不需要另外帶篩選參數
- class 名帶 hash 後綴（`_post_odfl4_1`），網站重 build 會變，選擇器一律用部分匹配或結構定位
- 「By 作者 | Last Updated: 日期」在 h2 文字裡，用 regex 抽
- 版本 tag 現行格式是「The Forbidden Rites 0.5.5」（賽季名 + 版號），判斷條件用「tag 內含 `\d+\.\d+`」，不要只比對舊式賽季名

### poe.ninja BD
- builds 頁面本身是 client-rendered Astro，HTML 內沒有表格資料，不要嘗試解析 HTML
- 正解是未公開但穩定的 JSON 端點 `GET https://poe.ninja/poe2/api/data/build-index-state`（免 auth、datacenter IP 可打），`statistics` 即前十升華占比（percentage = share of ladder）
- **選聯盟不能只挑「第一個 `hardcore=false`」**（2026-09-05 修）：那樣會撿到 SSF 或私人聯盟，賽季交替時也可能停在上一季。條件要寫明（見 `pick_ninja_league()`）：`category==0`（官方挑戰聯盟，排除 Standard 與私人聯盟）、`status==0`（進行中）、非 hardcore、`leagueUrl` 不以 `ssf` 結尾、且 `statistics` 非空。清單本身是新到舊排，第一個符合的就是現行賽季
- **各升華專屬連結**：依官方前端 routing（`a2.AsVFAiaS.mjs`），格式為 `https://poe.ninja/poe2/builds/{leagueUrl}?class={Name}`（空格以 `+` 連接），點擊可直達該升華篩選頁
- 不要再花時間逆推 builds 表格的列表端點（2026-08-26 已掃過全部 astro chunks，只有這一個公開端點）

### yt-dlp（v2026.08+）
- **沒有 `ytsearchdate` 前綴**了；`sp=CAI%3D`（上傳時間排序）已被 YouTube 靜默忽略，回傳順序是相關性排序
- 找「最新影片」的正解：flat 搜尋結果自帶 `channel_id`，改抓候選頻道的上傳 RSS——免費附發佈日期與觀看數（見 `yt_rss_latest()`）
- flat playlist 搜尋結果會混入播放清單項目（id 是 PL… 34 碼），組 pool 時只收 id 長度 11 的影片
- 影片縮圖不下載、不入 repo：前端直接引用 `https://i.ytimg.com/vi/{video_id}/mqdefault.jpg`

### 熱門影片挑選規則（不可退回舊做法）
- **時間優先於觀看數**：先取近 `HOT_CUTOFF_DAYS`（30 天）內上傳的候選、再依觀看數排序；窗內湊不滿 10 部才用較舊的遞補。
  舊版是「先依觀看數排序、邊掃邊查日期」並帶 `max_check` 上限，遇到 2024 上市期那批高觀看老片會把預算燒光，導致熱門區停在 2024
- **候選池要同時吃相關度與上傳時間兩種搜尋**：只用相關度排序時 YouTube 幾乎只回老片，新片根本進不了候選
- **日期先吃免費來源**（頻道 RSS → `data/video_dates.json` 快取），只有兩者都沒有才呼叫 `yt_full_info()`，且有 `HOT_LOOKUP_BUDGET` 次數上限。
  雲端 IP 被 YouTube 擋時 `yt_full_info()` 會大量失敗、日期變 `None`，快取就是那時的救命稻草——**不要把快取只用在挑選之後**
- 同頻道重複上傳／分段直播常出現完全同名的多支影片，熱門與最新都要過 `dedupe_video_items()`（以「頻道 + 標題」去重）

### DuckDuckGo（ddgs）
- 同一批 query 短時間內重跑會回 "No results found" 或引擎 429/403——速率限制，不是程式壞掉。除錯時不要連續重跑
- 中文用 `region="tw-zh"`、英文 `us-en`、日文 `jp-jp`

### 巴哈姆特（bsn=82273 流亡黯道 PoE 2 哈啦板）
- `RSS.php` 已失效，只能解析 `B.php?bsn=82273` HTML
- 帶 `.b-list__summary__mark` 的列是置頂/公告/精華，**跳過**
- 解析失敗時保留舊資料並記 log，不要覆蓋成空檔

### X（Twitter）
- 免費讀取只有兩條活路：syndication 端點與 ddgs 站內搜尋（`site:x.com`）
- syndication 極敏感於連續請求：每天只打官方帳號一次（目前僅 `@pathofexile`），失敗就保留舊資料
- 推文發文日期由 status id（snowflake）右移 22 bits 加 1288834974657 換算
- `tweets_*.json` 以 tid 去重累積，每語言上限 250 筆；ddgs 撿到的標題格式是「顯示名稱 on X: 推文內容」，解析後要過 `game_in_title()` 關鍵字過濾

## Git 與部署流程

> 🔴 **本 repo 是 PUBLIC，builder 一律不得執行 `git push`。**
> 實作完成後 commit 到本地就停，回報「哪幾個 commit 可推」，由 Frank 逐次授權後人工推送。
> **下方步驟 2–3 是在描述整條流程（含 Frank 負責的部分），其中出現的 `git push` 不是給你執行的。**
> 細則見全域規範 `~/.codex/AGENTS.md` 的「Git：本機操作自由，push 是閘門」，此處不另立一套說法。

1. push 前依全域規範做機密掃描
2. **push 之後線上不會自動更新**，必須手動觸發：`gh workflow run deploy.yml --ref main`（workflow 也負責當天的雲端爬蟲）
3. 雲端 bot 每天 UTC 00:00 會產生 "daily data update" commit。本機 push 若被拒或 rebase 撞到 `data/*.json` 衝突（⚠️ 以下含推送指令，**僅限已獲授權者執行**）：

```bash
git pull --rebase
git checkout --theirs -- data/   # 衝突時以本地較新資料為準
git add data/ && git -c core.editor=true rebase --continue && git push
```

4. repo 必須保持 public（免費 Pages 限制），資料皆為公開網頁內容無敏感性問題

## 前端呈現規則

- **BD 卡採純文字顯示**：三來源（Mobalytics / Maxroll / poe.ninja）卡片皆無縮圖與外部連結 icon，僅顯示排名、標題、作者/更新日、標籤（或使用率條），避免缺圖導致版面崩壞
- Tweet 區外部連結 icon（`.ext-icon`）保留 13px 尺寸

改動後必須實際執行驗證，順序：

1. `./venv/bin/python -c "import ast; ast.parse(open('scraper.py').read())"` — Python 語法
2. `node --check static/app.js` — JS 語法
3. **`node tests/hero_contract.mjs` — 站台契約，必須全綠**（含 hero 三層結構、
   5 張 CTA 卡對應、以及「初次載入內容區就可見」的回歸保護）。不需額外套件，
   它會自己建站、起 server、驅動本機 Chrome headless
4. 跑 scraper 後檢查各區筆數與語言誤配 = 0
5. `./start.sh` 後 curl 兩項：`/` 200、`/data/site.json` 可解析（本機埠 8766）
6. push 後觸發 workflow，確認 run success 再 curl 線上 site.json

## 其他約定

- 本機 cron 與雲端 Actions 雙排程並存是刻意設計（互為備援），不要移除其中一個
- `venv/`、`logs/`、`site/` 都不入 git；臨時探測腳本用完即刪，不留根目錄
- 使用者環境是 2012 年老 iMac：scraper 全程約 3–5 分鐘屬正常（YouTube 完整 extract 與 RSS 佔大宗），三大 BD 站本身只要數秒
