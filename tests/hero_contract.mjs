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
const HTTP_PORT = 8797;  // 8791 被 nioh3 專案的 dev server 佔用
const CDP_PORT = 9337;

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

  // ── 回歸：初次載入就該看得到內容（必須放在任何點擊/捲動之前）──
  check("R0 初次載入內容區就可見（不需先點 tab）", () => {
    const v = document.querySelector("#view-builds");
    if (!v) return "找不到 #view-builds";
    if (v.classList.contains("hidden")) return "#view-builds 初次載入就是 hidden — init 沒有做初始 switchView";
    const h = Math.round(v.getBoundingClientRect().height);
    return h > 0 ? true : "#view-builds 可見但高度是 " + h;
  });

  // ── 契約：hero 結構 ──
  check("C1 hero section 存在", () =>
    document.querySelector("#hero") ? true : "找不到 #hero");

  check("C2 四個場景圖層齊全且順序正確", () => {
    const got = [...document.querySelectorAll("#hero .scene-img")]
      .map(e => [...e.classList].find(c => c.startsWith("scene-") && c !== "scene-img") ?? e.className);
    const want = ["scene-sky", "scene-town", "scene-frame-left", "scene-frame-right"];
    return JSON.stringify(got) === JSON.stringify(want)
      ? true : \`期望 \${JSON.stringify(want)}，實得 \${JSON.stringify(got)}\`;
  });

  check("C3 五張 CTA 卡的 data-tab 依序對應既有 tab", () => {
    const got = [...document.querySelectorAll("#hero .cta-card")].map(e => e.dataset.tab);
    const want = ["builds", "hot", "new", "bahamut", "tweets"];
    return JSON.stringify(got) === JSON.stringify(want)
      ? true : \`期望 \${JSON.stringify(want)}，實得 \${JSON.stringify(got)}\`;
  });

  // ── 契約：巨蛇邊框必須貼齊視窗左右緣（Bug A）──
  const edgeCheck = (el, side, vw) => {
    const cs = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    if (box.width < 30) return \`\${side} 邊框只有 \${box.width.toFixed(0)}px 寬，等於看不到\`;
    const touches = side === "left" ? box.left <= 1 : box.right >= vw - 1;
    if (!touches) return \`\${side} 邊框沒有貼齊視窗\${side === "left" ? "左" : "右"}緣（left=\${box.left.toFixed(0)}, right=\${box.right.toFixed(0)}, vw=\${vw}）\`;
    // 貼邊還不夠：背景若用 cover + center，窄視窗一樣會把蛇裁掉
    const posX = (cs.backgroundPosition.split(",")[0] || "").trim().split(/\\s+/)[0];
    const sizeX = (cs.backgroundSize.split(",")[0] || "").trim().split(/\\s+/)[0];
    const pinned = side === "left"
      ? ["0%", "0px", "left"].includes(posX)
      : ["100%", "right"].includes(posX);
    const unclipped = ["100%", "contain"].includes(sizeX) || sizeX.endsWith("px");
    if (!pinned && !unclipped)
      return \`\${side} 邊框貼邊了，但 background-position-x="\${posX}" / background-size-x="\${sizeX}" 仍會裁掉外緣的蛇\`;
    return true;
  };

  check("C6 左右邊框貼齊視窗兩緣且外緣不被裁（桌機 1440）", () => {
    const l = document.querySelector("#hero .scene-frame-left");
    const r = document.querySelector("#hero .scene-frame-right");
    if (!l || !r) return "找不到 .scene-frame-left / .scene-frame-right";
    const vw = document.documentElement.clientWidth;
    const rl = edgeCheck(l, "left", vw);
    if (rl !== true) return rl;
    return edgeCheck(r, "right", vw);
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

  check("C7 捲動時左右邊框往反方向移開（--frame-x 有被 CSS 消費）", () => {
    const l = document.querySelector("#hero .scene-frame-left");
    const r = document.querySelector("#hero .scene-frame-right");
    if (!l || !r) return "找不到 .scene-frame-left / .scene-frame-right";
    const tx = el => new DOMMatrixReadOnly(getComputedStyle(el).transform).m41;
    const lx = tx(l), rx = tx(r);
    if (Math.abs(lx) < 1 && Math.abs(rx) < 1)
      return "已捲到 hero 底部，但兩側邊框都沒有水平位移 — --frame-x 沒有被 CSS 讀取";
    if (!(lx < 0 && rx > 0))
      return \`方向不對：左邊框應往負向、右邊框應往正向，實得 left=\${lx.toFixed(1)}, right=\${rx.toFixed(1)}\`;
    return true;
  });

  // 依 CSS 規則算出背景實際被畫成多大，用來同時抓「變形」與「放大到只看得到局部」
  const drawnSize = async (el) => {
    const cs = getComputedStyle(el);
    const url = (cs.backgroundImage.match(/url\\(\"?(.*?)\"?\\)/) || [])[1];
    if (!url) return null;
    const img = new Image();
    img.src = url;
    await img.decode();
    const nw = img.naturalWidth, nh = img.naturalHeight, ratio = nw / nh;
    const ew = el.clientWidth, eh = el.clientHeight;
    const spec = cs.backgroundSize.split(",")[0].trim();
    let dw, dh;
    if (spec === "cover" || spec === "contain") {
      const sc = spec === "cover" ? Math.max(ew / nw, eh / nh) : Math.min(ew / nw, eh / nh);
      dw = nw * sc; dh = nh * sc;
    } else {
      const parts = spec.split(/\\s+/);
      const parse = (v, base) => (!v || v === "auto") ? null
        : (v.endsWith("%") ? parseFloat(v) / 100 * base : parseFloat(v));
      const w = parse(parts[0], ew), h = parse(parts[1], eh);
      if (w === null && h === null) { dw = nw; dh = nh; }
      else if (w === null) { dh = h; dw = h * ratio; }
      else if (h === null) { dw = w; dh = w / ratio; }
      else { dw = w; dh = h; }
    }
    return { dw, dh, ew, eh, ratio, spec };
  };

  const frames = {};
  for (const sel of [".scene-frame-left", ".scene-frame-right"]) {
    const el = document.querySelector("#hero " + sel);
    frames[sel] = el ? await drawnSize(el) : null;
  }

  check("C9 邊框素材不得被拉伸變形", () => {
    const bad = [];
    for (const [sel, m] of Object.entries(frames)) {
      if (!m) { bad.push(sel + " 量不到背景"); continue; }
      const drawn = m.dw / m.dh;
      if (Math.abs(drawn - m.ratio) / m.ratio > 0.05)
        bad.push(\`\${sel} background-size="\${m.spec}" 把素材畫成 \${m.dw.toFixed(0)}x\${m.dh.toFixed(0)}（比例 \${drawn.toFixed(3)}），素材原比例是 \${m.ratio.toFixed(3)} — 蛇會變形\`);
    }
    return bad.length ? bad.join("；") : true;
  });

  check("C10 邊框素材不得被放大到只看得見局部", () => {
    const bad = [];
    for (const [sel, m] of Object.entries(frames)) {
      if (!m) { bad.push(sel + " 量不到背景"); continue; }
      const over = m.dw / m.ew;
      if (over > 1.15)
        bad.push(\`\${sel} 背景被畫成 \${m.dw.toFixed(0)}px 寬，但元素只有 \${m.ew.toFixed(0)}px — 素材有 \${((1 - 1 / over) * 100).toFixed(0)}% 被裁掉，等於只看得到蛇的局部\`);
    }
    return bad.length ? bad.join("；") : true;
  });

  // C4 用 scrollTo(0, hero.offsetHeight) 會捲過 sticky 的有效範圍，
  // 舞台已經離開畫面，量幾何沒有意義。這裡捲回「進度 100% 但舞台仍黏著」的位置。
  if (hero) {
    window.scrollTo(0, hero.offsetHeight - window.innerHeight);
    window.dispatchEvent(new Event("scroll"));
    await sleep(400);
  }

  check("C11 捲動時 town 層仍蓋滿視窗底部（不露出下緣硬邊）", () => {
    const t = document.querySelector("#hero .scene-town");
    if (!t) return "找不到 .scene-town";
    const box = t.getBoundingClientRect();
    const vh = document.documentElement.clientHeight;
    // town 捲動時會上移做視差，若元素本身沒有向下的餘裕，下緣就會離開視窗、
    // 在畫面底部切出一條橫向硬邊（放大截圖可見）
    return box.bottom >= vh - 1 ? true
      : \`town 下緣在 \${box.bottom.toFixed(0)}px，視窗高 \${vh}px — 底部露出 \${(vh - box.bottom).toFixed(0)}px 的硬邊\`;
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


// ── 窄／直式視窗下的巨蛇可見性契約（跑在多個尺寸上）───────────
const narrowContract = (label) => `(async () => {
  const results = [];
  const l = document.querySelector("#hero .scene-frame-left");
  const r = document.querySelector("#hero .scene-frame-right");
  const vw = document.documentElement.clientWidth;
  const push = (name, ok, detail) => results.push({ name, ok, detail });

  if (!l || !r) {
    push("C8 ${label} 左右巨蛇貼齊兩緣可見", false, "找不到 .scene-frame-left / .scene-frame-right");
    return JSON.stringify(results);
  }

  const bl = l.getBoundingClientRect(), br = r.getBoundingClientRect();
  let ok = true, detail = "";
  if (bl.width < 30 || br.width < 30) { ok = false; detail = \`邊框寬度 left=\${bl.width.toFixed(0)}px right=\${br.width.toFixed(0)}px，等於看不到蛇\`; }
  else if (bl.left > 1) { ok = false; detail = \`左邊框沒貼左緣（left=\${bl.left.toFixed(0)}）\`; }
  else if (br.right < vw - 1) { ok = false; detail = \`右邊框沒貼右緣（right=\${br.right.toFixed(0)}, vw=\${vw}）\`; }
  push("C8 ${label} 左右巨蛇貼齊兩緣可見", ok, detail);

  // 同一組尺寸下也要驗「沒被放大到只剩局部」—— iPad 直式就是栽在這裡
  const drawn = async (el) => {
    const cs = getComputedStyle(el);
    const url = (cs.backgroundImage.match(/url\\(\"?(.*?)\"?\\)/) || [])[1];
    if (!url) return null;
    const img = new Image(); img.src = url; await img.decode();
    const nw = img.naturalWidth, nh = img.naturalHeight, ratio = nw / nh;
    const ew = el.clientWidth, eh = el.clientHeight;
    const spec = cs.backgroundSize.split(",")[0].trim();
    let dw, dh;
    if (spec === "cover" || spec === "contain") {
      const sc = spec === "cover" ? Math.max(ew / nw, eh / nh) : Math.min(ew / nw, eh / nh);
      dw = nw * sc; dh = nh * sc;
    } else {
      const parts = spec.split(/\\s+/);
      const parse = (v, base) => (!v || v === "auto") ? null
        : (v.endsWith("%") ? parseFloat(v) / 100 * base : parseFloat(v));
      const w = parse(parts[0], ew), h = parse(parts[1], eh);
      if (w === null && h === null) { dw = nw; dh = nh; }
      else if (w === null) { dh = h; dw = h * ratio; }
      else if (h === null) { dw = w; dh = w / ratio; }
      else { dw = w; dh = h; }
    }
    return { dw, dh, ew, ratio, spec };
  };

  const bad = [];
  for (const [sel, el] of [[".scene-frame-left", l], [".scene-frame-right", r]]) {
    const m = await drawn(el);
    if (!m) { bad.push(sel + " 量不到背景"); continue; }
    if (Math.abs(m.dw / m.dh - m.ratio) / m.ratio > 0.05)
      bad.push(\`\${sel} 變形（畫成 \${m.dw.toFixed(0)}x\${m.dh.toFixed(0)}，原比例 \${m.ratio.toFixed(3)}）\`);
    else if (m.dw / m.ew > 1.15)
      bad.push(\`\${sel} 被放大到 \${m.dw.toFixed(0)}px 寬但元素只有 \${m.ew.toFixed(0)}px，只看得到局部\`);
  }
  push("C10 ${label} 巨蛇不變形也不被放大到只剩局部", bad.length === 0, bad.join("；"));

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

  // 切成直式尺寸再驗巨蛇可見性（Bug A 的真正現場，桌機看不出來）
  const PORTRAITS = [
    { label: "iPad 直式 768x1024", w: 768, h: 1024 },
    { label: "手機直式 390x844", w: 390, h: 844 },
  ];
  const rn = [];
  for (const p of PORTRAITS) {
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: p.w, height: p.h, deviceScaleFactor: 1, mobile: false });
    await cdp.send("Runtime.evaluate", { expression: "window.scrollTo(0,0); window.dispatchEvent(new Event('scroll'));" });
    await sleep(400);
    rn.push(await cdp.send("Runtime.evaluate", {
      expression: narrowContract(p.label), awaitPromise: true, returnByValue: true }));
  }
  await cdp.send("Emulation.clearDeviceMetricsOverride");

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
  for (let i = 0; i < rn.length; i++) {
    try {
      results.push(...JSON.parse(rn[i].result.result.value));
    } catch {
      results.push({ name: `直式契約（第 ${i + 1} 組尺寸）`, ok: false,
                     detail: "沒有回傳結果：" + JSON.stringify(rn[i]).slice(0, 300) });
    }
  }
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
