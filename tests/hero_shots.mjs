#!/usr/bin/env node
// Hero 場景的「視覺」驗收工具 —— 契約測不到的那一半。
//
// 跑法：node tests/hero_shots.mjs [輸出目錄]
//       預設輸出到 logs/hero-shots/（logs/ 已在 .gitignore，截圖不入版控）
//
// 為什麼需要這支：
//   hero 的契約測試曾經 9/9 全綠，卻同時放行了兩個一眼就看得出來的視覺 bug
//   （直式螢幕看不到巨蛇、捲動時有殘影）。契約能驗結構、行為、幾何，但驗不到
//   色調對不對、硬邊突不突兀、構圖失不失衡。那些只能靠眼睛，這支負責把「眼睛
//   要看的東西」產出來。
//
// 它會在三種尺寸 x 四個捲動位置各截一張，共 12 張。跟 hero_contract.mjs 一樣
// 不需要任何 npm 套件：用 Node 22 內建的 WebSocket 直接講 CDP 驅動 headless Chrome。
//
// ⚠️ 截圖裡不明顯的東西要另外裁切放大看。town 層底部那條硬邊在整張截圖裡幾乎
//    看不出來，是裁出一小條放大兩倍才發現的。

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const BASE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SITE = path.join(BASE, "site");
const OUT = process.argv[2] ? path.resolve(process.argv[2]) : path.join(BASE, "logs", "hero-shots");
const HTTP_PORT = 8798;   // 避開 hero_contract.mjs 的 8797 與 nioh3 的 8791
const CDP_PORT = 9338;

const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
               ".json": "application/json", ".webp": "image/webp", ".png": "image/png",
               ".jpg": "image/jpeg", ".svg": "image/svg+xml" };

const VIEWPORTS = [
  { name: "desktop", w: 1440, h: 900 },
  { name: "ipad",    w: 768,  h: 1024 },   // 直式，Bug A 當初的現場
  { name: "phone",   w: 390,  h: 844 },
];
const SCROLLS = [0, 0.35, 0.7, 1.0];       // hero 捲動進度

class CDP {
  constructor(ws) { this.ws = ws; this.id = 0; this.pending = new Map();
    ws.onmessage = e => { const m = JSON.parse(e.data);
      if (m.id && this.pending.has(m.id)) { this.pending.get(m.id)(m); this.pending.delete(m.id); } }; }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise(r => { this.pending.set(id, r); this.ws.send(JSON.stringify({ id, method, params })); });
  }
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ⚠️ 一定要先重新建置，否則截到的是舊的 site/（這裡浪費過一輪）
const venvPy = path.join(BASE, "venv", "bin", "python");
const py = fs.existsSync(venvPy) ? venvPy : "python3";
const b = spawnSync(py, [path.join(BASE, "build_site.py")], { cwd: BASE, encoding: "utf8" });
if (b.status !== 0) { console.error("build_site.py 失敗：", b.stderr); process.exit(2); }
console.log("[1/3]", b.stdout.trim());

const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(req.url.split("?")[0]);
  const f = path.join(SITE, rel === "/" ? "/index.html" : rel);
  if (!f.startsWith(SITE) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404).end(); return; }
  res.writeHead(200, { "Content-Type": MIME[path.extname(f)] ?? "application/octet-stream" });
  fs.createReadStream(f).pipe(res);
});
await new Promise(r => server.listen(HTTP_PORT, "127.0.0.1", r));

const chrome = spawn("google-chrome", ["--headless", "--disable-gpu", "--no-sandbox",
  `--remote-debugging-port=${CDP_PORT}`, "--user-data-dir=/tmp/poe2-hero-shots-profile", "about:blank"],
  { stdio: "ignore" });

let target = null;
for (let i = 0; i < 60; i++) {
  await sleep(500);
  try {
    const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
    target = list.find(t => t.type === "page");
    if (target?.webSocketDebuggerUrl) break;
  } catch { /* chrome 還沒起來 */ }
}
if (!target) { console.error("連不上 Chrome CDP"); chrome.kill(); server.close(); process.exit(2); }

const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
const cdp = new CDP(ws);
await cdp.send("Page.enable");
await cdp.send("Page.navigate", { url: `http://127.0.0.1:${HTTP_PORT}/index.html` });
for (let i = 0; i < 80; i++) {
  await sleep(300);
  const rs = await cdp.send("Runtime.evaluate", { expression: "document.readyState", returnByValue: true });
  if (rs.result?.result?.value === "complete") break;
}
await sleep(1500);   // 等資料 fetch 完、圖片解碼完
console.log("[2/3] Chrome 已連上，開始截圖…");

fs.mkdirSync(OUT, { recursive: true });
for (const v of VIEWPORTS) {
  await cdp.send("Emulation.setDeviceMetricsOverride", { width: v.w, height: v.h, deviceScaleFactor: 1, mobile: false });
  await sleep(500);
  for (const s of SCROLLS) {
    await cdp.send("Runtime.evaluate", { expression:
      `(() => { const h = document.querySelector("#hero");
         const r = Math.max(h.offsetHeight - window.innerHeight, 1);
         window.scrollTo(0, r * ${s}); window.dispatchEvent(new Event("scroll")); })()` });
    await sleep(500);
    const shot = await cdp.send("Page.captureScreenshot", { format: "png" });
    const f = path.join(OUT, `${v.name}_${Math.round(s * 100)}.png`);
    fs.writeFileSync(f, Buffer.from(shot.result.data, "base64"));
    console.log("      ", path.basename(f));
  }
}
await cdp.send("Emulation.clearDeviceMetricsOverride");
ws.close(); chrome.kill(); server.close();
console.log("[3/3] 12 張截圖完成 →", OUT);
process.exit(0);
