"""
契約：pick_new_videos() 一律回傳「候選池裡最近的 top_n 部影片」——當近期（原 21 天窗）
候選不足 top_n 筆時，也要用更舊的候選遞補湊滿，而不是任由窗口卡住只回傳不足額的筆數。
語意：Frank 要求「最新 tab 也要保持 10 個，因為它的意思就是『最近』的 10 部影片，
使用者才不會看到 tab 裡影片數量忽多忽少而覺得錯亂」。

背景：原本 collect_videos() 內的 pick_new() 只要 rss 候選非空就直接回傳，
不論筆數夠不夠 top_n；只有候選「完全是 0 筆」才會觸發 full-extract 掃描補齊。
本測試把「不足額也要遞補湊滿」這個契約釘死。

跑法：./venv/bin/python -m unittest tests.test_pick_new_videos -v
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


def _video(vid, channel="ch"):
    return {
        "video_id": vid, "title": f"POE2 build {vid}", "channel": channel,
        "channel_id": channel, "view_count": 10, "url": f"https://youtu.be/{vid}",
    }


def _to_item(v, date, vc):
    return {"video_id": v["video_id"], "title": v["title"], "channel": v["channel"],
            "url": v["url"], "views": vc, "date": date, "lang": "test"}


def _keep(_title):
    return True


class PickNewVideosBackfillTest(unittest.TestCase):
    def test_enough_within_window_no_backfill_needed(self):
        pool = [_video(f"v{i}") for i in range(12)]
        rss_map = {v["video_id"]: {"title": v["title"], "date": _date(i), "views": 10}
                   for i, v in enumerate(pool)}

        with mock.patch.object(scraper, "yt_full_info", side_effect=AssertionError("不應呼叫")):
            out = scraper.pick_new_videos(pool, rss_map, _keep, _to_item, top_n=10)

        self.assertEqual(len(out), 10)
        self.assertEqual([it["video_id"] for it in out], [f"v{i}" for i in range(10)],
                          "候選足夠時應直接依日期新到舊排序取前 10")

    def test_backfills_with_older_candidates_when_recent_window_short(self):
        # 只有 3 部落在近期（21 天內對應的模擬窗），其餘 9 部較舊，仍應遞補湊滿 10
        recent = [_video(f"r{i}") for i in range(3)]
        older = [_video(f"o{i}") for i in range(9)]
        pool = recent + older
        rss_map = {}
        for i, v in enumerate(recent):
            rss_map[v["video_id"]] = {"title": v["title"], "date": _date(i), "views": 10}
        for i, v in enumerate(older):
            rss_map[v["video_id"]] = {"title": v["title"], "date": _date(40 + i), "views": 10}

        with mock.patch.object(scraper, "yt_full_info", side_effect=AssertionError("不應呼叫")):
            out = scraper.pick_new_videos(pool, rss_map, _keep, _to_item, top_n=10)

        self.assertEqual(len(out), 10, "近期候選只有 3 筆時，應該用較舊的候選遞補湊滿 10 筆")
        self.assertEqual([it["video_id"] for it in out],
                          [f"r{i}" for i in range(3)] + [f"o{i}" for i in range(7)],
                          "遞補後仍要整體依日期新到舊排序")

    def test_falls_back_to_full_extract_when_rss_missing_dates(self):
        # rss_map 完全沒有候選（模擬 RSS 抓不到資料），要改用 pool 逐一查詳細資訊補齊
        pool = [_video(f"p{i}") for i in range(15)]
        rss_map = {}

        def fake_full_info(vid):
            idx = int(vid[1:])
            return _date(idx), 10

        with mock.patch.object(scraper, "yt_full_info", side_effect=fake_full_info):
            out = scraper.pick_new_videos(pool, rss_map, _keep, _to_item, top_n=10)

        self.assertEqual(len(out), 10, "rss 完全沒候選時，應改用 full-extract 掃描湊滿 10 筆")
        self.assertEqual([it["video_id"] for it in out], [f"p{i}" for i in range(10)])

    def test_returns_fewer_than_top_n_when_total_candidates_short(self):
        pool = [_video(f"v{i}") for i in range(5)]
        rss_map = {v["video_id"]: {"title": v["title"], "date": _date(i), "views": 10}
                   for i, v in enumerate(pool)}

        with mock.patch.object(scraper, "yt_full_info", side_effect=AssertionError("不應呼叫")):
            out = scraper.pick_new_videos(pool, rss_map, _keep, _to_item, top_n=10)

        self.assertEqual(len(out), 5, "候選總數不足 top_n 時，不該無中生有湊出不存在的資料")


if __name__ == "__main__":
    unittest.main()
