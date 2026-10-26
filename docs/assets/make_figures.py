"""The README's two figures, generated from the numbers the tests assert.

Hand-rolled SVG rather than a plotting library: the repo already requires
chromium, the figures are three bar groups, and a 30 MB dependency for that
would be a cost every contributor pays. The SVG is the source and diffs as
text; the PNG is rendered from it because that is what a README shows and a PNG
cannot be sanitised into something else by a proxy.

**Every number here comes from a source the test suite already recomputes**:
`reproduce.py`'s DETERMINISTIC_CELLS for the two baselines, the run records for
the skill, and `results/ablation/` for the second figure. `figures.json` is
written next to the images and `tests/test_artifacts.py` compares it against
those sources, so a figure cannot drift away from the claim it illustrates.

    python docs/assets/make_figures.py            # regenerate both figures
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ASSETS = Path(__file__).resolve().parent

# A palette that survives greyscale printing and colour-blind readers, because
# the point of the second bar is to be compared with the first.
GRAY = "#9aa4b2"
BLUE = "#5b7290"
GREEN = "#2f6f4f"
AMBER = "#b45309"
INK = "#1f2937"
MUTED = "#6b7280"
RULE = "#e5e7eb"

FONT = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
        "'Helvetica Neue', Arial, sans-serif")


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def text(x: float, y: float, s: str, size: int = 12, weight: int = 400,
         fill: str = INK, anchor: str = "start", opacity: float = 1.0) -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" '
            f'font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}" opacity="{opacity}">{esc(s)}</text>')


def bar(x: float, y: float, w: float, h: float, fill: str, radius: float = 3) -> str:
    if h <= 0:
        return ""
    r = min(radius, w / 2, h)
    return (f'<path d="M{x:.1f},{y + h:.1f} L{x:.1f},{y + r:.1f} '
            f'Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} '
            f'L{x + w - r:.1f},{y:.1f} Q{x + w:.1f},{y:.1f} '
            f'{x + w:.1f},{y + r:.1f} L{x + w:.1f},{y + h:.1f} Z" fill="{fill}"/>')


def svg_doc(width: int, height: int, body: list[str]) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" role="img">'
            f'<rect width="{width}" height="{height}" fill="#ffffff"/>'
            + "".join(body) + "</svg>\n")


def legend(x: float, y: float, items: list[tuple[str, str]]) -> list[str]:
    out = []
    for label, colour in items:
        if colour == "dashed":
            out.append(f'<line x1="{x:.1f}" y1="{y - 4:.1f}" x2="{x + 16:.1f}" '
                       f'y2="{y - 4:.1f}" stroke="{AMBER}" stroke-width="1.6" '
                       f'stroke-dasharray="4 3"/>')
        else:
            out.append(f'<rect x="{x:.1f}" y="{y - 9:.1f}" width="11" height="11" '
                       f'rx="2" fill="{colour}"/>')
        out.append(text(x + 17, y, label, size=11, fill=MUTED))
        x += 17 + 7.0 * len(label) + 22
    return out


# --------------------------------------------------------------------------
# Figure 1: the page moves, and what each method is worth
# --------------------------------------------------------------------------

def figure_ladder() -> tuple[str, dict]:
    from reproduce import DETERMINISTIC_CELLS

    # The two baselines are the deterministic cells; the skill is the three
    # runs per page that tests/test_artifacts.py asserts at 100 with SR 100.
    def cell(mode: str, variant: str) -> float:
        return DETERMINISTIC_CELLS[(mode, variant)][0]

    skill = {}
    for variant in ("default", "relayout-nostid"):
        runs = sorted(ROOT.glob(f"results/exec-skill+verifier-{variant}-r*.json"))
        scores = [json.loads(p.read_text(encoding="utf-8"))["score"] for p in runs]
        if not scores or min(scores) != 100.0:
            raise SystemExit(f"figure assumes the skill scores 100 on {variant}: {scores}")
        skill[variant] = scores[0]

    groups = [
        ("recorded page", "default",
         cell("replay", "default"), cell("reparam", "default"), skill["default"]),
        ("values changed", "jitter",
         cell("replay", "jitter"), cell("reparam", "jitter"), None),
        ("re-laid out, hooks gone", "relayout-nostid",
         cell("replay", "relayout-nostid"), cell("reparam", "relayout-nostid"),
         skill["relayout-nostid"]),
    ]

    W, H = 900, 470
    left, right, top, bottom = 78, 40, 132, 96
    plot_h = H - top - bottom
    plot_w = W - left - right

    def y_of(v: float) -> float:
        return top + plot_h * (1 - v / 100.0)

    body: list[str] = [
        text(left - 34, 44, "A recording is perfect until the page moves",
             size=22, weight=600),
        text(left - 34, 70, "Score out of 100, same task, same page contents — "
             "the page is the only variable", size=13, fill=MUTED),
    ]
    body += legend(left - 34, 100, [
        ("replay the recording", GRAY),
        ("re-parameterized replay", BLUE),
        ("skill + verifier", GREEN),
        ("dashed = nothing done (15)", "dashed"),
    ])

    for v in (0, 25, 50, 75, 100):
        yy = y_of(v)
        body.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{left + plot_w}" '
                    f'y2="{yy:.1f}" stroke="{RULE}" stroke-width="1"/>')
        body.append(text(left - 12, yy + 4, str(v), size=11, fill=MUTED, anchor="end"))

    group_w = plot_w / len(groups)
    bar_w = 34
    gap = 12
    for gi, (label, _variant, replay, reparam, skl) in enumerate(groups):
        cx = left + group_w * (gi + 0.5)
        series = [("replay", replay, GRAY), ("reparam", reparam, BLUE)]
        if skl is not None:
            series.append(("skill", skl, GREEN))
        start = cx - (len(series) * (bar_w + gap) - gap) / 2
        for si, (_, value, colour) in enumerate(series):
            bx = start + si * (bar_w + gap)
            body.append(bar(bx, y_of(value), bar_w, plot_h * value / 100.0, colour))
            body.append(text(bx + bar_w / 2, y_of(value) - 7, f"{value:.0f}",
                             size=12, weight=600, fill=INK, anchor="middle"))
        body.append(text(cx, top + plot_h + 24, label, size=12, fill=INK,
                         anchor="middle"))
        if skl is None:
            body.append(text(cx, top + plot_h + 44, "skill: not measured here",
                             size=10, fill=MUTED, anchor="middle", opacity=0.9))

    floor_y = y_of(15.0)
    body.append(f'<line x1="{left}" y1="{floor_y:.1f}" x2="{left + plot_w}" '
                f'y2="{floor_y:.1f}" stroke="{AMBER}" stroke-width="1.4" '
                f'stroke-dasharray="5 4"/>')
    body.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" '
                f'y2="{top + plot_h}" stroke="{INK}" stroke-width="1.2"/>')
    body.append(text(left - 34, H - 34,
                     "Sources: reproduce.py (replay and re-parameterized cells, "
                     "asserted without a model); results/exec-skill+verifier-*.json "
                     "(3 runs per page, all 100, SR 100).", size=10, fill=MUTED))
    body.append(text(left - 34, H - 18,
                     "The skill is the only condition that holds where the "
                     "recording collapses. Where the page did not move, the "
                     "recording ties it for free.", size=10, fill=MUTED))

    data = {
        "figure": "ladder",
        "groups": [{"page": label, "variant": variant, "replay": replay,
                    "reparameterized": reparam, "skill": skl}
                   for label, variant, replay, reparam, skl in groups],
        "floor": 15,
    }
    return svg_doc(W, H, body), data


# --------------------------------------------------------------------------
# Figure 2: the score was fine, the run never finished
# --------------------------------------------------------------------------

def figure_score_vs_finished() -> tuple[str, dict]:
    arms = [
        ("with the\r\nverifier clause", "with-clause"),
        ("without it", "no-clause"),
        ("the stock skill", "v3"),
    ]
    rows = []
    for label, tag in arms:
        runs = [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(ROOT.glob(f"results/ablation/*-r*-{tag}.json"))]
        if len(runs) != 3:
            raise SystemExit(f"figure assumes three runs for {tag}: {len(runs)}")
        score = sum(r["score"] for r in runs) / len(runs)
        finished = sum(1 for r in runs if r["run"]["finished"]) / len(runs)
        rows.append({"arm": label.replace("\r\n", " "), "score": score,
                     "finished": finished, "runs": len(runs)})

    W, H = 900, 400
    left, right, top, bottom = 78, 40, 138, 104
    plot_h = H - top - bottom
    plot_w = W - left - right

    def y_of(v: float) -> float:
        return top + plot_h * (1 - v / 100.0)

    body: list[str] = [
        text(left - 34, 44, "The score says 100; the run never said it was done",
             size=22, weight=600),
        text(left - 34, 70, "Three skills, same page, same executor, three runs "
             "each. Each is measured twice: by its rubric, and by whether the "
             "agent ever finished.", size=13, fill=MUTED),
    ]
    body += legend(left - 34, 106, [
        ("rubric score (mean)", BLUE),
        ("runs that declared completion", GREEN),
    ])

    for v in (0, 25, 50, 75, 100):
        yy = y_of(v)
        body.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{left + plot_w}" '
                    f'y2="{yy:.1f}" stroke="{RULE}" stroke-width="1"/>')
        body.append(text(left - 12, yy + 4, str(v), size=11, fill=MUTED, anchor="end"))

    group_w = plot_w / len(rows)
    bar_w = 56
    gap = 26
    for gi, row in enumerate(rows):
        cx = left + group_w * (gi + 0.5)
        start = cx - (2 * bar_w + gap) / 2
        for si, (key, colour) in enumerate((("score", BLUE), ("finished", GREEN))):
            # `score` is already 0-100; `finished` is a fraction. Scaling both by
            # 100 drew the score bars a hundred times too tall -- over the title.
            value = float(row[key]) * (100.0 if key == "finished" else 1.0)
            bx = start + si * (bar_w + gap)
            body.append(bar(bx, y_of(value), bar_w, plot_h * value / 100.0, colour))
            shown = f"{value:.0f}" if key == "score" else f"{value:.0f}%"
            body.append(text(bx + bar_w / 2, y_of(value) - 7, shown, size=13,
                             weight=600, fill=INK, anchor="middle"))
        body.append(text(cx, top + plot_h + 24, row["arm"], size=12, fill=INK,
                         anchor="middle"))

    body.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" '
                f'y2="{top + plot_h}" stroke="{INK}" stroke-width="1.2"/>')
    body.append(text(left - 34, H - 40,
                     "Sources: results/ablation/exec-skill+verifier-relayout-nostid-"
                     "r1..r3-{with-clause,no-clause,v3}.json.", size=10, fill=MUTED))
    body.append(text(left - 34, H - 24,
                     "The middle arm did the work correctly three times and spent "
                     "its whole 30-step budget without declaring completion, so "
                     "the verifier never ran. Read the finished column.", size=10,
                     fill=MUTED))
    return svg_doc(W, H, body), {"figure": "score-vs-finished", "arms": rows}


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------

def render_png(svg_path: Path, png_path: Path, scale: int = 2) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 900, "height": 2400},
                                device_scale_factor=scale)
        page.goto(svg_path.as_uri(), wait_until="load")
        page.set_viewport_size({"width": 900, "height": 2400})
        box = page.evaluate("() => { const s = document.documentElement;"
                            " return {w: s.getAttribute('width'),"
                            " h: s.getAttribute('height')}; }")
        page.set_viewport_size({"width": int(box["w"]), "height": int(box["h"])})
        page.locator("svg").screenshot(path=str(png_path))
        browser.close()


def main() -> int:
    figures = {
        "ladder": figure_ladder(),
        "score-vs-finished": figure_score_vs_finished(),
    }
    data = {}
    for name, (svg, payload) in figures.items():
        svg_path = ASSETS / f"{name}.svg"
        svg_path.write_text(svg, encoding="utf-8")
        render_png(svg_path, ASSETS / f"{name}.png")
        data[name] = payload
        print(f"  {name}.svg / .png")
    (ASSETS / "figures.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  figures.json ({len(data)} figures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
