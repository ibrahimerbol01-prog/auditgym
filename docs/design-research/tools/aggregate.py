"""Aggregate captured design samples into a dataset, statistics and contact sheets.

Usage: python3 -I aggregate.py <research_dir> <out_dir>
"""
import csv
import colorsys
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

research, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
(out / "contact_sheets").mkdir(exist_ok=True)

targets = json.loads((research / "targets.json").read_text()) + (json.loads((research / "targets2.json").read_text()) if (research / "targets2.json").exists() else [])
order = {t[1]: i for i, t in enumerate(targets)}
recs = []
for f in sorted((research / "data").glob("*.json")):
    if f.name.startswith("_"):
        continue
    recs.append(json.loads(f.read_text()))
recs.sort(key=lambda r: order.get(r["name"], 999))


def hsl(hexc):
    if not hexc:
        return None
    r, g, b = (int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return round(h * 360), round(s, 2), round(l, 2)


def hue_family(hexc):
    v = hsl(hexc)
    if not v:
        return None
    h, s, l = v
    if s < 0.15:
        return "neutral"
    if h < 20 or h >= 335:
        return "red/pink"
    if h < 45:
        return "orange/brown"
    if h < 70:
        return "yellow/gold"
    if h < 165:
        return "green"
    if h < 200:
        return "teal/cyan"
    if h < 245:
        return "blue"
    if h < 290:
        return "indigo/violet"
    return "magenta/purple"


GENERIC = {"system-ui", "-apple-system", "ui-sans-serif", "sans-serif", "BlinkMacSystemFont", "Segoe UI", "Arial", "Helvetica", "Helvetica Neue", "Roboto"}

rows = []
for r in recs:
    m = r.get("metrics") or {}
    sig = m.get("signals") or {}
    fonts = [f for f, _ in (m.get("fonts_by_chars") or [])]
    body_font = m.get("body_font")
    row = {
        "id": r["id"], "name": r["name"], "category": r["category"], "url": r["url"],
        "final_url": r.get("final_url"), "status": r.get("status"), "ok": r.get("ok"),
        "title": m.get("title"), "h1": m.get("h1"),
        "theme": m.get("theme"), "page_bg": m.get("page_bg"),
        "accent": m.get("accent"), "accent_family": hue_family(m.get("accent")),
        "h1_font": m.get("h1_font"), "h1_size_px": m.get("h1_size_px"), "h1_weight": m.get("h1_weight"),
        "body_font": body_font, "top_fonts": " | ".join(fonts[:3]),
        "serif_share": m.get("serif_share"), "mono_share": m.get("mono_share"),
        "control_radius_px": m.get("control_radius_median"),
        "gradients": sig.get("gradients"), "colored_glows": sig.get("colored_glows"),
        "backdrop_blur": sig.get("backdrop_blur"), "caps_labels": sig.get("caps_letterspaced_labels"),
        "emoji": sig.get("emoji"), "h1_italic_spans": m.get("h1_italic_spans"),
        "mentions_agent": (m.get("copy") or {}).get("mentions_agent"),
        "mentions_trust": (m.get("copy") or {}).get("mentions_trust"),
        "mentions_evidence": (m.get("copy") or {}).get("mentions_evidence"),
        "shot_desktop": f"shots/{r['id']}__desktop.jpg", "shot_full": f"shots/{r['id']}__full.jpg",
        "shot_mobile": f"shots/{r['id']}__mobile.jpg",
    }
    # A capture behind a login wall, bot check or near-empty page is kept but flagged.
    row["usable"] = bool(r.get("ok") and r.get("status") and r["status"] < 400 and (sig.get("text_elements") or 0) >= 15)
    rows.append(row)

(out / "samples.json").write_text(json.dumps({"captured": len(rows), "samples": rows, "raw": recs}, indent=2, ensure_ascii=False))
with open(out / "samples.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

# ---------- statistics over usable samples (excluding the pattern-library and reference rows for market stats)
usable = [r for r in rows if r["usable"]]
market = [r for r in usable if r["category"] not in ("patterns", "reference")]


def pct(n, d):
    return f"{(100 * n / d):.0f}%" if d else "n/a"


def font_key(f):
    return (f or "").strip()


stats = {"n_captured": len(rows), "n_usable": len(usable), "n_market": len(market)}
by_cat = defaultdict(list)
for r in market:
    by_cat[r["category"]].append(r)

lines = []
lines.append(f"Captured {len(rows)} pages; {len(usable)} usable; market sample (excluding pattern libraries and references) n = {len(market)}.\n")
lines.append("| Measure | All market | " + " | ".join(sorted(by_cat)) + " |")
lines.append("|---|---|" + "---|" * len(by_cat))


def row_stat(label, fn):
    cells = [fn(market)] + [fn(by_cat[c]) for c in sorted(by_cat)]
    lines.append(f"| {label} | " + " | ".join(cells) + " |")


row_stat("n", lambda rs: str(len(rs)))
row_stat("Dark theme first", lambda rs: pct(sum(r["theme"] == "dark" for r in rs), len(rs)))
row_stat("Inter is a top-3 font", lambda rs: pct(sum("inter" in (r["top_fonts"] or "").lower().split(" | ") for r in rs), len(rs)))
row_stat("System/default font stack is top-3", lambda rs: pct(sum(any(f in ("-apple-system", "system-ui", "ui-sans-serif", "blinkmacsystemfont", "arial", "helvetica") for f in (r["top_fonts"] or "").lower().split(" | ")) for r in rs), len(rs)))
row_stat("Serif headline (h1)", lambda rs: pct(sum(any(k in (r["h1_font"] or "").lower() for k in ("serif", "garamond", "tiempos", "times", "georgia", "freight", "canela", "lyon", "ivar", "signifier", "sectra", "editorial", "copernicus", "newsreader", "fraunces", "playfair")) and "sans" not in (r["h1_font"] or "").lower() for r in rs), len(rs)))
row_stat("Any gradient element", lambda rs: pct(sum((r["gradients"] or 0) > 0 for r in rs), len(rs)))
row_stat("Coloured glow shadows", lambda rs: pct(sum((r["colored_glows"] or 0) > 0 for r in rs), len(rs)))
row_stat("Backdrop blur (glass)", lambda rs: pct(sum((r["backdrop_blur"] or 0) > 0 for r in rs), len(rs)))
row_stat("≥3 letter-spaced CAPS labels", lambda rs: pct(sum((r["caps_labels"] or 0) >= 3 for r in rs), len(rs)))
row_stat("Accent is indigo/violet/purple", lambda rs: pct(sum(r["accent_family"] in ("indigo/violet", "magenta/purple") for r in rs), len(rs)))
row_stat("No saturated button colour (monochrome CTAs)", lambda rs: pct(sum(r["accent"] is None for r in rs), len(rs)))
row_stat("Pill-shaped buttons (radius ≥ 20 px)", lambda rs: pct(sum((r["control_radius_px"] or 0) >= 20 for r in rs), len(rs)))
row_stat("Square-ish buttons (radius ≤ 4 px)", lambda rs: pct(sum(r["control_radius_px"] is not None and r["control_radius_px"] <= 4 for r in rs), len(rs)))
row_stat("Median h1 size (px)", lambda rs: str(round(statistics.median([r["h1_size_px"] for r in rs if r["h1_size_px"]]))) if any(r["h1_size_px"] for r in rs) else "n/a")
row_stat("Mentions 'agent'", lambda rs: pct(sum((r["mentions_agent"] or 0) > 0 for r in rs), len(rs)))
row_stat("Mentions evidence/sources/citations", lambda rs: pct(sum((r["mentions_evidence"] or 0) > 0 for r in rs), len(rs)))

font_counter = Counter()
for r in market:
    for f in (r["top_fonts"] or "").split(" | "):
        if f:
            font_counter[font_key(f).lower()] += 1
accent_counter = Counter(r["accent_family"] for r in market if r["accent_family"])
lines.append("\n**Most common fonts (pages where the font is in the top 3 by text volume):** " + ", ".join(f"{f} ({n})" for f, n in font_counter.most_common(15)))
lines.append("\n**Accent hue families (from saturated button backgrounds):** " + ", ".join(f"{k} ({n})" for k, n in accent_counter.most_common()))
(out / "stats.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))

# ---------- contact sheets: one per category, desktop viewport thumbnails with labels
TW, TH, PAD, LAB = 480, 300, 16, 34
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    font_s = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
except OSError:
    font = font_s = ImageFont.load_default()
cats = defaultdict(list)
for r in rows:
    cats[r["category"]].append(r)
for cat, rs in cats.items():
    cols = 3
    n = len(rs)
    rws = (n + cols - 1) // cols
    W = cols * TW + (cols + 1) * PAD
    Hh = rws * (TH + LAB) + (rws + 1) * PAD + 40
    sheet = Image.new("RGB", (W, Hh), (24, 23, 21))
    d = ImageDraw.Draw(sheet)
    d.text((PAD, 12), f"AI app design samples · {cat} · {n} products · desktop 1440×900", fill=(239, 233, 220), font=font)
    for i, r in enumerate(rs):
        x = PAD + (i % cols) * (TW + PAD)
        y = 40 + PAD + (i // cols) * (TH + LAB + PAD)
        p = research / r["shot_desktop"]
        if p.exists():
            im = Image.open(p).convert("RGB")
            im.thumbnail((TW, TH))
            sheet.paste(im, (x, y))
        else:
            d.rectangle([x, y, x + TW, y + TH], outline=(90, 85, 76))
            d.text((x + 10, y + 10), "no capture", fill=(150, 140, 127), font=font_s)
        if r["usable"]:
            label = r["name"]
        elif r["ok"] and r["status"] and r["status"] < 400:
            label = r["name"] + "  (image only: too little text to measure)"
        else:
            label = r["name"] + "  (blocked, login wall or timeout)"

        d.text((x, y + TH + 4), label, fill=(239, 233, 220), font=font)
        meta = f"{r['theme'] or '?'} · {r['top_fonts'][:40] if r['top_fonts'] else '?'} · accent {r['accent'] or '-'}"
        d.text((x, y + TH + 20), meta, fill=(174, 167, 151), font=font_s)
    sheet.save(out / "contact_sheets" / f"{cat}.jpg", quality=82)
print("contact sheets:", sorted(p.name for p in (out / "contact_sheets").glob("*.jpg")))
