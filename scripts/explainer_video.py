#!/usr/bin/env python3
"""Generate the hurdy-gurdy explainer video (YouTube-ready MP4).

The deck is a Remotion (React) project in video/remotion/: ten animated
slides timed to per-slide narration. This script synthesizes the narration,
writes the wavs and the timing manifest the deck reads, and invokes
`remotion render` to produce a 1080p H.264/AAC MP4 plus a ready-to-paste
YouTube description.

Two narration engines:
  - default: Kokoro (hexgrad/Kokoro-82M, voice af_heart)
  - --voice-clone REF.wav: Chatterbox (ResembleAI) zero-shot cloning from a
    10-30 s clean speech sample; sampling seeds are pinned per slide so the
    output is reproducible, and Chatterbox watermarks the audio (Perth)

Requirements:
  - Kokoro path: pip install kokoro soundfile  (needs torch; ~330 MB model
    from Hugging Face on first run), plus espeak-ng, e.g. `brew install
    espeak-ng` (misaki's out-of-vocabulary fallback; the dylib bundled in
    the espeakng-loader wheel is broken on macOS -- it ignores its
    data-path argument and exits the process -- so a system install is
    required)
  - cloning path: pip install chatterbox-tts  (~2 GB model on first run;
    uses Apple-Silicon MPS when available)
  - Node >= 18 (the render step runs `npm install` + `npx remotion render`)

Usage:
  python3 scripts/explainer_video.py [--audio-only | --render-only]
                                     [--voice-clone REF.wav]
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REMOTION = REPO / "video" / "remotion"
AUDIO_DIR = REMOTION / "public" / "audio"
MANIFEST = REMOTION / "src" / "narration.json"
OUT_MP4 = REPO / "video" / "hurdy-gurdy-explainer.mp4"

FPS = 30
LEAD_IN = 0.5   # silence before narration starts on each slide
TAIL = 1.0      # silence after narration ends before the next slide
VOICE = "af_heart"
SAMPLE_RATE = 24000
CHUNK_GAP = 0.2  # silence inserted between Kokoro sentence chunks

PAPER_TITLE = "Untrusted Authors, Trusted Answers"
PAPER_SUBTITLE = "A Calculus of Fidelity-Graded Translations"
REPO_URL = "github.com/cksystemsgroup/hurdy-gurdy"

# --------------------------------------------------------------------------
# Narration, one entry per slide in video/remotion/src/slides/. The strings
# are written for TTS: proper names are respelled phonetically (RISC-V ->
# "risk five", BTOR2 -> "beetor two", SMT-LIB -> "S M T lib") so the
# synthesized speech says what the slide shows. The chapter titles become
# YouTube chapters in description.txt.
# --------------------------------------------------------------------------

SLIDES: list[tuple[str, str, str]] = [
    (
        "slide01",
        "What hurdy-gurdy is",
        "This is hurdy-gurdy, a platform for deterministic, fidelity-graded "
        "translations between formal languages. It implements the calculus from "
        "the paper, Untrusted Authors, Trusted Answers, available as an archive "
        "preprint from the repository. The idea, in one sentence: to answer a "
        "question about a program, move the program to where the question is "
        "decidable, without ever trusting an unaudited step.",
    ),
    (
        "slide02",
        "The vision: bootstrapping LLMs toward correctness",
        "Before the mechanics, the vision. Hurdy-gurdy is built as a "
        "two-directional experiment in L L M generated correctness: it "
        "bootstraps L L Ms toward correctness. In one direction, L L Ms "
        "develop hurdy-gurdy itself: independent agents wrote every pair, "
        "and the architecture's cross-checks are the only semantic gate. In "
        "the other direction, L L Ms use hurdy-gurdy to generate correct "
        "code, answering questions about programs through deterministic, "
        "graded, checked moves. Nearly all code is L L M generated; the "
        "human contribution is the architecture. And the same gate is the "
        "growth model: anyone, an L L M, an agent, or a human, can add a new "
        "language pair through an ordinary pull request, admitted by the "
        "architecture, not the author.",
    ),
    (
        "slide03",
        "Every translation is a place to be wrong",
        "A C program's reachability question becomes a model checking problem. "
        "A Python assertion becomes an arithmetic query. Every such move is a "
        "translation, and every translation is a place to be wrong. The classical "
        "responses, certified compilation and translation validation, are "
        "statements about a single edge. But in practice, representations form a "
        "graph: many source languages, several solver-facing targets, and more "
        "than one way to get from here to there, with honestly different "
        "trustworthiness.",
    ),
    (
        "slide04",
        "The pair is a commuting square",
        "The unit of the platform is the pair: two formally defined languages "
        "and four pure functions. A translator. An interpreter for each "
        "language. And a target-to-source interpreter, that carries a solver's "
        "answer back to the source. Together they close a commuting square: "
        "interpreting the source directly must match translating, interpreting "
        "the target, and carrying the result back. The square commuting is the "
        "pair's correctness statement, and a point where it fails to commute "
        "localizes a translator bug.",
    ),
    (
        "slide05",
        "Determinism and the five fidelity grades",
        "Everything is deterministic: the same input produces byte-identical "
        "output, always. And pairs do not pretend to be equally trustworthy. "
        "Each declares a fidelity grade. Predicted, when the output is "
        "foreseeable from a written specification. Reproducible, when it is "
        "only pinned. Checked, when it is validated against the source on "
        "every run. Proved, when a machine-checked proof accompanies it. And "
        "trusted, which assures nothing, and never ships uncovered.",
    ),
    (
        "slide06",
        "Routes compose -- and branch",
        "Pairs compose into routes, which inherit determinism and are only as "
        "faithful as their weakest pair. But routes can branch. Risk five "
        "reaches beetor two along two routes: directly, with a translator "
        "written from the instruction-set manual, and through sail, the "
        "architecture's formal model. The two translators were built "
        "independently, and that independence is a resource: agreement "
        "corroborates both routes, while disagreement localizes the bug to one "
        "pair. Branching turns several merely-checked pairs into a jointly "
        "stronger guarantee.",
    ),
    (
        "slide07",
        "The registry: 13 languages, two hubs",
        "The initial registry holds thirteen languages and thirteen pairs, "
        "organized around two reasoning hubs. Beetor two, for bit-level model "
        "checking, is reached by C through risk five, and by front ends for "
        "the sixty-four bit Arm architecture, WebAssembly, E B P F, and the "
        "Ethereum virtual machine. S M T lib, the theory-rich hub, is reached "
        "by chemical reaction networks and by a Python fragment, and a bridge "
        "connects the two hubs.",
    ),
    (
        "slide08",
        "The experiment: untrusted authors",
        "And here is the experiment. Every pair, translator, carry-back, and "
        "tests, was implemented by an independent L L M agent from a one-page "
        "brief, largely unsupervised, with the architecture's cross-checks as "
        "the only semantic gate. The platform's intended player is also an "
        "L L M: it chooses questions and routes, but can take no unchecked "
        "step. The compositional core of the calculus is mechanized in lean "
        "four. Trust comes from the architecture, not from the author.",
    ),
    (
        "slide09",
        "What the gate caught",
        "The paper reports measurements, not aspirations: per-construct "
        "coverage, counted only where a construct is both covered and "
        "faithful. Branch agreement along the dual risk five and Arm routes, "
        "with machine-derived ground truth. Certified unreachability, "
        "re-validated by a formally verified checker. And the defects the "
        "architecture caught, including one in the certificate pipeline's own "
        "checker adapter, and three in its own measuring instruments.",
    ),
    (
        "slide10",
        "Why the name",
        "Why the name? A hurdy-gurdy is an instrument whose player cranks a "
        "wheel, and the mechanism turns each choice into sound the same way, "
        "every time. The translator is the keyboard, same key, same pitch. The "
        "interpreters are the wheel. And the player, an L L M or a human, "
        "decides what to ask. Read the paper, Untrusted Authors, Trusted "
        "Answers, a Calculus of Fidelity-Graded Translations, and explore the "
        "code, the evidence, and the lean mechanization on GitHub.",
    ),
]


def configure_espeak() -> None:
    """Point phonemizer at a working espeak-ng install.

    Import misaki.espeak first: its module-level init points phonemizer at
    the espeakng-loader wheel, whose bundled dylib aborts the whole process
    on macOS, so the override below must come after.
    """
    import misaki.espeak  # noqa: F401
    from phonemizer.backend.espeak.wrapper import EspeakWrapper

    candidates = [
        (os.environ.get("ESPEAK_NG_LIBRARY"), os.environ.get("ESPEAK_NG_DATA")),
        ("/opt/homebrew/lib/libespeak-ng.dylib", "/opt/homebrew/share/espeak-ng-data"),
        ("/usr/local/lib/libespeak-ng.dylib", "/usr/local/share/espeak-ng-data"),
        ("/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1", "/usr/lib/x86_64-linux-gnu/espeak-ng-data"),
        ("/usr/lib/aarch64-linux-gnu/libespeak-ng.so.1", "/usr/lib/aarch64-linux-gnu/espeak-ng-data"),
    ]
    for lib, data in candidates:
        if lib and data and Path(lib).exists() and (Path(data) / "phontab").exists():
            EspeakWrapper.set_library(lib)
            EspeakWrapper.set_data_path(data)
            return
    sys.exit(
        "no usable espeak-ng found (the espeakng-loader wheel's dylib is "
        "broken); install one, e.g. `brew install espeak-ng`, or set "
        "ESPEAK_NG_LIBRARY and ESPEAK_NG_DATA"
    )


def _sentence_chunks(text: str, limit: int = 280) -> list[str]:
    """Greedily pack whole sentences into chunks Chatterbox handles well."""
    import re

    chunks: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if chunks and len(chunks[-1]) + len(sentence) + 1 <= limit:
            chunks[-1] += " " + sentence
        else:
            chunks.append(sentence)
    return chunks


def _kokoro_speaker():
    configure_espeak()
    from kokoro import KPipeline

    pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")

    def speak(text: str, seed: int) -> list:
        return [audio.numpy() for _, _, audio in pipeline(text, voice=VOICE)]

    return speak


def _chatterbox_speaker(ref_path: str):
    import torch

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    if device == "mps":  # checkpoints are saved for cuda; retarget the load
        _load = torch.load
        torch.load = lambda *a, **k: _load(
            *a, **{**k, "map_location": k.get("map_location", torch.device("mps"))}
        )
    from chatterbox.tts import ChatterboxTTS

    model = ChatterboxTTS.from_pretrained(device=device)
    if model.sr != SAMPLE_RATE:
        sys.exit(f"chatterbox sample rate {model.sr} != {SAMPLE_RATE}")

    def speak(text: str, seed: int) -> list:
        parts = []
        for chunk in _sentence_chunks(text):
            torch.manual_seed(seed)
            wav = model.generate(chunk, audio_prompt_path=ref_path)
            parts.append(wav.squeeze(0).cpu().numpy())
        return parts

    return speak


def synthesize(clone_ref: str | None) -> list[float]:
    """Render one wav per slide; return narration seconds."""
    import numpy as np
    import soundfile as sf

    speak = _chatterbox_speaker(clone_ref) if clone_ref else _kokoro_speaker()
    voice_label = f"cloned:{Path(clone_ref).name}" if clone_ref else VOICE
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    gap = np.zeros(int(CHUNK_GAP * SAMPLE_RATE), dtype=np.float32)

    seconds = []
    for idx, (slide_id, chapter, narration) in enumerate(SLIDES):
        chunks = speak(narration, seed=idx)
        parts = []
        for i, chunk in enumerate(chunks):
            if i:
                parts.append(gap)
            parts.append(chunk)
        audio = np.concatenate(parts)
        peak = float(np.abs(audio).max())
        if peak > 0.9:
            audio = audio * (0.9 / peak)
        sf.write(AUDIO_DIR / f"{slide_id}.wav", audio, SAMPLE_RATE)
        dur = len(audio) / SAMPLE_RATE
        seconds.append(dur)
        print(f"  {slide_id}  {dur:5.1f}s  {chapter}")

    MANIFEST.write_text(json.dumps({
        "fps": FPS,
        "leadInSeconds": LEAD_IN,
        "tailSeconds": TAIL,
        "voice": voice_label,
        "slides": [
            {"id": slide_id, "seconds": round(dur, 3)}
            for (slide_id, _, _), dur in zip(SLIDES, seconds)
        ],
    }, indent=2) + "\n")
    return seconds


def render() -> None:
    if not (REMOTION / "node_modules").exists():
        subprocess.run(["npm", "install", "--no-audit", "--no-fund"],
                       cwd=REMOTION, check=True)
    concurrency = os.environ.get("REMOTION_CONCURRENCY", "2")
    subprocess.run(
        ["npx", "remotion", "render", "Explainer", str(OUT_MP4),
         f"--concurrency={concurrency}"],
        cwd=REMOTION, check=True,
    )


def write_description(seconds: list[float]) -> None:
    chapters = []
    t = 0.0
    for (_, chapter, _), dur in zip(SLIDES, seconds):
        m, s = divmod(int(t), 60)
        chapters.append(f"{m:02d}:{s:02d} {chapter}")
        t += LEAD_IN + dur + TAIL

    (REPO / "video" / "description.txt").write_text(f"""hurdy-gurdy in a few minutes: {PAPER_TITLE}

hurdy-gurdy is a platform for deterministic, fidelity-graded translations
between formal languages, so that an LLM (or a human) can move a program to
where a question is decidable -- and reason about it there through external
interpreters and solvers -- without ever trusting an unaudited step.

This video explains the vision -- hurdy-gurdy as a two-directional experiment
in LLM-generated correctness (LLMs develop hurdy-gurdy; LLMs use hurdy-gurdy
to generate correct code), with a growth model where new language pairs are
admitted by the architecture, not the author -- and the core ideas: pairs as
commuting squares, determinism, the five fidelity grades, routes that compose
and branch, and the two reasoning hubs (BTOR2 and SMT-LIB).

Paper: "{PAPER_TITLE}: {PAPER_SUBTITLE}" by Christoph Kirsch
(arXiv preprint; built from the repository at tag arxiv.1 -- paper/arxiv.pdf)

Code, evidence, and the Lean 4 mechanization:
https://{REPO_URL}

{chr(10).join(chapters)}
""")


def main() -> None:
    args = sys.argv[1:]
    clone_ref = None
    if "--voice-clone" in args:
        i = args.index("--voice-clone")
        if i + 1 >= len(args):
            sys.exit(__doc__)
        clone_ref = args[i + 1]
        del args[i:i + 2]
        if not Path(clone_ref).exists():
            sys.exit(f"no such reference audio: {clone_ref}")

    mode = args[0] if args else ""
    if mode not in ("", "--audio-only", "--render-only") or len(args) > 1:
        sys.exit(__doc__)

    if mode == "--render-only":
        manifest = json.loads(MANIFEST.read_text())
        seconds = [s["seconds"] for s in manifest["slides"]]
    else:
        seconds = synthesize(clone_ref)

    if mode != "--audio-only":
        render()
        size_mb = OUT_MP4.stat().st_size / 1e6
        print(f"\nwrote {OUT_MP4}  ({size_mb:.1f} MB)")

    write_description(seconds)
    print(f"wrote {REPO / 'video' / 'description.txt'}")


if __name__ == "__main__":
    main()
