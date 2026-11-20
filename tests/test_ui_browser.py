"""End-to-end UI test in a real browser: the whole player journey, by mouse and by keyboard.

Needs Playwright (a dev-only tool, never imported by src/). Skipped when it is not installed, unless
AUDITGYM_E2E=1, which CI sets so that a missing browser fails loudly instead of skipping.
Optional: CHROME_PATH points to a Chrome/Chromium binary instead of Playwright's bundled one.
"""
import os
import threading
import unittest

from auditgym.cli import ui_extra_files
from auditgym.env.adapters import make_http_server

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - depends on the machine
    sync_playwright = None

REQUIRED = os.environ.get("AUDITGYM_E2E") == "1"


@unittest.skipIf(sync_playwright is None and not REQUIRED, "Playwright not installed (dev-only E2E test)")
class TestUIBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sync_playwright is None:
            raise AssertionError("AUDITGYM_E2E=1 but Playwright is not installed")
        cls.srv, cls.env = make_http_server(0, "open", ui=True, extra_files=ui_extra_files())
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        path = os.environ.get("CHROME_PATH")
        cls.browser = cls.pw.chromium.launch(**({"executable_path": path} if path else {}))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.env.close()

    def page(self, width=1440, height=900):
        ctx = self.browser.new_context(viewport={"width": width, "height": height})
        pg = ctx.new_page()
        pg.set_default_timeout(10000)
        errors, external = [], []
        pg.on("console", lambda m: errors.append(f"{m.text} @ {m.location.get('url', '')}") if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("request", lambda r: external.append(r.url) if not r.url.startswith((self.base, "data:")) else None)
        self.addCleanup(ctx.close)
        return pg, errors, external

    def test_full_journey_with_the_mouse(self):
        pg, errors, external = self.page()
        pg.goto(self.base + "/")
        pg.wait_for_selector("#ep-rows tr")
        self.assertEqual(pg.locator("#ep-rows tr").count(), 10)
        self.assertIn("RECONCILE", pg.inner_text("#tape"))  # market tape is built from report.json
        pg.click("[data-split=dev]")
        pg.wait_for_function("document.querySelector('#ep-rows td')?.textContent.startsWith('dev-')")
        pg.click("[data-split=train]")
        pg.wait_for_function("document.querySelector('#ep-rows td')?.textContent.startsWith('train-')")
        pg.click("#ep-rows tr:nth-child(3) button")
        pg.wait_for_selector("#play:not(.hidden)")
        self.assertRegex(pg.inner_text("#ep-sub"), r"ep_[0-9a-f]{16}")
        self.assertIn("100", pg.inner_text("#budget-txt"))
        # browse: one page = one step
        pg.click("#table-tabs button:nth-child(2)")
        pg.wait_for_selector("#records tbody tr")
        self.assertIn("99", pg.inner_text("#budget-n"))
        pg.click("#records tbody tr:nth-child(2)")
        self.assertTrue(pg.inner_text("#rec-id").startswith("invoices /"))
        # document costs a step and renders
        pg.click("#open-doc")
        pg.wait_for_selector("#rec-doc .doc pre")
        self.assertIn("98", pg.inner_text("#budget-n"))
        # calculator
        pg.fill("#calc-in", "12400.00 * (491.35 - 488.00)")
        pg.press("#calc-in", "Enter")
        pg.wait_for_function("document.querySelector('#calc-out').textContent.includes('41540')")
        # build a finding, with validation of a bad amount first
        pg.click("#add-aff")
        pg.click("#add-ev")
        pg.fill("#f-amt", "12.5")
        self.assertEqual(pg.get_attribute("#f-amt", "aria-invalid"), "true")
        pg.click("#f-add")
        self.assertEqual(pg.locator("#f-list li:not(.empty)").count(), 0)
        pg.fill("#f-amt", "4386160")
        self.assertEqual(pg.get_attribute("#f-amt", "aria-invalid"), "false")
        pg.click("#f-add")
        self.assertEqual(pg.locator("#f-list li:not(.empty)").count(), 1)
        self.assertEqual(pg.inner_text("#find-count").strip(), "1 / 30")
        # remove and re-add to prove the × button works
        pg.click("#f-list li button")
        self.assertEqual(pg.locator("#f-list li:not(.empty)").count(), 0)
        pg.click("#add-aff")
        pg.fill("#f-amt", "4386160")
        pg.click("#f-add")
        # submit: cancel first, then confirm in the accessible dialog
        pg.click("#submit")
        pg.wait_for_selector("#confirm[open]")
        pg.click("#confirm-no")
        self.assertFalse(pg.is_visible("#result"))
        pg.click("#submit")
        pg.click("#confirm-yes")
        pg.wait_for_selector("#result:not(.hidden)")
        big = pg.inner_text("#r-big")
        self.assertRegex(big, r"^[+−]?\d\.\d{3}$")
        self.assertEqual(pg.locator("#r-list .badge").count(), 1)
        self.assertEqual(pg.locator("#r-tiles .card").count(), 6)
        pg.click("#again")
        pg.wait_for_selector("#start:not(.hidden)")
        self.assertEqual(errors, [], errors)
        self.assertEqual(external, [], "UI must work offline")

    def test_keyboard_only_journey(self):
        pg, errors, _ = self.page()
        pg.goto(self.base + "/")
        pg.wait_for_selector("#ep-rows tr")
        pg.keyboard.press("Tab")
        self.assertEqual(pg.evaluate("document.activeElement.className"), "skip")
        pg.focus("[data-split=train]")
        pg.keyboard.press("ArrowRight")
        pg.wait_for_function("document.querySelector('[data-split=dev]').getAttribute('aria-selected') === 'true'")
        self.assertEqual(pg.evaluate("document.activeElement.dataset.split"), "dev")
        pg.keyboard.press("ArrowLeft")
        pg.wait_for_function("document.querySelector('#ep-rows td')?.textContent.startsWith('train-')")
        pg.focus("#ep-rows tr:nth-child(2) button")
        pg.keyboard.press("Enter")
        pg.wait_for_selector("#play:not(.hidden)")
        self.assertEqual(pg.evaluate("document.activeElement.id"), "ep-title")
        pg.focus("#table-tabs button:nth-child(1)")
        pg.keyboard.press("Enter")
        pg.wait_for_selector("#records tbody tr")
        pg.focus("#records tbody tr:nth-child(1)")
        pg.keyboard.press("ArrowDown")
        pg.keyboard.press("Enter")
        self.assertTrue(pg.inner_text("#rec-id").startswith("ledger /"))
        pg.focus("#submit")
        pg.keyboard.press("Enter")
        pg.wait_for_selector("#confirm[open]")
        pg.keyboard.press("Escape")
        pg.wait_for_function("!document.querySelector('#confirm').open")
        self.assertEqual(pg.evaluate("document.activeElement.id"), "submit")
        self.assertEqual(errors, [], errors)

    def test_deep_link_and_report_page(self):
        pg, errors, external = self.page()
        pg.goto(self.base + "/?ep=train-3&table=invoices")
        pg.wait_for_selector("#records tbody tr")
        self.assertTrue(pg.is_visible("#play"))
        # the hero's "check it yourself" link opens train-03 with the cited invoice selected, at no step cost
        pg.goto(self.base + "/")
        pg.click(".case-open")
        pg.wait_for_selector("#records tr.sel")
        self.assertEqual(pg.get_attribute("#records tr.sel", "data-id"), "INV-S3-3287")
        self.assertIn("99", pg.inner_text("#budget-n"))
        pg.goto(self.base + "/report.html")
        pg.wait_for_selector("#areas .card")
        self.assertEqual(pg.locator("#areas .card").count(), 5)
        self.assertEqual(pg.locator("#pol tbody tr").count(), 4)
        self.assertGreater(pg.locator("#steps li").count(), 0)
        before = pg.inner_text("#obs")
        pg.click("#b-next")
        self.assertNotEqual(pg.inner_text("#obs"), before)
        self.assertEqual(errors, [], errors)
        self.assertEqual(external, [], "report must work offline")

    def test_layouts_do_not_overflow(self):
        for width in (390, 768, 1280, 1920):
            pg, errors, _ = self.page(width=width, height=900)
            for path in ("/", "/report.html"):
                pg.goto(self.base + path)
                pg.wait_for_load_state("networkidle")
                over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                self.assertLessEqual(over, 0, f"horizontal overflow {over}px at {width}px on {path}")
            self.assertEqual(errors, [], errors)

    def test_fonts_actually_load(self):
        pg, _, _ = self.page()
        pg.goto(self.base + "/")
        pg.wait_for_selector("#ep-rows tr")
        loaded = pg.evaluate("document.fonts.ready.then(() => [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family))")
        for fam in ("Inter", "Source Serif 4", "JetBrains Mono"):
            self.assertTrue(any(fam in f for f in loaded), f"{fam} not loaded: {loaded}")


if __name__ == "__main__":
    unittest.main()
