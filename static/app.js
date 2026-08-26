const SOURCE_HINTS = {
  mobalytics: "Mobalytics 站方熱門精選 BD，依站內排序取前 10",
  maxroll: "Maxroll 官方攻略團隊 BD 指南，依最新更新排序取前 10",
  poeninja: "poe.ninja 天梯統計：現行軟核聯盟使用率前 10 升華（占比為全聯盟角色百分比）",
};

const state = {
  data: null,
  buildsSource: "mobalytics",
  hotLang: "zh", newLang: "zh", tweetsLang: "zh",
  activeTab: "builds",
};
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  // textContent→innerHTML 只轉義 & < >，不含引號；值會被插進 src/href 屬性，故補上
  return d.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function fmtViews(n) {
  if (typeof n !== "number") return "";
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, "") + " 萬觀看";
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "K 觀看";
  return n + " 觀看";
}

const EXT_ICON = '<svg class="ext-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14L21 3"/></svg>';

function buildCard(b) {
  const tags = (b.tags || []).slice(0, 4)
    .map((t) => `<span class="tag">${esc(t)}</span>`).join("");
  const sub = [
    b.author ? `👤 ${esc(b.author)}` : "",
    b.updated ? `🕒 ${esc(b.updated)}` : "",
    b.patch ? `⭐ ${esc(b.patch)}` : "",
  ].filter(Boolean).join("");
  return `<article class="build-card">
    <span class="rank-badge">${b.rank}</span>
    <div class="build-main">
      <h4><a href="${esc(b.url)}" target="_blank" rel="noopener noreferrer">${esc(b.title)}</a></h4>
      ${sub ? `<div class="thread-sub">${sub}</div>` : ""}
      ${tags ? `<div class="card-foot">${tags}</div>` : ""}
    </div>
  </article>`;
}

function metaCard(m, maxPct) {
  const pct = typeof m.share_pct === "number" ? m.share_pct : 0;
  const w = maxPct > 0 ? Math.max(4, Math.round((pct / maxPct) * 100)) : 0;
  const trend = m.trend === 1
    ? '<span class="trend up">↗ 上升</span>'
    : m.trend === -1
      ? '<span class="trend down">↘ 下降</span>'
      : '<span class="trend flat">→ 持平</span>';
  return `<article class="meta-card">
    <span class="rank-badge">${m.rank}</span>
    <div class="build-main">
      <h4><a href="${esc(m.url)}" target="_blank" rel="noopener noreferrer">${esc(m.title)}</a></h4>
      <div class="share-bar"><span style="width:${w}%"></span></div>
      <div class="thread-sub">
        <span>${pct.toFixed(2)}% 使用率</span>${trend}
        <span>聯盟：${esc(m.league || "")}</span>
        ${typeof m.total_chars === "number" ? `<span>樣本 ${m.total_chars.toLocaleString()} 角色</span>` : ""}
      </div>
    </div>
  </article>`;
}

function videoCard(v, rank) {
  const vid = esc(v.video_id);
  return `<article class="video-card">
    <a class="thumb-link" href="${esc(v.url)}" target="_blank" rel="noopener noreferrer">
      <img class="thumb" src="https://i.ytimg.com/vi/${vid}/mqdefault.jpg" alt="" loading="lazy" referrerpolicy="no-referrer">
      <span class="play-badge"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.14v14l11-7-11-7z"/></svg></span>
      ${rank != null ? `<span class="rank-badge corner">${rank}</span>` : ""}
    </a>
    <div class="video-info">
      <h4><a href="${esc(v.url)}" target="_blank" rel="noopener noreferrer">${esc(v.title)}</a></h4>
      <div class="video-meta">
        <span class="lang-flag">${v.lang === "zh" ? "中文" : v.lang === "ja" ? "日文" : "EN"}</span>
        <span>${esc(v.channel)}</span>
        ${v.views != null ? `<span>👁 ${fmtViews(v.views)}</span>` : ""}
        ${v.date ? `<span>📅 ${esc(v.date)}</span>` : ""}
      </div>
    </div>
  </article>`;
}

document.addEventListener("error", (e) => {
  const img = e.target;
  if (img.tagName === "IMG" && img.classList.contains("thumb")) img.style.visibility = "hidden";
}, true);

/* ---------- renders ---------- */
function renderBuilds() {
  const src = state.buildsSource;
  $("#buildHint").textContent = SOURCE_HINTS[src] || "";
  const list = state.data[`builds_${src}`] || [];
  if (!list.length) {
    $("#buildList").innerHTML = '<p class="empty-msg">此來源尚無資料，等待下次每日掃描。</p>';
    return;
  }
  if (src === "poeninja") {
    const maxPct = Math.max(...list.map((m) => m.share_pct || 0));
    $("#buildList").innerHTML = list.map((m) => metaCard(m, maxPct)).join("");
  } else {
    $("#buildList").innerHTML = list.map(buildCard).join("");
  }
}

function renderVideos() {
  const hot = state.data[`videos_hot_${state.hotLang}`] || [];
  const fresh = state.data[`videos_new_${state.newLang}`] || [];
  $("#hotGrid").innerHTML = hot.length ? hot.map((v, i) => videoCard(v, i + 1)).join("") : '<p class="empty-msg">尚無資料。</p>';
  $("#newGrid").innerHTML = fresh.length ? fresh.map((v) => videoCard(v)).join("") : '<p class="empty-msg">尚無資料。</p>';
}

function renderBahamut() {
  const items = state.data.bahamut || [];
  $("#bahaList").innerHTML = items.length ? items.map((b, i) => `
    <div class="thread-item">
      <span class="thread-num">${i + 1}</span>
      <div class="thread-body">
        <h4><a href="${esc(b.url)}" target="_blank" rel="noopener noreferrer">${esc(b.title)}</a></h4>
        <div class="thread-sub"><span>👤 ${esc(b.author) || "匿名"}</span><span>🕒 ${esc(b.time)}</span></div>
      </div>
      ${b.replies ? `<span class="reply-badge">回應 ${esc(b.replies)}</span>` : ""}
    </div>`).join("") : '<p class="empty-msg">尚無資料。</p>';
}

function renderTweets() {
  const items = state.data[`tweets_${state.tweetsLang}`] || [];
  $("#tweetList").innerHTML = items.length ? items.map((tw) => `
    <article class="tweet-item">
      <div class="tweet-head">
        <a class="tweet-author" href="https://x.com/${esc(tw.author)}" target="_blank" rel="noopener noreferrer">${esc(tw.author_name || tw.author)}</a>
        <span class="tweet-handle">@${esc(tw.author)}</span>
        ${tw.date ? `<span>📅 ${esc(tw.date)}</span>` : ""}
        ${typeof tw.likes === "number" ? `<span>❤️ ${tw.likes.toLocaleString()}</span>` : ""}
        <a class="ext-link" href="${esc(tw.url)}" target="_blank" rel="noopener noreferrer" aria-label="在 X 開啟">${EXT_ICON}</a>
      </div>
      <p class="tweet-text"><a href="${esc(tw.url)}" target="_blank" rel="noopener noreferrer">${esc(tw.text)}</a></p>
    </article>`).join("") : '<p class="empty-msg">尚無資料。</p>';
}

function renderMeta() {
  const meta = state.data.meta || {};
  const map = {
    builds: ["builds_mobalytics", "builds_maxroll", "builds_poeninja"],
    videos_hot: ["videos_hot_zh", "videos_hot_en", "videos_hot_ja"],
    videos_new: ["videos_new_zh", "videos_new_en", "videos_new_ja"],
    bahamut: ["bahamut"],
    tweets: ["tweets_zh", "tweets_en", "tweets_ja"],
  };
  $$("[data-meta]").forEach((el) => {
    const times = (map[el.dataset.meta] || []).map((k) => meta[k]).filter(Boolean);
    el.textContent = times.length ? `最後更新：${times.sort().reverse()[0]}` : "尚未更新";
  });
  if (meta._last_run) $("#lastRun").textContent = `上次完整掃描：${meta._last_run}`;
}

/* ---------- search ---------- */
function localSearch(raw) {
  const q = raw.trim().toLowerCase();
  if (!q) return null;
  const words = q.split(/\s+/);
  const m = (item, keys) => {
    const hay = keys.map((k) => Array.isArray(item[k]) ? item[k].join(" ") : String(item[k] || "")).join(" ").toLowerCase();
    return words.every((w) => hay.includes(w));
  };
  const builds = [...(state.data.builds_mobalytics || []), ...(state.data.builds_maxroll || []), ...(state.data.builds_poeninja || [])]
    .filter((b) => m(b, ["title", "author", "source", "classes", "tags", "league", "patch"])).slice(0, 30);
  const hot = [...(state.data.videos_hot_zh || []), ...(state.data.videos_hot_en || []), ...(state.data.videos_hot_ja || [])]
    .filter((v) => m(v, ["title", "channel", "lang"])).slice(0, 20);
  const fresh = [...(state.data.videos_new_zh || []), ...(state.data.videos_new_en || []), ...(state.data.videos_new_ja || [])]
    .filter((v) => m(v, ["title", "channel", "lang"])).slice(0, 20);
  const baha = (state.data.bahamut || [])
    .filter((b) => m(b, ["title", "snippet", "author", "source"])).slice(0, 20);
  const tweets = [...(state.data.tweets_zh || []), ...(state.data.tweets_en || []), ...(state.data.tweets_ja || [])]
    .filter((t) => m(t, ["text", "author", "author_name"]))
    .sort((a, b) => String(b.date || "").localeCompare(String(a.date || ""))).slice(0, 20);
  return { builds, hot, new: fresh, bahamut: baha, tweets, total: builds.length + hot.length + fresh.length + baha.length + tweets.length };
}

async function doSearch(q) {
  q = q.trim();
  if (!q) return;
  const r = localSearch(q);
  $("#searchTitle").textContent = `「${q}」搜尋結果：共 ${r.total} 筆`;
  let html = "";
  if (r.builds.length) html += `<h3 class="group-title">Build（${r.builds.length}）</h3><div class="build-list">${r.builds.map((b) => b.source === "poeninja" ? metaCard(b, 20) : buildCard(b)).join("")}</div>`;
  if (r.hot.length) html += `<h3 class="group-title">熱門影片（${r.hot.length}）</h3><div class="video-grid">${r.hot.map((v) => videoCard(v)).join("")}</div>`;
  if (r.new.length) html += `<h3 class="group-title">最新影片（${r.new.length}）</h3><div class="video-grid">${r.new.map((v) => videoCard(v)).join("")}</div>`;
  if (r.bahamut.length) html += `<h3 class="group-title">巴哈討論（${r.bahamut.length}）</h3><div class="thread-list">${r.bahamut.map((b) => `
    <div class="thread-item"><div class="thread-body">
      <h4><a href="${esc(b.url)}" target="_blank" rel="noopener noreferrer">${esc(b.title)}</a></h4>
      <div class="thread-sub"><span>👤 ${esc(b.author) || "匿名"}</span><span>🕒 ${esc(b.time)}</span></div>
    </div></div>`).join("")}</div>`;
  if (r.tweets.length) html += `<h3 class="group-title">X 推文（${r.tweets.length}）</h3><div class="tweet-list">${r.tweets.map((tw) => `
    <article class="tweet-item">
      <div class="tweet-head">
        <a class="tweet-author" href="https://x.com/${esc(tw.author)}" target="_blank" rel="noopener noreferrer">${esc(tw.author_name || tw.author)}</a>
        <span class="tweet-handle">@${esc(tw.author)}</span>
        ${tw.date ? `<span>📅 ${esc(tw.date)}</span>` : ""}
        ${typeof tw.likes === "number" ? `<span>❤️ ${tw.likes.toLocaleString()}</span>` : ""}
        <a class="ext-link" href="${esc(tw.url)}" target="_blank" rel="noopener noreferrer" aria-label="在 X 開啟">${EXT_ICON}</a>
      </div>
      <p class="tweet-text"><a href="${esc(tw.url)}" target="_blank" rel="noopener noreferrer">${esc(tw.text)}</a></p>
    </article>`).join("")}</div>`;
  $("#searchResults").innerHTML = html || `<p class="no-result">找不到符合「${esc(q)}」的內容。</p>`;
  switchView("search");
}

function switchView(name) {
  if (name !== "search") state.activeTab = name;
  $$(".view").forEach((el) => el.classList.add("hidden"));
  $(`#view-${name}`).classList.remove("hidden");
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  window.scrollTo({ top: 0 });
}

/* ---------- init ---------- */
document.addEventListener("DOMContentLoaded", async () => {
  state.data = await (await fetch("data/site.json")).json();
  renderBuilds(); renderVideos(); renderBahamut(); renderTweets(); renderMeta();

  $$(".tab").forEach((t) => t.addEventListener("click", () => switchView(t.dataset.tab)));

  document.addEventListener("click", (e) => {
    const pill = e.target.closest(".pill");
    if (!pill) return;
    pill.closest(".pill-group").querySelectorAll(".pill").forEach((p) => p.classList.remove("active"));
    pill.classList.add("active");
    if (pill.dataset.source) {
      state.buildsSource = pill.dataset.source;
      renderBuilds();
    } else {
      state[`${pill.closest(".pill-group").dataset.langFor}Lang`] = pill.dataset.lang;
      renderVideos(); renderTweets();
    }
  });

  $("#searchForm").addEventListener("submit", (e) => { e.preventDefault(); doSearch($("#searchInput").value); });
  $("#clearSearch").addEventListener("click", () => { $("#searchInput").value = ""; switchView(state.activeTab); });

  switchView(state.activeTab);
});
