"""The terminal UI (auditgym.tui): keys, drawing helpers, and every section rendered at common terminal sizes."""
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from auditgym import tui  # noqa: E402


class HelperTests(unittest.TestCase):
    def test_keys_typed_together_are_all_read(self):
        self.assertEqual(tui.parse_keys("\x1b[B\x1b[B\x1b[D\r\tq"), ["down", "down", "left", "enter", "tab", "q"])
        self.assertEqual(tui.parse_keys("\x1b[1;5C1"), ["1"], "unknown escape sequences are skipped")
        self.assertEqual(tui.parse_keys("\x1b"), ["esc"])

    def test_width_ignores_colour_codes_and_clip_keeps_them_closed(self):
        st = tui.Style(True)
        s = st.POS + "+0.50" + st.R + " done"
        self.assertEqual(tui.vlen(s), 10)
        self.assertEqual(tui.vlen(tui.clip(s, 3)), 3)
        self.assertTrue(tui.clip(s, 3).endswith("\x1b[0m"))

    def test_chart_has_the_requested_size_and_draws_points(self):
        rows = tui.chart([([(0, -1.0), (9, 1.0)], "dev", False)], 20, 5, 9)
        self.assertEqual((len(rows), {len(r) for r in rows}), (5, {20}))
        self.assertTrue(any(c != " " for r in rows for c, _ in r))
        self.assertEqual(rows[0][-1][1], "dev", "the top right cell holds the last point")

    def test_wordmark_and_russian_plural(self):
        self.assertEqual(len(tui.wordmark()), 4)
        self.assertEqual([tui.cores(n, "ru") for n in (1, 4, 5, 12, 22)], ["1 ядро", "4 ядра", "5 ядер", "12 ядер", "22 ядра"])


class RenderTests(unittest.TestCase):
    """A real (tiny) training and evaluation, then every section drawn in both languages."""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp()
        cls.base = tempfile.mkdtemp()
        cls.old_prefs, tui.PREFS = tui.PREFS, os.path.join(cls.home, "tui.json")  # never touch the real settings
        cls.app = tui.App(base=cls.base, colour=True, lang="en", scout=False)
        res = cls.app.jobs.start_train({"method": "cem", "iterations": 2, "population": 4, "episodes_per_candidate": 1, "eval_every": 1})
        assert res["ok"], res
        cls.wait(cls.app)
        assert cls.app.jobs.start("reconcile", "dev", limit=1)["ok"]
        cls.wait(cls.app)
        cls.app._runs_at = 0

    @staticmethod
    def wait(app):
        for _ in range(600):
            if not app.jobs.busy():
                return
            time.sleep(0.1)
        raise AssertionError("run did not finish")

    @classmethod
    def tearDownClass(cls):
        tui.PREFS = cls.old_prefs
        shutil.rmtree(cls.home, ignore_errors=True)
        shutil.rmtree(cls.base, ignore_errors=True)

    def test_every_section_fits_the_terminal_in_both_languages(self):
        for lang in ("en", "ru"):
            self.app.lang = lang
            for w, h in ((80, 24), (120, 40)):
                for i, name in enumerate(tui.TABS):
                    self.app.tab = i
                    lines = self.app.render(w, h)
                    self.assertLessEqual(len(lines), h, (lang, w, name))
                    self.assertTrue(all(tui.vlen(line) <= w for line in lines), (lang, w, name))
        self.app.lang = "en"

    def test_training_view_shows_the_run(self):
        self.app.tab = 1
        text = tui.ESC.sub("", "\n".join(self.app.render(120, 40)))
        self.assertIn("Reward on held-out dev episodes", text)
        self.assertIn("iteration 2/2", text)
        self.assertRegex(text, r"[⠁-⣿]", "the braille chart is drawn")

    def test_runs_list_both_runs_and_keys_move_between_sections(self):
        self.app.tab = 2
        text = tui.ESC.sub("", "\n".join(self.app.render(120, 40)))
        self.assertIn("Training · CEM", text)
        self.assertIn("Evaluation · Reconciler", text)
        self.assertTrue(self.app.handle("4"))
        self.assertEqual(tui.TABS[self.app.tab], "settings")
        self.assertTrue(self.app.handle("right"))
        self.assertEqual(self.app.lang, "ru")
        self.assertTrue(os.path.isfile(tui.PREFS), "the language choice is saved")
        self.app.handle("right")
        self.assertEqual(self.app.lang, "en")
        self.assertFalse(self.app.handle("q"), "q quits when nothing runs")


if __name__ == "__main__":
    unittest.main()
