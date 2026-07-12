#!/usr/bin/env python3
"""Generate the hurdy-gurdy explainer video (YouTube-ready MP4).

Renders a narrated slide deck: slides are HTML pages screenshotted at
1920x1080 by headless Chromium, narration is synthesized per slide with
pico2wave, and ffmpeg assembles per-slide segments into a single
H.264/AAC MP4 plus a ready-to-paste YouTube description.

Requirements (all resolvable offline once installed):
  - a Chromium binary        (CHROMIUM env var, or auto-detected)
  - pico2wave                (apt: libttspico-utils)
  - ffmpeg with libx264+aac  (FFMPEG env var, or imageio-ffmpeg from PyPI)

Usage:  python3 scripts/explainer_video.py [outdir]   (default: video/)
"""

import glob
import html
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WIDTH, HEIGHT = 1920, 1080
FPS = 30
LEAD_IN = 0.5   # silence before narration starts on each slide
TAIL = 1.0      # silence after narration ends before the next slide

PAPER_TITLE = "Untrusted Authors, Trusted Answers"
PAPER_SUBTITLE = "A Calculus of Fidelity-Graded Translations"
REPO_URL = "github.com/cksystemsgroup/hurdy-gurdy"


def find_chromium() -> str:
    cand = os.environ.get("CHROMIUM")
    if cand and Path(cand).exists():
        return cand
    for pattern in (
        "/opt/pw-browsers/chromium-*/chrome-linux/chrome",
        str(Path.home() / ".cache/ms-playwright/chromium-*/chrome-linux/chrome"),
    ):
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    for name in ("chromium", "chromium-browser", "google-chrome"):
        path = shutil.which(name)
        if path:
            return path
    sys.exit("no Chromium binary found; set CHROMIUM")


def find_ffmpeg() -> str:
    cand = os.environ.get("FFMPEG")
    if cand and Path(cand).exists():
        return cand
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass
    path = shutil.which("ffmpeg")
    if path:
        return path
    sys.exit("no ffmpeg found; pip install imageio-ffmpeg or set FFMPEG")


# --------------------------------------------------------------------------
# Slide deck: (kicker, title, body_html, narration_for_tts)
#
# The narration strings are written for the pico2wave voice: proper names
# are respelled phonetically (RISC-V -> "risk five", BTOR2 -> "beetor two",
# SMT-LIB -> "S M T lib") so the synthesized speech says what the slide
# shows.
# --------------------------------------------------------------------------

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 1920px; height: 1080px; overflow: hidden; }
body {
  font-family: 'DejaVu Sans', sans-serif;
  background: radial-gradient(1200px 800px at 20% 0%, #1b2030 0%, #0e1118 55%, #0a0c11 100%);
  color: #e8e6e0;
  display: flex; flex-direction: column;
  padding: 90px 120px 70px;
}
.kicker {
  font-size: 26px; letter-spacing: 6px; text-transform: uppercase;
  color: #d4a24e; margin-bottom: 22px; font-weight: bold;
}
h1 { font-size: 74px; line-height: 1.12; margin-bottom: 46px; font-weight: bold; }
h1 .dim { color: #9aa3b5; }
.body { flex: 1; font-size: 40px; line-height: 1.5; color: #c9cdd8; }
.body p { margin-bottom: 26px; }
.body strong { color: #f0eee8; }
.accent { color: #d4a24e; }
.mono { font-family: 'DejaVu Sans Mono', monospace; }
ul.big { list-style: none; }
ul.big li { margin-bottom: 26px; padding-left: 44px; position: relative; }
ul.big li::before { content: '\\25B8'; position: absolute; left: 0; color: #d4a24e; }
.footer {
  display: flex; justify-content: space-between; align-items: baseline;
  font-size: 26px; color: #6c7484; font-family: 'DejaVu Sans Mono', monospace;
}
table.grades { border-collapse: collapse; width: 100%; font-size: 34px; }
table.grades th, table.grades td { text-align: left; padding: 16px 28px; }
table.grades th { color: #d4a24e; border-bottom: 2px solid #3a4154;
  text-transform: uppercase; letter-spacing: 2px; font-size: 27px; }
table.grades td { border-bottom: 1px solid #232937; color: #c9cdd8; }
table.grades td:first-child { font-family: 'DejaVu Sans Mono', monospace; color: #f0eee8; }
.diagram { display: flex; justify-content: center; align-items: center; }
svg text { font-family: 'DejaVu Sans Mono', monospace; }
.cols { display: flex; gap: 70px; }
.cols > div { flex: 1; }
"""


def footer(idx: int, total: int) -> str:
    return (
        f'<div class="footer"><span>{html.escape(REPO_URL)}</span>'
        f"<span>{idx:02d} / {total:02d}</span></div>"
    )


def square_svg() -> str:
    """The commuting square, the paper's central diagram."""
    return """
<svg width="1280" height="530" viewBox="0 0 1280 530">
  <defs>
    <marker id="arr" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
      <path d="M0,0 L10,4 L0,8 z" fill="#d4a24e"/>
    </marker>
  </defs>
  <g font-size="40" fill="#f0eee8">
    <rect x="60" y="40" width="300" height="90" rx="12" fill="#1b2233" stroke="#3a4154" stroke-width="2"/>
    <text x="210" y="98" text-anchor="middle">source</text>
    <rect x="920" y="40" width="300" height="90" rx="12" fill="#1b2233" stroke="#3a4154" stroke-width="2"/>
    <text x="1070" y="98" text-anchor="middle">target</text>
    <rect x="60" y="400" width="300" height="90" rx="12" fill="#1b2233" stroke="#3a4154" stroke-width="2"/>
    <text x="210" y="458" text-anchor="middle">source'</text>
    <rect x="920" y="400" width="300" height="90" rx="12" fill="#1b2233" stroke="#3a4154" stroke-width="2"/>
    <text x="1070" y="458" text-anchor="middle">target'</text>
  </g>
  <g stroke="#d4a24e" stroke-width="4" marker-end="url(#arr)">
    <line x1="380" y1="85" x2="900" y2="85"/>
    <line x1="210" y1="150" x2="210" y2="380"/>
    <line x1="1070" y1="150" x2="1070" y2="380"/>
    <line x1="900" y1="445" x2="380" y2="445"/>
  </g>
  <g font-size="32" fill="#9aa3b5">
    <text x="640" y="55" text-anchor="middle">translate&#160;&#160;T</text>
    <text x="245" y="275">interpret&#160;&#160;I&#8347;</text>
    <text x="1035" y="275" text-anchor="end">interpret&#160;&#160;I&#8348;</text>
    <text x="640" y="510" text-anchor="middle">carry back&#160;&#160;L</text>
  </g>
</svg>"""


def routes_svg() -> str:
    """The spine with its Sail branch."""
    box = (
        '<rect x="{x}" y="{y}" width="{w}" height="80" rx="12" '
        'fill="{f}" stroke="{s}" stroke-width="{sw}"/>'
        '<text x="{cx}" y="{cy}" text-anchor="middle" font-size="36" fill="#f0eee8">{t}</text>'
    )

    def node(x, y, w, t, hub=False):
        return box.format(
            x=x, y=y, w=w, f="#2a2417" if hub else "#1b2233",
            s="#d4a24e" if hub else "#3a4154", sw=3 if hub else 2,
            cx=x + w / 2, cy=y + 52, t=t,
        )

    return f"""
<svg width="1520" height="500" viewBox="0 0 1520 500">
  <defs>
    <marker id="arr2" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
      <path d="M0,0 L10,4 L0,8 z" fill="#8a93a8"/>
    </marker>
  </defs>
  {node(40, 110, 130, "C")}
  {node(300, 110, 230, "RISC-V")}
  {node(770, 110, 230, "BTOR2", hub=True)}
  {node(1180, 110, 270, "SMT-LIB", hub=True)}
  {node(530, 330, 190, "SAIL")}
  <g stroke="#8a93a8" stroke-width="4" marker-end="url(#arr2)" fill="none">
    <line x1="180" y1="150" x2="290" y2="150"/>
    <line x1="540" y1="150" x2="760" y2="150"/>
    <line x1="1010" y1="150" x2="1170" y2="150"/>
    <line x1="440" y1="195" x2="570" y2="322"/>
    <line x1="700" y1="325" x2="830" y2="198"/>
  </g>
  <g font-size="26" fill="#6c7484">
    <text x="235" y="90" text-anchor="middle">pinned</text>
    <text x="650" y="90" text-anchor="middle">from the ISA manual</text>
    <text x="1090" y="90" text-anchor="middle">bridge</text>
    <text x="420" y="290" text-anchor="end">from the formal model</text>
    <text x="790" y="290">independent route</text>
  </g>
  <text x="760" y="470" text-anchor="middle" font-size="34" fill="#d4a24e">
    two independent routes to the same hub &#8594; agreement corroborates both</text>
</svg>"""


def build_slides() -> list[tuple[str, str, str, str]]:
    slides = []

    slides.append((
        "",
        "",
        f'<div style="height:100%; display:flex; flex-direction:column; justify-content:center; text-align:center;">'
        f'<div class="kicker" style="font-size:34px;">hurdy-gurdy</div>'
        f'<h1 style="font-size:96px; margin-bottom:30px;">{PAPER_TITLE}</h1>'
        f'<div style="font-size:48px; color:#9aa3b5; margin-bottom:70px;">{PAPER_SUBTITLE}</div>'
        f'<div style="font-size:36px; color:#c9cdd8;">Christoph Kirsch '
        f'<span style="color:#6c7484;">&#183; University of Salzburg &#183; Czech Technical University</span></div>'
        f'<div class="mono" style="font-size:32px; color:#d4a24e; margin-top:28px;">{REPO_URL}</div>'
        f"</div>",
        "This is hurdy-gurdy, a platform for deterministic, fidelity-graded "
        "translations between formal languages. It implements the calculus from "
        "the paper, Untrusted Authors, Trusted Answers, available as an archive "
        "preprint from the repository. The idea, in one sentence: to answer a "
        "question about a program, move the program to where the question is "
        "decidable, without ever trusting an unaudited step.",
    ))

    slides.append((
        "The problem",
        "Every translation is a place to be wrong",
        """<ul class="big">
<li>A <strong>C</strong> reachability question becomes a bit-vector <strong>model-checking</strong> problem;
a <strong>Python</strong> assertion becomes an <strong>arithmetic query</strong></li>
<li>Classical answers: <strong>prove the translator once</strong> (certified compilation)
or <strong>validate each run</strong> (translation validation)</li>
<li>Both are statements about a <strong>single edge</strong> &mdash; but in practice
representations form a <span class="accent"><strong>graph</strong></span>, with edges of
<strong>honestly different</strong> trustworthiness</li>
</ul>""",
        "A C program's reachability question becomes a model checking problem. "
        "A Python assertion becomes an arithmetic query. Every such move is a "
        "translation, and every translation is a place to be wrong. The classical "
        "responses, certified compilation and translation validation, are "
        "statements about a single edge. But in practice, representations form a "
        "graph: many source languages, several solver-facing targets, and more "
        "than one way to get from here to there, with honestly different "
        "trustworthiness.",
    ))

    slides.append((
        "The unit",
        'The pair is a <span class="accent">commuting square</span>',
        f'<div class="diagram">{square_svg()}</div>'
        '<div class="mono" style="text-align:center; font-size:46px; color:#d4a24e; margin-top:36px;">'
        "I&#8347;(p) &#8801;<sub>&#960;</sub> L( I&#8348;( T(p) ) )</div>",
        "The unit of the platform is the pair: two formally defined languages "
        "and four pure functions. A translator. An interpreter for each "
        "language. And a target-to-source interpreter, that carries a solver's "
        "answer back to the source. Together they close a commuting square: "
        "interpreting the source directly must match translating, interpreting "
        "the target, and carrying the result back. The square commuting is the "
        "pair's correctness statement, and a point where it fails to commute "
        "localizes a translator bug.",
    ))

    slides.append((
        "The grades",
        "Determinism, then honest fidelity",
        """<p style="font-size:36px;">Every function is <strong>pure</strong>: same input &#8658;
byte-identical output. On top of that, each pair <strong>declares</strong> what it guarantees:</p>
<table class="grades">
<tr><th>Grade</th><th>The translator's output is&#8230;</th></tr>
<tr><td>predicted</td><td>derivable byte-for-byte from a written specification</td></tr>
<tr><td>reproducible</td><td>not predictable, but pinned &#8658; identical bytes</td></tr>
<tr><td>checked</td><td>validated against the source on every run</td></tr>
<tr><td>proved</td><td>accompanied by a machine-checked commutation proof</td></tr>
<tr><td>trusted</td><td>taken on faith &mdash; never shipped uncovered</td></tr>
</table>""",
        "Everything is deterministic: the same input produces byte-identical "
        "output, always. And pairs do not pretend to be equally trustworthy. "
        "Each declares a fidelity grade. Predicted, when the output is "
        "foreseeable from a written specification. Reproducible, when it is "
        "only pinned. Checked, when it is validated against the source on "
        "every run. Proved, when a machine-checked proof accompanies it. And "
        "trusted, which assures nothing, and never ships uncovered.",
    ))

    slides.append((
        "Composition",
        "Routes compose &mdash; and <span class=\"accent\">branch</span>",
        f'<div class="diagram">{routes_svg()}</div>',
        "Pairs compose into routes, which inherit determinism and are only as "
        "faithful as their weakest pair. But routes can branch. Risk five "
        "reaches beetor two along two routes: directly, with a translator "
        "written from the instruction-set manual, and through sail, the "
        "architecture's formal model. The two translators were built "
        "independently, and that independence is a resource: agreement "
        "corroborates both routes, while disagreement localizes the bug to one "
        "pair. Branching turns several merely-checked pairs into a jointly "
        "stronger guarantee.",
    ))

    slides.append((
        "The registry",
        "13 languages, 13 pairs, two hubs",
        """<div class="cols">
<div>
<p><span class="accent"><strong>BTOR2 hub</strong></span> &mdash; bit-level model checking</p>
<ul class="big" style="font-size:36px;">
<li>C &#8594; RISC-V &#8594; BTOR2 <span style="color:#6c7484;">(the spine)</span></li>
<li>AArch64, WebAssembly, eBPF, EVM</li>
<li>dual routes via SAIL for RISC-V <em>and</em> AArch64</li>
</ul>
</div>
<div>
<p><span class="accent"><strong>SMT-LIB hub</strong></span> &mdash; theory-rich queries</p>
<ul class="big" style="font-size:36px;">
<li>chemical reaction networks</li>
<li>Python (a fragment)</li>
<li>BTOR2 &#8594; SMT-LIB bridge</li>
</ul>
</div>
</div>""",
        "The initial registry holds thirteen languages and thirteen pairs, "
        "organized around two reasoning hubs. Beetor two, for bit-level model "
        "checking, is reached by C through risk five, and by front ends for "
        "the sixty-four bit Arm architecture, WebAssembly, E B P F, and the "
        "Ethereum virtual machine. S M T lib, the theory-rich hub, is reached "
        "by chemical reaction networks and by a Python fragment, and a bridge "
        "connects the two hubs.",
    ))

    slides.append((
        "The experiment",
        "Untrusted authors, in both directions",
        """<ul class="big">
<li><strong>Every pair was written by an independent LLM agent</strong> from a one-page brief,
largely unsupervised &mdash; the architecture's cross-checks are the only semantic gate</li>
<li>The intended <strong>player</strong> is also an LLM: it chooses questions and routes,
but <span class="accent"><strong>can take no unchecked step</strong></span></li>
<li>The compositional core of the calculus is <strong>mechanized in Lean&#160;4</strong></li>
<li style="color:#d4a24e;"><strong>Trust comes from the architecture, not from the author</strong></li>
</ul>""",
        "And here is the experiment. Every pair, translator, carry-back, and "
        "tests, was implemented by an independent L L M agent from a one-page "
        "brief, largely unsupervised, with the architecture's cross-checks as "
        "the only semantic gate. The platform's intended player is also an "
        "L L M: it chooses questions and routes, but can take no unchecked "
        "step. The compositional core of the calculus is mechanized in lean "
        "four. Trust comes from the architecture, not from the author.",
    ))

    slides.append((
        "The evidence",
        "What the gate caught",
        """<ul class="big">
<li>Measured <strong>per-construct coverage</strong>: covered &#8743; faithful, against spec inventories
and public benchmark suites</li>
<li><strong>Branch agreement</strong> along the dual RISC-V and AArch64 routes,
with machine-derived ground truth</li>
<li><strong>Certified unreachability</strong> re-validated by a formally verified checker</li>
<li>Real defects caught &mdash; including one in the certificate pipeline's
<span class="accent"><strong>own checker adapter</strong></span> and three in its
<span class="accent"><strong>own measuring instruments</strong></span></li>
</ul>""",
        "The paper reports measurements, not aspirations: per-construct "
        "coverage, counted only where a construct is both covered and "
        "faithful. Branch agreement along the dual risk five and Arm routes, "
        "with machine-derived ground truth. Certified unreachability, "
        "re-validated by a formally verified checker. And the defects the "
        "architecture caught, including one in the certificate pipeline's own "
        "checker adapter, and three in its own measuring instruments.",
    ))

    slides.append((
        "Why the name",
        "The instrument and the player",
        f"""<p>A hurdy-gurdy's player cranks a wheel; the mechanism turns each choice
into sound <strong>the same way, every time</strong>.</p>
<ul class="big">
<li>the <strong>translator</strong> is the keyboard &mdash; same key &#8594; same pitch</li>
<li>the <strong>interpreters</strong> are the wheel &mdash; they make the sound real</li>
<li>the <strong>player</strong> &mdash; an LLM, or you &mdash; decides what to ask</li>
</ul>
<p style="margin-top:50px; font-size:36px; color:#9aa3b5;">
Paper: <strong style="color:#e8e6e0;">&ldquo;{PAPER_TITLE}: {PAPER_SUBTITLE}&rdquo;</strong>
(arXiv preprint &mdash; <span class="mono">paper/arxiv.pdf</span>, tag <span class="mono">arxiv.1</span>)<br/>
Code, evidence &amp; Lean mechanization: <span class="mono accent">{REPO_URL}</span></p>""",
        "Why the name? A hurdy-gurdy is an instrument whose player cranks a "
        "wheel, and the mechanism turns each choice into sound the same way, "
        "every time. The translator is the keyboard, same key, same pitch. The "
        "interpreters are the wheel. And the player, an L L M or a human, "
        "decides what to ask. Read the paper, Untrusted Authors, Trusted "
        "Answers, a Calculus of Fidelity-Graded Translations, and explore the "
        "code, the evidence, and the lean mechanization on GitHub.",
    ))

    return slides


def slide_html(kicker: str, title: str, body: str, idx: int, total: int) -> str:
    head = ""
    if kicker:
        head = f'<div class="kicker">{kicker}</div><h1>{title}</h1>'
    return (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{CSS}</style></head><body>"
        f'{head}<div class="body">{body}</div>{footer(idx, total)}'
        f"</body></html>"
    )


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def main() -> None:
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "video"
    work = outdir / "build"
    work.mkdir(parents=True, exist_ok=True)

    chromium = find_chromium()
    ffmpeg = find_ffmpeg()
    if not shutil.which("pico2wave"):
        sys.exit("pico2wave not found (apt-get install libttspico-utils)")

    slides = build_slides()
    total = len(slides)
    segments = []

    for i, (kicker, title, body, narration) in enumerate(slides, 1):
        html_path = work / f"slide{i:02d}.html"
        png_path = work / f"slide{i:02d}.png"
        wav_path = work / f"slide{i:02d}.wav"
        seg_path = work / f"seg{i:02d}.mp4"

        html_path.write_text(slide_html(kicker, title, body, i, total))
        # Oversize the window: headless "new" spends ~80px of --window-size
        # on non-viewport chrome; the encode step crops back to WIDTHxHEIGHT.
        run([
            chromium, "--headless=new", "--no-sandbox", "--disable-gpu",
            "--hide-scrollbars", "--force-device-scale-factor=1",
            f"--window-size={WIDTH},{HEIGHT + 200}",
            f"--screenshot={png_path}", f"file://{html_path}",
        ])
        run(["pico2wave", "-l", "en-US", "-w", str(wav_path), narration])

        dur = LEAD_IN + wav_seconds(wav_path) + TAIL
        delay_ms = int(LEAD_IN * 1000)
        run([
            ffmpeg, "-y", "-loop", "1", "-framerate", str(FPS),
            "-i", str(png_path), "-i", str(wav_path),
            "-filter_complex",
            f"[0:v]crop={WIDTH}:{HEIGHT}:0:0,fade=t=in:st=0:d=0.4,format=yuv420p[v];"
            f"[1:a]adelay={delay_ms}|{delay_ms},aresample=44100,apad[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k", str(seg_path),
        ])
        segments.append(seg_path)
        print(f"  slide {i:02d}/{total}  {dur:5.1f}s  {title or PAPER_TITLE!r}")

    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{s.name}'\n" for s in segments))
    final = outdir / "hurdy-gurdy-explainer.mp4"
    run([
        ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-c", "copy", "-movflags", "+faststart", str(final),
    ])

    (outdir / "description.txt").write_text(f"""hurdy-gurdy in a few minutes: {PAPER_TITLE}

hurdy-gurdy is a platform for deterministic, fidelity-graded translations
between formal languages, so that an LLM (or a human) can move a program to
where a question is decidable -- and reason about it there through external
interpreters and solvers -- without ever trusting an unaudited step.

This video explains the core ideas: pairs as commuting squares, determinism,
the five fidelity grades, routes that compose and branch, the two reasoning
hubs (BTOR2 and SMT-LIB), and the experiment in LLM-generated correctness.

Paper: "{PAPER_TITLE}: {PAPER_SUBTITLE}" by Christoph Kirsch
(arXiv preprint; built from the repository at tag arxiv.1 -- paper/arxiv.pdf)

Code, evidence, and the Lean 4 mechanization:
https://{REPO_URL}

00:00 What hurdy-gurdy is
""")

    size_mb = final.stat().st_size / 1e6
    print(f"\nwrote {final}  ({size_mb:.1f} MB)")
    print(f"wrote {outdir / 'description.txt'}")


if __name__ == "__main__":
    main()
