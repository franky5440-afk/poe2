"""
契約：collect_videos() 該語言的頻道 RSS 一部影片都拿不到（rss_map 為空）時，
視為「YouTube 擋下雲端 IP、爬蟲失敗」，hot/new 一律回傳空 list，
交由 update_videos() 既有的「0 筆保留前一日資料」保護處理；
不可把搜尋池裡沒日期的老片當熱門遞補塞滿 10 部覆寫線上資料。

背景：09/08、09/09 兩天雲端 RSS 全回 404/500（44 頻道 → 0 部），
zh 熱門候選全無日期 → pick_hot_videos() 忠實用觀看數最高的老片遞補湊滿 10 部，
線上 videos_hot_zh.json 被 2023～2026/06 的舊片整批覆寫。
「遞補湊滿」規則本身保留（那是淡季真的沒新片時的行為），
本測試釘死的是：RSS 0 部＝爬蟲壞掉，不是內容淡季，不得落地。

RSS 正常（有拿到影片）時行為不變，仍照 pick_hot_videos / pick_new_videos 產出。

跑法：./venv/bin/python -m unittest tests.test_collect_videos_rss_blocked -v
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scraper  # noqa: E402


def _video(vid, views, channel="惡魔貓"):
    return {"video_id": vid, "title": f"POE2 攻略 {vid}", "channel": channel,
            "channel_id": f"UC{vid}", "view_count": views,
            "url": f"https://www.youtube.com/watch?v={vid}"}


class CollectVideosRssBlockedTest(unittest.TestCase):
    def setUp(self):
        # 搜尋池照常拿得到（yt-dlp flat search 沒被擋），但全都沒日期——
        # 這正是 09/08 線上的狀態
        self.pool = [_video(f"v{i}", views=100000 - i) for i in range(12)]
        for name, ret in (("yt_flat_search", self.pool), ("yt_rss_latest", [])):
            p = mock.patch.object(scraper, name, return_value=ret)
            p.start()
            self.addCleanup(p.stop)
        # 全網路查日期也一律失敗
        p = mock.patch.object(scraper, "yt_full_info", return_value=(None, None))
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(scraper.time, "sleep", return_value=None)
        p.start()
        self.addCleanup(p.stop)

    def test_rss_zero_videos_returns_empty_hot_and_new(self):
        hot, new = scraper.collect_videos("zh", {})

        self.assertEqual(hot, [], "RSS 0 部＝爬蟲失敗，hot 必須回空 list 讓 update_videos 保留舊資料，"
                                  "不可拿無日期老片遞補湊滿")
        self.assertEqual(new, [], "RSS 0 部＝爬蟲失敗，new 必須回空 list")

    def test_rss_working_still_picks_normally(self):
        rss_rows = [(v["video_id"], v["title"], "2026-09-01", v["view_count"], v["channel"])
                    for v in self.pool]
        with mock.patch.object(scraper, "yt_rss_latest", return_value=rss_rows):
            hot, new = scraper.collect_videos("zh", {})

        self.assertEqual(len(hot), 10, "RSS 正常時 hot 照舊產出 10 部")
        self.assertEqual(len(new), 10, "RSS 正常時 new 照舊產出 10 部")


if __name__ == "__main__":
    unittest.main()
