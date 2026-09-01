"""
契約：update_videos() 對 hot/new 各自獨立比照 update_builds() / update_bahamut()
的既有慣例——某語言某分類這次抓到 0 筆時，保留前一日資料、不覆寫、不更新
meta 時間戳；抓到非 0 筆才覆寫。

背景：09/01 線上版 YouTube 反機器人驗證擋下雲端 IP，zh/en/ja 的 hot/new
六個檔案被 0 筆直接覆寫成空檔，使用者端就看到「影片區都沒資料」。
scraper.py 的 update_builds()/update_bahamut() 都已有這個保護，唯獨
update_videos() 沒有——本測試把這個缺口釘死成契約。

跑法：./venv/bin/python -m unittest tests.test_update_videos -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scraper  # noqa: E402


def _item(vid, tag):
    return {"video_id": vid, "title": f"video-{tag}", "date": "2026-08-30", "views": 100}


class UpdateVideosKeepsPreviousOnEmptyTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.data_dir = Path(self._tmpdir.name)
        self.data_patch = mock.patch.object(scraper, "DATA", self.data_dir)
        self.data_patch.start()
        self.addCleanup(self.data_patch.stop)

        # zh 的舊資料（模擬前一日還抓得到的正常快照）
        self.old_hot_zh = [_item("old_hot_zh", "old-hot-zh")]
        self.old_new_zh = [_item("old_new_zh", "old-new-zh")]
        (self.data_dir / "videos_hot_zh.json").write_text(
            json.dumps(self.old_hot_zh), encoding="utf-8")
        (self.data_dir / "videos_new_zh.json").write_text(
            json.dumps(self.old_new_zh), encoding="utf-8")
        (self.data_dir / "meta.json").write_text(json.dumps({
            "videos_hot_zh": "2026-08-30 08:09",
            "videos_new_zh": "2026-08-30 08:09",
        }), encoding="utf-8")

        # en/ja 完全沒有舊檔（模擬正常這次應該落地新資料）
        self.new_hot_en = [_item("new_hot_en", "new-hot-en")]
        self.new_new_en = [_item("new_new_en", "new-new-en")]
        self.new_hot_ja = [_item("new_hot_ja", "new-hot-ja")]
        self.new_new_ja = [_item("new_new_ja", "new-new-ja")]

        def fake_collect_videos(lang):
            # zh 模擬這次 YouTube 擋下、兩區都拿不到任何影片
            if lang == "zh":
                return [], []
            if lang == "en":
                return self.new_hot_en, self.new_new_en
            return self.new_hot_ja, self.new_new_ja

        self.collect_patch = mock.patch.object(
            scraper, "collect_videos", side_effect=fake_collect_videos)
        self.collect_patch.start()
        self.addCleanup(self.collect_patch.stop)

    def _read(self, name):
        return json.loads((self.data_dir / name).read_text(encoding="utf-8"))

    def test_zh_zero_result_keeps_previous_data_and_meta(self):
        scraper.update_videos()

        self.assertEqual(self._read("videos_hot_zh.json"), self.old_hot_zh,
                          "zh 這次抓到 0 筆，videos_hot_zh.json 必須保留前一日資料，不可覆寫成空檔")
        self.assertEqual(self._read("videos_new_zh.json"), self.old_new_zh,
                          "zh 這次抓到 0 筆，videos_new_zh.json 必須保留前一日資料，不可覆寫成空檔")

        meta = self._read("meta.json")
        self.assertEqual(meta["videos_hot_zh"], "2026-08-30 08:09",
                          "zh 這次抓到 0 筆，videos_hot_zh 的 meta 時間戳不可更新")
        self.assertEqual(meta["videos_new_zh"], "2026-08-30 08:09",
                          "zh 這次抓到 0 筆，videos_new_zh 的 meta 時間戳不可更新")

    def test_en_ja_nonzero_result_still_overwrites_normally(self):
        scraper.update_videos()

        self.assertEqual(self._read("videos_hot_en.json"), self.new_hot_en)
        self.assertEqual(self._read("videos_new_en.json"), self.new_new_en)
        self.assertEqual(self._read("videos_hot_ja.json"), self.new_hot_ja)
        self.assertEqual(self._read("videos_new_ja.json"), self.new_new_ja)

        meta = self._read("meta.json")
        for key in ("videos_hot_en", "videos_new_en", "videos_hot_ja", "videos_new_ja"):
            self.assertIn(key, meta, f"{key} 抓到非 0 筆時必須有 meta 時間戳")


if __name__ == "__main__":
    unittest.main()
