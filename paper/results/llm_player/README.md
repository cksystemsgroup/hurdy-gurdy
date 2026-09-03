# The LLM-player experiment (paper §"An LLM plays the platform")

A first, deliberately small controlled evaluation of the *player* half of
the paper's two-directional experiment: can an LLM, handed the platform,
produce correct conclusions whose trust rests on machine-checked evidence
rather than on the model's say-so?

## Protocol

- **Questions**: `questions.json` — 12 reachability questions with
  platform-established ground truth (6 REACHABLE / 6 UNREACHABLE): RISC-V
  loop/signedness/load-width (R1–R6, ground truth corroborated along BOTH
  RISC-V routes), eBPF square-residue and bounded-factorization (E1–E4),
  Python assert-violability (P1–P2). Traps were chosen where plausible
  unaided reasoning errs (srli vs srai, lb vs lbu, strict bounds,
  factorization of a ~2^30 prime).
- **Subject**: fresh, context-free frontier-LLM agents (same model family
  as the platform's builders — a stated limitation). One agent per
  question per arm; 24 runs; no retries; no cherry-picking.
- **Arm A (unaided)**: the question text only; instructed to answer by
  reasoning alone, no tools/files/code; answer as
  `VERDICT: ... / CONFIDENCE: high|medium|low`.
- **Arm B (player)**: the same question, the repository path, and the
  head-construction snippet from `questions.json`; instructed to decide
  *via the platform* (both routes where two exist; the proved tier for
  expected-unreachable eBPF questions; witness replay where applicable)
  and report `VERDICT` + `EVIDENCE`.
- **Grading**: verdict vs ground truth; for arm B, whether the platform
  actually ran and what artifact the answer rests on (see
  `transcripts.md` for the full final messages).

## Results

`results.json`. Both arms 12/12. The headline is the *evidence class*,
not accuracy: every arm-A answer rests on the model's reasoning (all
delivered at high confidence — confidence would not have flagged an
error); every arm-B answer carries a checked artifact (two-route
agreement with bounded-k hedging, witness replays, tier-raises to
`proved` with a 17 MB LRAT re-validated by cake_lpr on E3). On E3, arm A
was right by *recall* (1073741789 is the largest prime below 2^30) —
exactly the kind of evidence the calculus cannot grade.

## Limitations (stated in the paper)

1. The protocol scripts which platform entry points to use; players
   execute and interpret rather than discover the platform cold.
2. Subject model from the builders' family.
3. 12 small questions cannot separate the arms on correctness; scaling
   to unaided-failure difficulty is named future work.
