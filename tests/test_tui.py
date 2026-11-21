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


class FeatureTests(unittest.TestCase):
    """The test block on Training, `m` and `x` there, the Seeds field, the `e` prompt's test split and the replay."""

    SMALL = {"iterations": 2, "population": 4, "episodes_per_candidate": 1}

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp()
        cls.base = tempfile.mkdtemp()
        cls.old_prefs, tui.PREFS = tui.PREFS, os.path.join(cls.home, "tui.json")
        cls.app = tui.App(base=cls.base, colour=True, lang="en", scout=False)
        res = cls.app.jobs.start_train({"method": "cem", **cls.SMALL, "eval_every": 1})
        assert res["ok"], res
        cls.train_id = res["run"]
        RenderTests.wait(cls.app)
        assert cls.app.jobs.start("reconcile", "dev", limit=2)["ok"]
        RenderTests.wait(cls.app)
        cls.app._runs_at = 0

    @classmethod
    def tearDownClass(cls):
        tui.PREFS = cls.old_prefs
        shutil.rmtree(cls.home, ignore_errors=True)
        shutil.rmtree(cls.base, ignore_errors=True)

    def setUp(self):
        self.app.lang, self.app.replay, self.app.msg, self.app.group_ids = "en", None, "", None
        self.app.train_id, self.app._runs_at = self.train_id, 0

    def text(self, w=120, h=40):
        lines = self.app.render(w, h)
        self.assertLessEqual(len(lines), h)
        self.assertTrue(all(tui.vlen(line) <= w for line in lines), (w, h))
        return tui.ESC.sub("", "\n".join(lines))

    def sizes(self):
        for lang in ("en", "ru"):
            self.app.lang = lang
            for w, h in ((80, 24), (120, 40)):
                yield lang, w, h, self.text(w, h)
        self.app.lang = "en"

    def test_training_shows_the_test_block_in_both_languages_and_sizes(self):
        self.assertIn("auditor", tui.read_run(self.train_id, self.base).get("test") or {}, "the backend measured the test")
        self.app.tab = 1
        for lang, w, h, text in self.sizes():
            self.assertIn("Test (20 fresh episodes)" if lang == "en" else "Тест (20 новых эпизодов)", text, (lang, w))
            self.assertIn("Trained auditor" if lang == "en" else "Обученный аудитор", text, (lang, w))
            self.assertIn("Reconciler" if lang == "en" else "Сверщик", text, (lang, w))
            self.assertRegex(text, r"\d+/\d+", "found / issues per error type")
            self.assertIn("%", text, (lang, w, "the progress bar still fits"))
        self.assertIn("m evaluate on test", self.text())

    def test_training_shows_a_spinner_while_the_test_runs(self):
        r = dict(tui.read_run(self.train_id, self.base))
        r.pop("test", None)
        r["status_note"] = "testing"
        self.app._run_cache[self.train_id] = (time.monotonic() + 1e6, r)   # as run.json reads while testing
        try:
            self.app.tab = 1
            for lang, w, h, text in self.sizes():
                self.assertIn("measuring on the test set" if lang == "en" else "замер на тестовой выборке", text, (lang, w))
        finally:
            self.app._run_cache.pop(self.train_id, None)

    def test_m_evaluates_the_trained_model_on_the_test_split(self):
        self.app.tab = 1
        self.app.handle("m")
        self.assertEqual(tui.TABS[self.app.tab], "runs")
        RenderTests.wait(self.app)
        self.app._runs_at = 0
        r = self.app.runs()[self.app.sel]
        self.assertEqual((r["model_run"], r["split"], r["agent"]), (self.train_id, "test", "auditor-cem"))
        for lang, w, h, text in self.sizes():
            self.assertIn(("Evaluation · Auditor · CEM" if lang == "en" else "Оценка · Аудитор · CEM"), text, (lang, w))
            self.assertIn(self.train_id[:30], text, (lang, w))
        text = self.text()
        self.assertIn("found / missed by error type", text)
        self.assertIn("reward by kind of episode", text)
        self.assertIn("false findings", text)

    def test_x_exports_the_report(self):
        self.app.tab = 1
        self.app.handle("x")
        path = os.path.join(self.base, self.train_id, "report.md")
        self.assertTrue(os.path.isfile(path))
        self.assertIn("report.md", self.app.msg)
        self.assertIn("Report saved", self.text())

    def test_e_prompt_asks_for_the_split(self):
        self.app.tab = 2
        self.app.handle("e")
        self.app.handle("1")
        self.assertEqual(self.app.ask_split, "reconcile")
        self.assertIn("20 fresh test episodes", self.text(80, 24))
        self.app.handle("t")
        self.assertIsNone(self.app.ask_split)
        RenderTests.wait(self.app)
        self.app._runs_at = 0
        r = self.app.runs()[0]
        self.assertEqual((r["agent"], r["split"], r["episodes"]), ("reconcile", "test", 20))
        self.app.handle("e")
        self.app.handle("2")
        self.app.handle("esc")
        self.assertFalse(self.app.jobs.busy(), "Esc cancels")

    def test_replay_shows_the_steps_and_esc_returns(self):
        self.app.tab = 2
        self.app._runs_at = 0
        self.app.sel = next(i for i, r in enumerate(self.app.runs()) if r["kind"] == "evaluation" and r["split"] == "dev")
        self.app.handle("enter")
        self.assertIsNotNone(self.app.replay)
        for lang, w, h, text in self.sizes():
            self.assertIn("Replay" if lang == "en" else "Повтор", text)
            self.assertIn("list_records", text, (lang, w))
            self.assertIn("[1]", text)
        self.app.handle("right")
        self.assertEqual(self.app.replay["ep"], 1)
        text = self.text(80, 24)
        self.assertIn("[2]", text)
        for _ in range(40):
            self.app.handle("down")
        self.assertIn("submit", self.text(80, 24), "scrolled to the last step")
        self.app.handle("esc")
        self.assertIsNone(self.app.replay)
        self.app.handle("enter")
        self.app.handle("backspace")
        self.assertIsNone(self.app.replay)
        self.assertEqual(tui.parse_keys("\x7f"), ["backspace"])

    def test_seeds_3_starts_a_group(self):
        old = dict(tui.SIZES["fast"])
        tui.SIZES["fast"] = dict(self.SMALL)
        try:
            self.app.tab, self.app.field = 0, 3
            self.app.pick.update(size=0, seeds=0)
            self.app.handle("right")
            self.assertEqual(self.app.pick["seeds"], 1)
            self.assertIn("compare the seeds", self.text())
            self.app.handle("enter")
            self.assertEqual(tui.TABS[self.app.tab], "train")
            self.assertTrue(self.app.train_id.endswith("-s1"))
            RenderTests.wait(self.app)
        finally:
            tui.SIZES["fast"] = old
        self.app._runs_at = 0
        group = [r for r in self.app.runs() if r.get("group")]
        self.assertEqual(sorted(r["seed"] for r in group), [1, 2, 3])
        self.assertEqual(len({r["group"] for r in group}), 1)
        self.app.tab = 2
        self.app.sel = self.app.runs().index(group[0])
        for lang, w, h, text in self.sizes():
            self.assertIn("seeds of the group" if lang == "en" else "сиды группы", text, (lang, w))
        self.app.pick["seeds"] = 0


if __name__ == "__main__":
    unittest.main()
