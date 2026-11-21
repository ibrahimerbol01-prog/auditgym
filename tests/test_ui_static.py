"""UI integrity checks that need no browser (standard library only).

They catch the small things that embarrass a demo: a missing font, a dead element id, an unlabeled
input, a link to the internet in an offline tool, colours that fail WCAG contrast.
"""
import http.client
import json
import os
import re
import threading
import unittest

from auditgym.cli import ui_extra_files
from auditgym.env.adapters import STATIC_DIR, STATIC_WHITELIST, make_http_server

HTML = ("index.html", "play.html", "report.html", "runs.html", "train.html")
JS = {"index.html": "home.js", "play.html": "app.js", "report.html": "report.js", "runs.html": "runs.js", "train.html": "train.js"}


def read(name):
    with open(os.path.join(STATIC_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def css_vars():
    root = re.search(r":root\{(.*?)\}", read("style.css"), re.S).group(1)
    return dict(re.findall(r"--([\w-]+):(#[0-9a-fA-F]{6})", root))


def contrast(a, b):
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class Server:
    def __enter__(self):
        self.srv, self.env = make_http_server(0, "open", ui=True, extra_files=ui_extra_files())
        self.port = self.srv.server_address[1]
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()
        return self

    def get(self, path, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", path, headers={"Host": f"127.0.0.1:{self.port}", **(headers or {})})
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, r.getheader("Content-Type") or "", body

    def __exit__(self, *a):
        self.srv.shutdown()
        self.srv.server_close()
        self.env.close()


class TestUIStatic(unittest.TestCase):
    def test_every_whitelisted_file_and_font_is_served(self):
        css = read("style.css")
        fonts = sorted(set(re.findall(r"url\(/fonts/([\w.-]+)\)", css)))
        self.assertGreaterEqual(len(fonts), 10)
        with Server() as s:
            for path in STATIC_WHITELIST:
                code, ctype, body = s.get(path)
                self.assertEqual(code, 200, path)
                self.assertTrue(body, path)
                self.assertRegex(ctype, r"text/(html|css|javascript)", path)
            for f in fonts:
                code, ctype, body = s.get("/fonts/" + f)
                self.assertEqual(code, 200, f)
                self.assertEqual(body[:4], b"wOF2", f)
            for path in ("/data/train.json", "/data/dev.json"):
                code, _, body = s.get(path)
                self.assertEqual(code, 200, path)
                self.assertEqual(len(json.loads(body)["episodes"]), 10)

    def test_server_refuses_anything_else(self):
        with Server() as s:
            for path in ("/private/x", "/fonts/../app.js", "/fonts/x.ttf", "/../README.md", "/style.css.bak", "/data/secret.json"):
                self.assertEqual(s.get(path)[0], 404, path)

    def test_every_font_family_ships_its_licence(self):
        files = os.listdir(os.path.join(STATIC_DIR, "fonts"))
        for fam in ("inter", "source-serif-4", "jetbrains-mono"):
            self.assertTrue(any(f.startswith(fam) for f in files), fam)
            self.assertIn(f"OFL-{fam}.txt", files)
        for f in (x for x in files if x.endswith(".woff2")):
            self.assertTrue(any(f.startswith(fam) for fam in ("inter", "source-serif-4", "jetbrains-mono")), f"unlicensed font {f}")

    def test_no_network_dependencies(self):
        for name in HTML + tuple(JS.values()) + ("style.css",):
            text = read(name)
            for url in re.findall(r"""(?:src|href)\s*=\s*["'](https?:[^"']+)|url\(\s*["']?(https?:[^)"']+)""", text):
                self.fail(f"{name} loads from the network: {url}")
            self.assertNotIn("@import", text, name)

    def test_every_element_id_used_by_scripts_exists(self):
        for html, js in JS.items():
            ids = set(re.findall(r'\sid="([\w-]+)"', read(html)))
            used = set(re.findall(r'\$\("([\w-]+)"\)', read(js)))
            self.assertTrue(used, js)
            self.assertFalse(used - ids, f"{js} references ids missing from {html}: {sorted(used - ids)}")
            dup = [i for i in ids if len(re.findall(rf'\sid="{i}"', read(html))) > 1]
            self.assertFalse(dup, f"duplicate ids in {html}: {dup}")

    def test_accessibility_basics(self):
        for html in HTML:
            text = read(html)
            self.assertRegex(text, r'<html lang="ru">', html)
            self.assertIn('name="viewport"', text, html)
            self.assertIn('class="skip"', text, html)
            ids = set(re.findall(r'\sid="([\w-]+)"', text))
            labelled = set(re.findall(r'<label[^>]*for="([\w-]+)"', text))
            for m in re.finditer(r"<(input|select|textarea)\b([^>]*)>", text):
                attrs = m.group(2)
                fid = re.search(r'id="([\w-]+)"', attrs)
                start = text.rfind("<label", 0, m.start())
                wrapped = start != -1 and text.find("</label>", start) > m.start()
                ok = (fid and fid.group(1) in labelled) or wrapped or "aria-label" in attrs
                self.assertTrue(ok, f"{html}: unlabeled control {m.group(0)[:80]}")
            for m in re.finditer(r"<button\b([^>]*)>(.*?)</button>", text, re.S):
                name = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                self.assertTrue(name or "aria-label" in m.group(1), f"{html}: button without a name {m.group(0)[:80]}")
            for m in re.finditer(r"<img\b[^>]*>", text):
                self.assertIn("alt=", m.group(0), html)
            for ref in re.findall(r'aria-(?:labelledby|describedby)="([\w-]+)"', text):
                self.assertIn(ref, ids, f"{html}: aria reference to missing id {ref}")
        self.assertNotIn("confirm(", read("app.js"), "use the accessible <dialog>, not window.confirm")
        self.assertIn("prefers-reduced-motion", read("style.css"))
        self.assertIn(":focus-visible", read("style.css"))

    def test_hero_case_figures_match_the_episode_data(self):
        """Every figure in the hero case card is read from train-03's public tables, so a regenerated
        suite can never leave a stale or invented number on the start page."""
        import csv
        from decimal import ROUND_HALF_EVEN, Decimal
        ep = "ep_8969ce76c2b8c8da"
        pub = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "episodes", "train", ep, "public")
        html = read("play.html")
        case = re.search(r'<figure class="case.*?</figure>', html, re.S).group(0)
        self.assertIn(ep, case)

        def group(minor):
            whole, frac = divmod(minor, 100)
            return f"{whole:,}".replace(",", " ") + f".{frac:02d}"

        with open(os.path.join(pub, "invoices.jsonl"), encoding="utf-8") as fh:
            invoices = {r["invoice_id"]: r for r in map(json.loads, filter(str.strip, fh))}
        with open(os.path.join(pub, "fx.csv"), encoding="utf-8") as fh:
            fx = {(r["date"], r["source_currency"], r["target_currency"]): r["rate"] for r in csv.DictReader(fh)}
        with open(os.path.join(pub, "ledger.csv"), encoding="utf-8") as fh:
            ledger = {r["row_id"]: r for r in csv.DictReader(fh)}
        rows = re.findall(r'<tr class="([^"]*)"><td>(INV-[\w-]+)</td><td class="dt">(\d\d)\.(\d\d)</td><td class="num">([\d ]+\.\d\d)<span class="u">([A-Z]{3})</span></td><td class="gl">(GL-[\w-]+)</td><td><svg[^>]*><use href="#tm-(\w+)"/></svg></td></tr>', case)
        self.assertEqual([r[1] for r in rows], ["INV-S3-3285", "INV-S3-3286", "INV-S3-3287", "INV-S3-3288", "INV-S3-3289"])
        for cls, inv, dd, mm, total, ccy, gl, mark in rows:
            rec = invoices[inv]
            self.assertEqual(rec["issued_at"][5:10], f"{mm}-{dd}", inv)
            self.assertEqual(rec["currency"], ccy, inv)
            self.assertEqual(group(rec["total_minor"]), total, inv)
            # the cited ledger row is this invoice's receivable; a tick means it agrees, a cross that it does not
            self.assertEqual((ledger[gl]["invoice_id"], ledger[gl]["account"]), (inv, "1200"), gl)
            agrees = ccy == "KZT" and int(ledger[gl]["debit_minor"]) == rec["total_minor"]
            self.assertEqual(mark, "agree" if agrees else "exc", f"{inv}: mark {mark}")
        inv = invoices["INV-S3-3287"]
        right, wrong = fx[("2026-03-13", "USD", "KZT")], fx[("2026-03-18", "USD", "KZT")]
        self.assertEqual((right, wrong), ("503.695", "501.515"))
        booked = int(ledger["GL-S3-11663"]["debit_minor"])
        self.assertEqual(ledger["GL-S3-11663"]["invoice_id"], "INV-S3-3287")
        cent = Decimal("1")
        expected = int((Decimal(inv["total_minor"]) * Decimal(right)).quantize(cent, ROUND_HALF_EVEN))
        self.assertEqual(int((Decimal(inv["total_minor"]) * Decimal(wrong)).quantize(cent, ROUND_HALF_EVEN)), booked)
        diff = expected - booked
        figures = {
            "invoice": group(inv["total_minor"]), "right rate": right, "wrong rate": wrong,
            "should be booked": group(expected), "booked": group(booked), "difference": group(diff),
            "difference in minor units": str(diff), "invoice date": "13.03", "wrong rate date": "18.03",
        }
        self.assertEqual((figures["should be booked"], figures["booked"], figures["difference"], figures["difference in minor units"]),
                         ("10 134 343.40", "10 090 481.80", "43 861.60", "4386160"))
        for name, text in figures.items():
            self.assertTrue(text in case, f"hero {name} {text!r} is not shown or is stale")
        self.assertIn(f'data-count="{diff}"', case)

    def test_colour_contrast_meets_wcag_aa(self):
        dark = re.search(r"\[data-theme=dark\]\{(.*?)\}", read("style.css"), re.S)
        self.assertIsNotNone(dark, "the dark theme must exist")
        themes = [("light", css_vars()), ("dark", {**css_vars(), **dict(re.findall(r"--([\w-]+):(#[0-9a-fA-F]{6})", dark.group(1)))})]
        for name, v in themes:
            with self.subTest(theme=name):
                self._contrast(v)

    def _contrast(self, v):
        pairs = [  # (foreground, background, minimum ratio)
            ("txt", "bg", 7), ("txt", "s1", 7), ("txt2", "s1", 4.5), ("txt2", "s2", 4.5), ("txt3", "s1", 4.5),
            ("gold", "bg", 4.5), ("gold", "s1", 4.5), ("gold-ink", "gold", 7), ("pos", "s1", 4.5), ("neg", "s1", 4.5),
        ]
        for fg, bg, need in pairs:
            ratio = contrast(v[fg], v[bg])
            self.assertGreaterEqual(ratio, need, f"--{fg} on --{bg}: {ratio:.2f} < {need}")


if __name__ == "__main__":
    unittest.main()
