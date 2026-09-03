"""
契約：pick_hot_videos() 熱門影片候選在 HOT_CUTOFF_DAYS（30 天）窗內不足 top_n 筆時，
要用窗外（較舊）但觀看數較高的影片依序遞補湊滿，而不是直接回傳不足 top_n 筆。
窗內候選一律優先於窗外遞補候選，不因觀看數高就插隊。

背景：Frank 要求「影片區的兩個 tab 保持有 10 個，熱門影片超出 30 天窗就用舊一點的遞補」。
原本 collect_videos() 內的 pick_hot() 是嚴格 cutoff，窗外一律跳過，
候選不足時就會回傳少於 10 筆。本測試把「遞補湊滿」這個契約釘死。

跑法：./venv/bin/python -m unittest tests.test_pick_hot_videos -v
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scraper  # noqa: E402


def _date(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _video(vid, views, channel="ch"):
    return {
        "video_id": vid, "title": f"POE2 build {vid}", "channel": channel,
        "channel_id": channel, "view_count": views, "url": f"https://youtu.be/{vid}",
    }


def _to_item(v, date, vc):
    return {"video_id": v["video_id"], "title": v["title"], "channel": v["channel"],
            "url": v["url"], "views": vc, "date": date, "lang": "test"}


def _keep(_title):
    return True


class PickHotVideosBackfillTest(unittest.TestCase):
    def setUp(self):
        # yt_full_info 只在候選缺 date/views 時才會被呼叫；測試資料一律靠 rss_map 補齊，
        # 這裡 patch 起來純粹避免不小心打到真網路。
        self.yt_full_info_patch = mock.patch.object(
            scraper, "yt_full_info", side_effect=AssertionError("不應呼叫 yt_full_info"))
        self.yt_full_info_patch.start()
        self.addCleanup(self.yt_full_info_patch.stop)

    def test_enough_within_cutoff_no_backfill_needed(self):
        pool = [_video(f"in{i}", views=100 - i) for i in range(12)]
        rss_map = {v["video_id"]: {"title": v["title"], "date": _date(20), "views": v["view_count"]}
                   for v in pool}

        out = scraper.pick_hot_videos(pool, rss_map, _keep, _to_item, top_n=10)

        self.assertEqual(len(out), 10)
        self.assertEqual([it["video_id"] for it in out],
                          [f"in{i}" for i in range(10)],
                          "候選足夠時應直接依觀看數排序取前 10，不需要動用窗外資料")

    def test_backfills_with_older_videos_when_short(self):
        within = [_video(f"in{i}", views=50 - i) for i in range(4)]
        outside = [_video(f"out{i}", views=999 - i) for i in range(8)]  # 觀看數故意設得很高
        pool = within + outside
        rss_map = {}
        for v in within:
            rss_map[v["video_id"]] = {"title": v["title"], "date": _date(20), "views": v["view_count"]}
        for v in outside:
            rss_map[v["video_id"]] = {"title": v["title"], "date": _date(45), "views": v["view_count"]}

        out = scraper.pick_hot_videos(pool, rss_map, _keep, _to_item, top_n=10)

        self.assertEqual(len(out), 10, "窗內只有 4 筆時，應該用窗外影片遞補湊滿 10 筆")
        self.assertEqual([it["video_id"] for it in out[:4]], [f"in{i}" for i in range(4)],
                          "窗內候選必須全部排在前面，不因窗外觀看數更高就插隊")
        self.assertEqual({it["video_id"] for it in out[4:]},
                          {f"out{i}" for i in range(6)},
                          "窗外遞補應依觀看數由高到低取到湊滿 top_n 為止")

    def test_returns_fewer_than_top_n_when_total_candidates_short(self):
        pool = [_video(f"v{i}", views=10 - i) for i in range(5)]
        rss_map = {v["video_id"]: {"title": v["title"], "date": _date(10), "views": v["view_count"]}
                   for v in pool}

        out = scraper.pick_hot_videos(pool, rss_map, _keep, _to_item, top_n=10)

        self.assertEqual(len(out), 5, "候選總數不足 top_n 時，不該無中生有湊出不存在的資料")


if __name__ == "__main__":
    unittest.main()
