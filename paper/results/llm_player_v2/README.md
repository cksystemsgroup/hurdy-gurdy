# The LLM-player experiment, v2 — unscripted, over MCP

The second controlled evaluation of the *player* half of the paper's
two-directional experiment, designed to remove the first experiment's
two protocol limitations (`../llm_player/README.md`): the entry points
are no longer scripted, and the questions are hardened until unaided
reasoning actually fails.

## Protocol

- **Questions**: `questions.json` — 8 bounded reachability questions
  over BTOR2 systems given verbatim in the question text (4 REACHABLE /
  4 UNREACHABLE): constraint-guarded modular counters where the bound
  and the per-frame constraint semantics both matter (Q1–Q2), 17-bit
  bounded factorization of a semiprime and of a prime (Q3–Q4), three
  HWMCC instances verbatim — trex02-1, phases_2-1, and the
  negated-refs beem adding.5 (Q5–Q7) — and a 7-step 64-bit LCG orbit
  (Q8). Ground truth was platform-established before any run: every
  question decided by BOTH the SMT bridge (z3) and btormc with
  agreeing verdicts, reachable witnesses replayed.
- **Subject**: fresh, context-free frontier-LLM agents (same model
  family as the platform's builders — still a stated limitation). One
  agent per question per arm; 16 graded runs; no retries of graded
  runs; no cherry-picking.
- **Arm A (unaided)**: the question text only; instructed to answer by
  reasoning alone, no tools/code/files; `VERDICT / CONFIDENCE / WHY`.
- **Arm B (player, v2 — UNSCRIPTED)**: the same question, the
  repository path, and one rule: interact with the platform **only
  through its MCP server** (`python3 -m gurdy mcp`, JSON-RPC 2.0 over
  stdio). No head-construction snippets, no named entry points, no
  reading the repository's source or docs — tool discovery is part of
  the task. Report `VERDICT + EVIDENCE` (tools called, decisive
  artifact, hedging the evidence class requires).
- **Grading**: verdict vs ground truth; for arm B, whether the MCP
  surface was actually the sole interface and what artifact the answer
  rests on. Full final messages in `transcripts.md`.

## Results

`results.json`. **Arm A: 7/8. Arm B: 8/8.**

The separation the first experiment could not produce: on Q4 (does
1676656651 factor with both factors in [2, 131071]?) the unaided arm
exhausted hand arithmetic — trial division to ~1000, a Fermat pass —
and then *guessed* REACHABLE on the meta-heuristic that benchmark
constants are usually planted semiprimes (wrong: the constant is
prime; 34 minutes, and the only run at low confidence). The player arm
returned the machine verdict `unreachable` at k=2, hedged it correctly
as a bounded UNSAT with no witness to replay, and — unprompted —
devised a positive control (the same system with constant 15 must be
and was reachable, witness_ok) to rule out a vacuous pipeline.

Every arm-B agent, cold, wrote a stdlib JSON-RPC driver, discovered
the 10-tool surface, picked `reach`, and articulated the evidence
asymmetry the calculus is built on (a replayed witness needs no
hedging; a bounded unreachable rests on the bridge's UNSAT). Emergent
behaviors nobody scripted: k-bracketing to pin the bound convention
(Q2: 30/35/36/40), input-pinning to machine-check hand-derived
factors (Q3), positive controls against vacuous negatives (Q4, Q5,
Q7), calibration probes for negated-ref semantics (Q7), and an
independent recomputation cross-check (Q8).

Arm A remains formidable: it decoded two HWMCC pc-encodings cold
(Q5, Q6), recognized the beem adding protocol and bounded its growth
(Q7), and iterated a 64-bit LCG seven times by hand, digit-exact
(Q8). Its one failure was exactly where the platform's floor is
higher than any amount of unaided cleverness: a refutation that needs
a solver. Honest note: this time low confidence *did* flag the wrong
answer — one instance, not a calibration claim.

## Honesty notes

1. Q5's arm-A prompt contained a transcription slip (the bad line
   appeared once garbled, with an inline correction giving the exact
   line); the agent used the corrected line. Arm B's Q5 prompt was
   clean.
2. The first launches of arm B Q5–Q8 died on an infrastructure rate
   limit before producing any verdict or tool call; they were
   relaunched as fresh agents. No graded run was retried.
3. Subject model is still from the builders' family; 8 questions is
   still small. What v2 fixes is the protocol (unscripted discovery)
   and the difficulty floor (one unaided failure), not the scale.
4. Ground truth and arm B share the platform's deciders (bridge +
   btormc agreement, witness replay); as in v1, arm B can fail
   essentially only by mis-operating the tools. The discriminating
   arm is A.
