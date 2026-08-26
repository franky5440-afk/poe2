#!/usr/bin/env node
// Hero cinematic 捲動場景的契約測試。
//
// 跑法：node tests/hero_contract.mjs
// 不需要任何 npm 套件：用 Node 22 內建 WebSocket 直接講 CDP，驅動本機 Chrome headless。
//
// C1–C5 在 hero 實作完成前必然失敗（那就是待實作的契約）。
// R1–R3 是回歸保護，任何時候都必須綠。

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const BASE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SITE = path.join(BASE, "site");
const HTTP_PORT = 8791;
const CDP_PORT = 9333;

const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
               ".json": "application/json", ".webp": "image/webp", ".png": "image/png",
               ".jpg": "image/jpeg", ".svg": "image/svg+xml" };

// ── 在瀏覽器裡跑的契約 ─────────────────────────────────────────────
const CONTRACT = `(async () => {
  const results = [];
  const check = (name, fn) => {
    try { const r = fn(); results.push({ name, ok: r === true, detail: r === true ? "" : String(r) }); }
    catch (e) { results.push({ name, ok: false, detail: "EXCEPTION: " + e.message }); }
  };
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  // 等資料 fetch 完成、內容區渲染出來
  for (let i = 0; i < 60; i++) {
    if (document.querySelector("#buildList")?.children.length) break;
    await sleep(100);
  }

  // ── 契約：hero 結構 ──
  check("C1 hero section 存在", () =>
    document.querySelector("#hero") ? true : "找不到 #hero");

  check("C2 三個場景圖層齊全且順序正確", () => {
    const got = [...document.querySelectorAll("#hero .scene-img")]
      .map(e => [...e.classList].find(c => c.startsWith("scene-")) ?? e.className);
    const want = ["scene-sky", "scene-town", "scene-frame"];
    return JSON.stringify(got) === JSON.stringify(want)
      ? true : \`期望 \${JSON.stringify(want)}，實得 \${JSON.stringify(got)}\`;
  });

  check("C3 五張 CTA 卡的 data-tab 依序對應既有 tab", () => {
    const got = [...document.querySelectorAll("#hero .cta-card")].map(e => e.dataset.tab);
    const want = ["builds", "hot", "new", "bahamut", "tweets"];
    return JSON.stringify(got) === JSON.stringify(want)
      ? true : \`期望 \${JSON.stringify(want)}，實得 \${JSON.stringify(got)}\`;
  });

  // ── 契約：hero 行為 ──
  const hero = document.querySelector("#hero");
  if (hero) {
    window.scrollTo(0, hero.offsetHeight);
    window.dispatchEvent(new Event("scroll"));
    await sleep(400);
  }

  check("C4 捲到 hero 底部時標題已淡出 (--title-opacity <= 0.05)", () => {
    if (!hero) return "找不到 #hero，無法捲動";
    const raw = getComputedStyle(document.documentElement).getPropertyValue("--title-opacity");
    const v = parseFloat(raw);
    if (Number.isNaN(v)) return "--title-opacity 未定義";
    return v <= 0.05 ? true : \`實得 \${v}\`;
  });

  check("C5 點第 3 張 CTA 卡會切到「最新影片」view", () => {
    const cards = document.querySelectorAll("#hero .cta-card");
    if (cards.length < 3) return \`只有 \${cards.length} 張卡\`;
    cards[2].click();
    const view = document.querySelector("#view-new");
    const tab = document.querySelector('.tab[data-tab="new"]');
    if (!view) return "找不到 #view-new";
    if (view.classList.contains("hidden")) return "#view-new 仍是 hidden";
    if (!tab?.classList.contains("active")) return ".tab[data-tab=new] 沒有 active";
    return true;
  });

  // ── 回歸：既有功能不可被破壞 ──
  check("R1 五個既有 tab 按鈕都還在", () => {
    const got = [...document.querySelectorAll("nav.tabs .tab")].map(e => e.dataset.tab);
    const want = ["builds", "hot", "new", "bahamut", "tweets"];
    return JSON.stringify(got) === JSON.stringify(want) ? true : \`實得 \${JSON.stringify(got)}\`;
  });

  check("R2 既有 tab 切換仍正常運作", () => {
    document.querySelector('.tab[data-tab="bahamut"]').click();
    const v = document.querySelector("#view-bahamut");
    return v && !v.classList.contains("hidden") ? true : "#view-bahamut 沒有顯示出來";
  });

  check("R3 BD 內容區仍有渲染出卡片（資料流沒斷）", () => {
    const n = document.querySelector("#buildList")?.children.length ?? 0;
    return n > 0 ? true : "#buildList 是空的";
  });

  return JSON.stringify(results);
})()`;

// ── CDP 小客戶端 ───────────────────────────────────────────────────
class CDP {
  constructor(ws) { this.ws = ws; this.id = 0; this.pending = new Map();
    ws.onmessage = e => { const m = JSON.parse(e.data);
      if (m.id && this.pending.has(m.id)) { this.pending.get(m.id)(m); this.pending.delete(m.id); } }; }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise(res => { this.pending.set(id, res);
      this.ws.send(JSON.stringify({ id, method, params })); });
  }
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  console.log("[1/4] 建置靜態站…");
  const venvPy = path.join(BASE, "venv", "bin", "python");
  const py = fs.existsSync(venvPy) ? venvPy : "python3";
  const b = spawnSync(py, [path.join(BASE, "build_site.py")], { cwd: BASE, encoding: "utf8" });
  if (b.status !== 0) { console.error("build_site.py 失敗：", b.stderr); return 2; }
  console.log("      ", b.stdout.trim());

  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(req.url.split("?")[0]);
    const file = path.join(SITE, rel === "/" ? "/index.html" : rel);
    if (!file.startsWith(SITE) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404).end("nope"); return;
    }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] ?? "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(r => server.listen(HTTP_PORT, "127.0.0.1", r));
  console.log(`[2/4] 靜態站起在 127.0.0.1:${HTTP_PORT}`);

  const chrome = spawn("google-chrome", [
    "--headless", "--disable-gpu", "--no-sandbox", "--window-size=1440,900",
    `--remote-debugging-port=${CDP_PORT}`,
    "--user-data-dir=/tmp/poe2-hero-test-profile",
    "about:blank",
  ], { stdio: "ignore" });

  let target = null;
  for (let i = 0; i < 60; i++) {
    await sleep(500);
    try {
      const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
      target = list.find(t => t.type === "page");
      if (target?.webSocketDebuggerUrl) break;
    } catch { /* chrome 還沒起來 */ }
  }
  if (!target) { console.error("連不上 Chrome CDP"); chrome.kill(); server.close(); return 2; }
  console.log("[3/4] Chrome 已連上，跑契約…");

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  const cdp = new CDP(ws);

  await cdp.send("Page.enable");
  await cdp.send("Page.navigate", { url: `http://127.0.0.1:${HTTP_PORT}/index.html` });
  let ready = false;
  for (let i = 0; i < 80; i++) {
    await sleep(500);
    const rs = await cdp.send("Runtime.evaluate", {
      expression: "document.readyState + '|' + location.pathname", returnByValue: true });
    const v = rs.result?.result?.value ?? "";
    if (v.startsWith("complete") && v.includes("/index.html")) { ready = true; break; }
  }
  if (!ready) { console.error("頁面沒有載入完成"); ws.close(); chrome.kill(); server.close(); return 2; }

  const r = await cdp.send("Runtime.evaluate", {
    expression: CONTRACT, awaitPromise: true, returnByValue: true,
  });

  ws.close(); chrome.kill(); server.close();

  if (r.error) {
    console.error("CDP 回錯誤：", JSON.stringify(r.error, null, 2));
    return 2;
  }
  if (!r.result) {
    console.error("CDP 回應非預期：", JSON.stringify(r).slice(0, 600));
    return 2;
  }
  if (r.result?.exceptionDetails) {
    console.error("契約腳本自己爆了：", JSON.stringify(r.result.exceptionDetails, null, 2));
    return 2;
  }
  const results = JSON.parse(r.result.result.value);
  console.log("[4/4] 契約結果：\n");
  let passed = 0;
  for (const x of results) {
    console.log(`  [${x.ok ? "PASS" : "FAIL"}] ${x.name}`);
    if (!x.ok) console.log(`         → ${x.detail}`);
    passed += x.ok ? 1 : 0;
  }
  console.log(`\n  ${passed}/${results.length} 通過`);
  return passed === results.length ? 0 : 1;
}

main().then(c => process.exit(c)).catch(e => { console.error(e); process.exit(2); });
