#!/usr/bin/env python3
import hashlib
import html as html_lib
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

import cloudscraper
import requests
import yt_dlp
from bs4 import BeautifulSoup
from ddgs import DDGS

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
LOGS = BASE / "logs"
DATA.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOGS / "scraper.log", encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("poe2")

UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.5",
}

VIDEO_DOMAINS = ("youtube.com", "youtu.be", "bilibili.com", "twitch.tv", "nicovideo.jp")

NEW_CUTOFF_DAYS = 21
HOT_CUTOFF_DAYS = 30
RSS_CHANNEL_CAP = 60
NEW_FLAT_LIMIT = 150
GAME_TERMS = ("poe2", "poe 2", "path of exile 2", "流亡黯道")

TWEET_CAP = 250
X_SEARCH_QUERIES = {
    "zh": ('"流亡黯道2" OR "POE2" site:x.com', "tw-zh"),
    "en": ('"Path of Exile 2" site:x.com', "us-en"),
    "ja": ('"PoE2" site:x.com', "jp-jp"),
}
X_OFFICIAL_ACCOUNTS = ("pathofexile",)
SYND_URL = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{}?showReplies=false"
SYND_MARKER = '<script id="__NEXT_DATA__" type="application/json">'
STATUS_RE = re.compile(r"\b(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status(?:es)?/(\d{10,})")
TIME_PREFIX_RE = re.compile(
    r"^(?:\d+\s+(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)\s+ago"
    r"|[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2})\s*[·\-–—]\s*"
)
JUNK_RES = (
    re.compile(r"log\s*in\s*sign\s*up"),
    re.compile(r"sensitive\s+content"),
    re.compile(r"this\s+post\s+is\s+(?:only\s+available|unavailable)"),
    re.compile(r"\(\@[A-Za-z0-9_]+\)\.\s*\d+\s+(?:replies|retweets|likes)\b"),
)


def clean_tweet_text(text):
    t = TIME_PREFIX_RE.sub("", text or "").strip()
    if not t:
        return None
    low = t.lower()
    if any(p.search(low) for p in JUNK_RES):
        return None
    return t


def now_str():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def load_json(name, default):
    p = DATA / name
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def save_json(name, obj):
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def set_meta(section):
    meta = load_json("meta.json", {})
    meta[section] = now_str()
    save_json("meta.json", meta)


CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")


def has_cjk(s):
    return bool(CJK_RE.search(s or ""))


def detect_lang(text, url=""):
    t = text or ""
    if KANA_RE.search(t):
        return "ja"
    d = domain_of(url)
    if d.endswith(".jp"):
        return "ja"
    if has_cjk(t):
        return "zh"
    return "en"


def norm_url(u):
    u = u.split("#")[0].rstrip("/")
    return u.lower()


def domain_of(u):
    netloc = urlparse(u).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def md5_id(text):
    return re.sub(r"[^a-f0-9]", "", hashlib.md5(text.encode()).hexdigest())


def is_video_url(url):
    d = domain_of(url)
    return any(d == vd or d.endswith("." + vd) for vd in VIDEO_DOMAINS)


# ---------------------------------------------------------------- 三大站 Top 10 BD

MOBA_BUILDS_URL = "https://mobalytics.gg/poe-2/builds"
MAXROLL_BUILDS_URL = "https://maxroll.gg/poe2/build-guides"
NINJA_STATE_URL = "https://poe.ninja/poe2/api/data/build-index-state"
NINJAA_SITE_URL = "https://poe.ninja/poe2/builds"
BUILD_TOP_N = 10


def fetch_moba_html():
    """mobalytics 在 Cloudflare 後面，requests 必被 403，須用 cloudscraper"""
    s = cloudscraper.create_scraper(browser={"browser": "firefox", "platform": "linux", "desktop": True})
    r = s.get(MOBA_BUILDS_URL, timeout=40)
    r.raise_for_status()
    return r.text


def moba_card(card):
    """單張 Mobalytics BD 卡 -> dict；非 BD 卡（工具/文章）回 None。
    卡片內容區第一個 div 是標題、第二個是「By 作者 ∙ Updated on 日期」"""
    link_a = card.select_one('a[href^="/poe-2/builds/"]')
    if not link_a:
        return None
    path = link_a.get("href", "")
    url = f"https://mobalytics.gg{path}"
    author, title, updated = "", "", None
    prof = card.select_one('a[href^="/poe-2/profile/"]')
    if prof:
        author = prof.get_text(strip=True)
        byline = prof.find_parent("div")
        wrap = byline.find_parent("div") if byline else None
        if wrap is not None:
            divs = wrap.find_all("div", recursive=False)
            if len(divs) >= 2:
                title = divs[0].get_text(" ", strip=True)
                m = re.search(r"Updated on\s+(.+)$", divs[1].get_text(" ", strip=True))
                if m:
                    updated = m.group(1).strip()
    if not title:
        title = path.rsplit("/", 1)[-1].replace("-", " ")
    if not author:
        return None
    tags = []
    for d in card.select('a[href*="-builds"]:not([href^="/poe-2/builds"])'):
        t = d.get_text(strip=True)
        if t and not t.startswith("+") and t not in tags:
            tags.append(t)
    return {
        "id": md5_id(url),
        "title": title,
        "url": url,
        "author": author,
        "updated": updated,
        "classes": [t for t in tags[:1]],
        "tags": tags[1:] if len(tags) > 1 else [],
        "source": "mobalytics",
        "found_date": now_str()[:10],
    }


def scrape_mobalytics():
    soup = BeautifulSoup(fetch_moba_html(), "html.parser")
    out, seen = [], set()
    for card in soup.select('[data-testid="discovery-item"]'):
        it = moba_card(card)
        if not it:
            continue
        k = norm_url(it["url"])
        if k in seen:
            continue
        seen.add(k)
        it["rank"] = len(out) + 1
        out.append(it)
        if len(out) >= BUILD_TOP_N:
            break
    return out


def scrape_maxroll():
    r = requests.get(MAXROLL_BUILDS_URL, headers=UA, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out, seen = [], set()
    for art in soup.find_all("article"):
        a = art.select_one('a[href^="/poe2/build-guides/"]')
        if not a:
            continue
        url = f"https://maxroll.gg{a['href']}"
        k = norm_url(url)
        if k in seen:
            continue
        seen.add(k)
        h2 = art.find("h2")
        title = (h2.get("title") if h2 else "") or (h2.get_text(" ", strip=True) if h2 else "")
        author, updated = "", None
        if h2:
            m = re.search(r"By\s+(\S+)\s*\|\s*Last Updated:\s*(.+)", h2.get_text(" ", strip=True))
            if m:
                author = m.group(1)
                updated = m.group(2).strip()
        tags = []
        patch = None
        for sp in art.select('[class*="_tag_"]'):
            t = sp.get_text(" ", strip=True)
            if not t or t in tags:
                continue
            if re.match(r"^[A-Z]\w+\s+Of\s+The\s+\w+", t) or re.match(r"^\d+\.\d+", t):
                patch = patch or t
                continue
            tags.append(t)
        out.append({
            "id": md5_id(url),
            "rank": len(out) + 1,
            "title": title.strip(),
            "url": url,
            "author": author,
            "updated": updated,
            "patch": patch,
            "classes": tags[-2:-1] or tags[:1],
            "tags": tags,
            "source": "maxroll",
            "found_date": now_str()[:10],
        })
        if len(out) >= BUILD_TOP_N:
            break
    return out


def scrape_poeninja():
    """官方未公開但穩定的端點：各聯盟前十升華占比（share of ladder）。
    取第一個非 hardcore 聯盟（現行主力軟核聯盟）的前 10 名"""
    r = requests.get(NINJA_STATE_URL, headers={**UA, "Referer": NINJAA_SITE_URL}, timeout=30)
    r.raise_for_status()
    leagues = r.json().get("leagueBuilds") or []
    league = next((l for l in leagues if not l.get("hardcore")), None)
    if not league:
        raise ValueError("no softcore league in build-index-state")
    out = []
    league_url = (league.get("leagueUrl") or "").strip("/")
    for st in (league.get("statistics") or [])[:BUILD_TOP_N]:
        cls = (st.get("class") or "").strip()
        if not cls:
            continue
        # poe.ninja 官方連結格式：/poe2/builds/{leagueUrl}?class={Name}（空格以 + 連接）
        url = f"{NINJAA_SITE_URL}/{league_url}?class={cls.replace(' ', '+')}" if league_url else NINJAA_SITE_URL
        out.append({
            "id": md5_id(f"{league.get('leagueName')}/{cls}"),
            "rank": len(out) + 1,
            "title": cls,
            "share_pct": round(st.get("percentage", 0), 2),
            "trend": st.get("trend", 0),
            "league": league.get("leagueName"),
            "total_chars": league.get("total"),
            "url": url,
            "source": "poeninja",
            "found_date": now_str()[:10],
        })
    return out


def update_builds():
    steps = [
        ("builds_mobalytics", scrape_mobalytics),
        ("builds_maxroll", scrape_maxroll),
        ("builds_poeninja", scrape_poeninja),
    ]
    for name, fn in steps:
        try:
            items = fn()
        except Exception as e:
            log.error("%s failed: %s", name, e)
            continue
        if items:
            save_json(f"{name}.json", items)
            set_meta(name)
            log.info("%s: %d builds", name, len(items))
        else:
            log.warning("%s: parsed 0 items, keeping previous data", name)


# ---------------------------------------------------------------- YouTube

def yt_flat_search(query, n, sort_by_date=False, flat_limit=None):
    if sort_by_date:
        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp=CAI%3D"
    else:
        url = f"ytsearch{n}:{query}"
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True, "socket_timeout": 30}
    if flat_limit:
        opts["playlist_items"] = f"1:{flat_limit}"
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    out = []
    for e in info.get("entries") or []:
        if not isinstance(e, dict):
            continue
        vid = e.get("id")
        if not vid or len(vid) != 11:
            continue
        out.append({
            "video_id": vid,
            "title": e.get("title") or "",
            "channel": e.get("channel") or e.get("uploader") or "",
            "channel_id": e.get("channel_id") or "",
            "view_count": e.get("view_count"),
            "duration": e.get("duration"),
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    return out


YDL_FULL = {"quiet": True, "no_warnings": True, "skip_download": True, "socket_timeout": 30}


def yt_rss_latest(channel_id):
    out = []
    try:
        r = requests.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}", headers=UA, timeout=15)
        r.raise_for_status()
        ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
              "m": "http://search.yahoo.com/mrss/"}
        for e in ET.fromstring(r.content).findall("a:entry", ns):
            vid = e.findtext("yt:videoId", "", ns)
            title = (e.findtext("a:title", "", ns) or "").strip()
            pub = (e.findtext("a:published", "", ns) or "")[:10]
            views = e.find(".//m:statistics", ns)
            out.append((vid, title, pub, int(views.get("views")) if views is not None and views.get("views", "").isdigit() else None))
    except Exception as e:
        log.warning("yt rss %s: %s", channel_id[:12], e)
    return out


def yt_full_info(vid):
    try:
        with yt_dlp.YoutubeDL(YDL_FULL) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
        ud = info.get("upload_date")
        date = f"{ud[:4]}-{ud[4:6]}-{ud[6:8]}" if ud else None
        vc = info.get("view_count")
        return date, vc if isinstance(vc, int) else None
    except Exception as e:
        log.warning("yt full %s: %s", vid, e)
        return None, None


def game_in_title(title):
    t = (title or "").lower().replace("path of exile", "poe").replace("流亡黯道", "poe")
    return any(w in t.replace(" ", "") or w in t for w in ("poe2", "poe 2"))


def within_cutoff(date_str, cutoff):
    try:
        return bool(date_str) and datetime.strptime(date_str, "%Y-%m-%d").date() >= cutoff
    except ValueError:
        return False


def collect_videos(lang):
    if lang == "zh":
        hot_queries, new_queries = ["POE2 攻略", "流亡黯道2 配裝"], ["POE2 攻略"]

        def keep(title):
            return has_cjk(title) and not KANA_RE.search(title)
    elif lang == "ja":
        hot_queries, new_queries = ["PoE2 ビルド", "POE2 攻略"], ["PoE2 ビルド"]

        def keep(title):
            return bool(KANA_RE.search(title))
    else:
        hot_queries, new_queries = ["PoE2 build guide", "Path of Exile 2 build"], ["Path of Exile 2 build"]

        def keep(title):
            return not has_cjk(title)

    pool_hot = []
    seen = set()
    for q in hot_queries:
        for v in yt_flat_search(q, 25):
            k = v["video_id"]
            if k in seen:
                continue
            seen.add(k)
            if not keep(v["title"]):
                continue
            pool_hot.append(v)

    def to_item(v, date, vc):
        return {
            "video_id": v["video_id"],
            "title": v["title"],
            "channel": v["channel"],
            "url": v["url"],
            "views": vc,
            "date": date,
            "lang": lang,
        }

    pool_new = []
    seen2 = set()
    for q in new_queries:
        for v in yt_flat_search(q, 25, sort_by_date=True, flat_limit=NEW_FLAT_LIMIT):
            k = v["video_id"]
            if k in seen2:
                continue
            seen2.add(k)
            if not keep(v["title"]):
                continue
            pool_new.append(v)

    chans = []
    for v in sorted(pool_hot, key=lambda x: -(x.get("view_count") or 0)):
        cid = v.get("channel_id")
        if cid and cid not in chans:
            chans.append(cid)
    for v in pool_new:
        cid = v.get("channel_id")
        if cid and cid not in chans:
            chans.append(cid)
    rss_map = {}
    for cid in chans[:RSS_CHANNEL_CAP]:
        for vid, title, pub, views in yt_rss_latest(cid):
            if pub and len(pub) == 10:
                rss_map[vid] = {"title": title, "date": pub, "views": views}
        time.sleep(0.3)
    log.info("videos [%s]: %d channels rss -> %d videos", lang, min(len(chans), RSS_CHANNEL_CAP), len(rss_map))

    def pick_hot(pool, top_n):
        """賽季遊戲不看全歷史觀看數：只取近 HOT_CUTOFF_DAYS 天上傳的影片，再依觀看數排序"""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=HOT_CUTOFF_DAYS)).date()
        chan_of = {v["video_id"]: v["channel"] for v in pool}
        cands = {v["video_id"]: dict(v) for v in pool}
        # 頻道 RSS 近 30 天上傳也列入候選，避免搜尋結果偏舊時樣本不足
        for vid, info in rss_map.items():
            if vid in cands:
                continue
            if not (within_cutoff(info["date"], cutoff) and keep(info["title"]) and game_in_title(info["title"])):
                continue
            cands[vid] = {"video_id": vid, "title": info["title"], "channel": chan_of.get(vid, ""),
                          "url": f"https://www.youtube.com/watch?v={vid}", "view_count": info["views"]}

        known = [v for v in cands.values() if isinstance(v.get("view_count"), int)]
        unknown = [v for v in cands.values() if not isinstance(v.get("view_count"), int)]
        need = max(0, top_n * 2 - len(known))
        for v in unknown[:need]:
            views = (rss_map.get(v["video_id"]) or {}).get("views")
            if not isinstance(views, int):
                _, views = yt_full_info(v["video_id"])
                time.sleep(0.5)
            if isinstance(views, int):
                v["view_count"] = views
                known.append(v)

        out = []
        for v in sorted(known, key=lambda x: -(x["view_count"] or 0)):
            date = (rss_map.get(v["video_id"]) or {}).get("date")
            if not date:
                date, _ = yt_full_info(v["video_id"])
                time.sleep(0.4)
            if not within_cutoff(date, cutoff):
                continue
            out.append(to_item(v, date, v["view_count"]))
            if len(out) >= top_n:
                break
        return out

    def pick_new(pool, top_n):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=NEW_CUTOFF_DAYS)).date()
        chan_of = {v["video_id"]: v["channel"] for v in pool}
        cands = {}
        for vid, info in rss_map.items():
            try:
                recent = datetime.strptime(info["date"], "%Y-%m-%d").date() >= cutoff
            except ValueError:
                continue
            if not (recent and keep(info["title"]) and game_in_title(info["title"])):
                continue
            cands[vid] = to_item({"video_id": vid, "title": info["title"], "channel": chan_of.get(vid, ""), "url": f"https://www.youtube.com/watch?v={vid}"}, info["date"], info["views"])
        items = sorted(cands.values(), key=lambda x: x["date"] or "", reverse=True)[:top_n]
        if items:
            return items
        log.warning("videos new [%s]: rss empty, falling back to full-extract scan", lang)
        recent, scanned = [], 0
        for v in pool:
            if len(recent) >= top_n or scanned >= 40:
                break
            scanned += 1
            date, vc = yt_full_info(v["video_id"])
            time.sleep(0.4)
            try:
                is_recent = bool(date) and datetime.strptime(date, "%Y-%m-%d").date() >= cutoff
            except ValueError:
                is_recent = False
            if is_recent:
                recent.append(to_item(v, date, vc))
        return sorted(recent, key=lambda x: x["date"] or "", reverse=True)

    hot = pick_hot(pool_hot, 10)
    log.info("videos hot [%s]: %d within %dd", lang, len(hot), HOT_CUTOFF_DAYS)

    log.info("videos new [%s]: %d candidates", lang, len(pool_new))
    new = pick_new(pool_new, 10)

    return hot, new


def update_videos():
    cache = load_json("video_dates.json", {})
    for lang in ("zh", "en", "ja"):
        hot, new = collect_videos(lang)
        for it in [*hot, *new]:
            vid = it["video_id"]
            if it["date"]:
                cache[vid] = it["date"]
            elif vid in cache:
                it["date"] = cache[vid]
        save_json(f"videos_hot_{lang}.json", hot)
        save_json(f"videos_new_{lang}.json", new)
        set_meta(f"videos_hot_{lang}")
        set_meta(f"videos_new_{lang}")
        log.info("videos [%s]: hot=%d new=%d", lang, len(hot), len(new))
    save_json("video_dates.json", cache)


# ---------------------------------------------------------------- 巴哈姆特

BAHA_URL = "https://forum.gamer.com.tw/B.php?bsn=82273"
BAHA_BASE = "https://forum.gamer.com.tw/"


def parse_baha_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for row in soup.select("tr.b-list__row"):
        if row.select_one(".b-list__summary__mark"):
            continue
        main_link = row.select_one("td.b-list__main > a[href*='C.php']")
        if not main_link:
            continue
        title_el = row.select_one(".b-list__main__title")
        brief = row.select_one(".b-list__brief")
        num_el = row.select_one(".b-list__count__number span")
        author_el = row.select_one(".b-list__count__user a")
        time_el = row.select_one(".b-list__time__edittime a")
        items.append({
            "title": title_el.get_text(" ", strip=True) if title_el else "",
            "url": urljoin(BAHA_BASE, main_link.get("href", "")),
            "author": author_el.get_text(strip=True) if author_el else "",
            "replies": num_el.get_text(strip=True) if num_el else "",
            "time": time_el.get_text(strip=True) if time_el else "",
            "snippet": brief.get_text(" ", strip=True)[:200] if brief else "",
        })
    return items


def update_bahamut():
    items = []
    try:
        r = requests.get(BAHA_URL, headers=UA, timeout=20)
        r.raise_for_status()
        rows = parse_baha_rows(r.text)
        seen = set()
        for it in rows:
            k = norm_url(it["url"])
            if k in seen:
                continue
            seen.add(k)
            it["id"] = md5_id(k)
            it["source"] = "forum.gamer.com.tw"
            it["found_date"] = now_str()[:10]
            items.append(it)
            if len(items) >= 10:
                break
    except Exception as e:
        log.error("bahamut failed: %s", e)
    if items:
        save_json("bahamut.json", items)
        set_meta("bahamut")
        log.info("bahamut: %d topics", len(items))
    else:
        log.warning("bahamut: no items parsed, keeping previous data")


# ---------------------------------------------------------------- X 推文

def snowflake_date(tid):
    ts = (int(tid) >> 22) + 1288834974657
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def x_timeline(screen_name):
    try:
        r = requests.get(SYND_URL.format(screen_name), headers=UA, timeout=20)
        r.raise_for_status()
        data = json.loads(r.text.split(SYND_MARKER, 1)[1].split("</script>", 1)[0])
        entries = data["props"]["pageProps"]["timeline"]["entries"]
        out = []
        for e in entries:
            tw = e.get("content", {}).get("tweet", {})
            tid = tw.get("id_str") or ""
            text = (tw.get("full_text") or "").strip()
            likes = tw.get("favorite_count")
            if not tid or not text:
                continue
            out.append({
                "tid": tid,
                "author": screen_name,
                "author_name": (tw.get("user", {}) or {}).get("name") or "",
                "text": text,
                "likes": likes if isinstance(likes, int) else None,
                "date": snowflake_date(tid),
            })
        return out
    except Exception as e:
        log.warning("x timeline %s: %s", screen_name, e)
        return []


def tweet_item(t):
    url = f"https://x.com/{t['author']}/status/{t['tid']}"
    text = t.get("text") or ""
    return {
        "id": md5_id(url),
        "tid": t["tid"],
        "url": url,
        "author": t["author"],
        "author_name": t.get("author_name") or "",
        "text": text,
        "date": t.get("date") or snowflake_date(t["tid"]),
        "likes": t.get("likes"),
        "lang": detect_lang(text),
    }


def update_tweets():
    pool = {}
    for lang in ("zh", "en", "ja"):
        for it in load_json(f"tweets_{lang}.json", []):
            if isinstance(it.get("tid"), str) and it["tid"].isdigit():
                pool[it["tid"]] = it

    added = 0

    def merge(t):
        nonlocal added
        if t["tid"] not in pool:
            added += 1
        pool[t["tid"]] = tweet_item(t)

    with DDGS() as d:
        for qkey, (q, region) in X_SEARCH_QUERIES.items():
            try:
                results = list(d.text(q, region=region, max_results=20))
            except Exception as e:
                log.warning("ddgs x %s %s: %s", qkey, q, e)
                continue
            for r in results:
                m = STATUS_RE.search(r.get("href") or "")
                if not m:
                    continue
                title = html_lib.unescape((r.get("title") or "").strip())
                body = html_lib.unescape((r.get("body") or "").strip())
                if not game_in_title(title + " " + body):
                    continue
                disp, _, rest = title.partition(" on X:")
                text = rest.strip()
                if text.endswith("/ X"):
                    text = text[:-3].strip()
                if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
                    text = text[1:-1].strip()
                if not text:
                    text = body
                text = clean_tweet_text(text)
                if not text:
                    continue
                merge({"tid": m.group(2), "author": m.group(1).lower(),
                       "author_name": disp.strip(), "text": text})
            time.sleep(1.5)

    for sn in X_OFFICIAL_ACCOUNTS:
        for t in x_timeline(sn):
            if game_in_title(t["text"]):
                merge(t)

    buckets = {"zh": [], "en": [], "ja": []}
    for it in pool.values():
        lang = it.get("lang") if it.get("lang") in buckets else detect_lang(it["text"])
        buckets[lang].append(it)
    total = {}
    for lang, items in buckets.items():
        items.sort(key=lambda x: ((x.get("date") or ""), (x.get("likes") or 0)), reverse=True)
        items = items[:TWEET_CAP]
        total[lang] = len(items)
        save_json(f"tweets_{lang}.json", items)
    set_meta("tweets")
    log.info("tweets: +%d -> zh=%d en=%d ja=%d", added, total["zh"], total["en"], total["ja"])


def main():
    started = time.time()
    log.info("=" * 50)
    steps = [
        ("builds", update_builds),
        ("videos", update_videos),
        ("bahamut", update_bahamut),
        ("tweets", update_tweets),
    ]
    failures = []
    for name, fn in steps:
        try:
            fn()
        except Exception as e:
            log.exception("%s crashed: %s", name, e)
            failures.append(name)
    set_meta("_last_run")
    log.info("done in %.1fs%s", time.time() - started, f" | FAILED: {failures}" if failures else "")


if __name__ == "__main__":
    main()
