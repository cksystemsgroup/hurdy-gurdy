# Pair — `ebpf-btor2`  ·  eBPF → BTOR2

*Status: **partial** — the ALU / jump / load-store core plus byte-swap, the
legacy `ABS`/`IND` packet loads, and the `CALL` (helper-call) instruction are
built (`gurdy/pairs/ebpf_btor2/`, tests in `tests/test_ebpf_btor2_pair.py`):
ALU64 and ALU32 (reg/imm, with 32-bit zero-extension and the eBPF-defined
`DIV`/0 -> 0 and `MOD`/0 -> destination-unchanged edges), byte-swap (`BPF_END`:
`le`/`be` on ALU and unconditional `bswap` on ALU64, at 16/32/64), the
conditional jumps (JMP/JMP32) plus `JA` and `EXIT`, `LDDW`, the MEM-mode
loads/stores, the classic socket-filter packet loads (`LD|{ABS,IND}|{B,H,W}`:
big-endian reads into `r0` from a constant packet `Array bv64 bv8`, with the
out-of-bounds drop edge), and `CALL` (helper-return-as-input — see below) are
lowered to a BTOR2 transition system (PC-keyed ITE dispatch over `r0`–`r10`,
data memory and the packet as `Array bv64 bv8`, per-call-site BTOR2 inputs).
Construct coverage is **126/126** over the spec-derived inventory (was 124/124
before this widening: +2 = `CALL` known/other helper ids); the commuting square
is validated against the shared eBPF interpreter, and the emitted `bad` is
decided end-to-end through the `btor2-smtlib` bridge. The in-scope construct
set is now complete — no eBPF construct in scope hard-aborts. Ported from v2;
byte-swap added on shared eBPF interpreter v0.2; packet loads on v0.3; CALL on
v0.4.*

**`unsupported` histogram** (constructs that still hard-abort, BENCHMARKS.md
§3): *empty* — `ebpf:call` was the last pending construct and is now covered
(the previously-listed `ABS`/`IND` packet-load forms were covered in the prior
widening). Nothing was dropped (coverage ratchet, BENCHMARKS.md §5). Genuinely
malformed encodings still hard-abort with a typed `unsupported` (e.g. a
`BPF_END` at a non-{16,32,64} width, a packet `LD|ABS|DW` double-word form, an
unknown ALU/JMP op nibble).

Translate eBPF bytecode into a BTOR2 transition system. Scope is the
arithmetic / jump / load-store core plus byte-swap (`BPF_END`), the legacy
`ABS`/`IND` packet loads, and `CALL`; malformed encodings abort loading rather
than translate unsoundly.

## CALL — the helper-return-as-input model (the human-decided semantics)

A `CALL` is modeled **uniformly for every helper id** — there is no per-helper
table and no `unsupported: ebpf:call` for any id (known or unknown). The model
(decided by a human; implemented exactly, not re-litigated):

- **Helper return `r0` = a fresh symbolic program input.** Each call site's
  return value is a new free input, consumed *identically* by the shared eBPF
  interpreter `I_s` (from a per-call helper-effect stream, `binding`
  `helper_inputs`) and by the BTOR2 model `T` (fresh per-call-site BTOR2
  `input` nodes `call{i}_r0`). The helper id (in `imm`) is recorded in the
  decode/trace but does **not** constrain `r0`: the return is unconstrained.
- **Standard ABI for the rest.** The caller-saved `r1`–`r5` are **clobbered**
  — set to fresh per-call inputs too (`call{i}_r1`..`call{i}_r5`), so `I_s` and
  `T` agree on them deterministically; the callee-saved `r6`–`r9` and the frame
  pointer `r10` are **preserved**; `pc` advances by one instruction.
- **One source of truth, mirrored.** `T`'s `CALL` lowering
  (`_effect` in `translate.py`) and the interpreter's `_helper_effect`
  (`interp.py`) both draw `r0`/`r1`–`r5` from the same per-call helper input and
  preserve `r6`–`r10`. `L` (`helper_inputs_from_behavior` in `lift.py`) recovers
  the consumed helper inputs from the BTOR2 behavior — the call site wrote its
  fresh inputs into `r0`–`r5`, so the post-cycle `r0`–`r5` *are* the stream —
  and replaying that stream through `I_s` reproduces the run (the square on the
  witness, the carry-back). The BTOR2 `input` nodes are free **per cycle**, so a
  call site inside a loop reads a fresh return each iteration, matching the
  interpreter's dynamic stream order.

**Soundness / over-approximation.** Because the helper return is an
unconstrained input, the BTOR2 model **over-approximates any real helper**: the
solver explores *all* possible helper returns. This is a sound abstraction for
**safety verification** — if no `bad` is reachable under any helper return, none
is reachable under the real helper, so **no real bug is missed**. The cost is
possible **false positives**: a `bad` reported reachable may depend on a helper
return the concrete helper can never produce (the carried-back witness then
exhibits that helper input, so the player can inspect it). The deterministic
commuting square `I_s(p) == L(I_t(T(p)))` still holds because both sides read
the *same* helper input at each call.

The byte-swap lowering (`_end_lower` in `translate.py`) mirrors the
interpreter's `byteswap`/`_end` (its single source of truth) from one
per-construct definition, over a fixed **little-endian host** model: `le`
truncates the low *width* bits with no reorder, `be`/`bswap` reverse the byte
order, all zero-extending into the 64-bit destination (RFC 9669 §"Byte swap
instructions"). The cross-check (`square()`) runs both on the same programs
and asserts agreement under `π`.

The packet-load lowering (`_pkt_load_be` / `_pkt_in_bounds` in `translate.py`,
mirroring the interpreter's `pkt_load_be` / `pkt_in_bounds`) reads the packet
in **big-endian** (network) byte order: `LD|ABS|sz` at absolute offset `imm`,
`LD|IND|sz` at `src + imm`, with `sz ∈ {1,2,4}` zero-extended into `r0`. The
packet is a constant BTOR2 state array (no `next`, so it never changes); its
length is a program constant. An out-of-bounds access (`offset < 0` or
`offset + sz > pkt_len`) takes the **defined drop edge** — `r0` is cleared and
the program halts (the classic socket filter's "drop the packet" return) —
kept distinct from the typed `unsupported` abort. The unsigned bounds form
(`addr < pkt_len ∧ addr + sz ≤ pkt_len`) is faithful because a negative source
offset wraps to a huge `bv64` value that `addr < pkt_len` rejects.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** eBPF — [`languages/ebpf`](../../languages/ebpf/README.md).
- **Target.** BTOR2 — [`languages/btor2`](../../languages/btor2/README.md).
- **Translator `T`.** A spec-derived per-opcode lowering from eBPF bytecode
  (+ scope) to a BTOR2 transition system: state for `r0`–`r10`, a bounded
  stack/memory as an array, a constant packet array (when the program does
  legacy packet loads), per-call-site `input` nodes (when the program calls a
  helper), `pc`, a halt flag; PC-keyed dispatch; init/next/constraint/bad.
  Deterministic and schema-predictable.
- **Source interpreter.** The **shared** eBPF interpreter
  ([`languages/ebpf`](../../languages/ebpf/README.md)) — reused; contributed
  by this pair if first. Consumes the per-call `helper_inputs` stream for
  `CALL` exactly as it consumes the initial registers / the packet (more
  program inputs).
- **Target interpreter.** The **shared** BTOR2 interpreter — reused (its
  `input` op + per-cycle input binding model the helper returns; unchanged).
- **Target-to-source interpreter `L`.** Decodes a BTOR2/solver witness into
  an eBPF behavior (entry registers + the reaching run / halt cycle), and
  recovers the per-call helper-return inputs (`helper_inputs_from_behavior`)
  so a replay through `I_s` reproduces the run. Pair-owned.

## Projection `π`

Post-step `r0`–`r10`, memory observables, and halt — the eBPF interpreter's
observables mapped onto the BTOR2 state variables.

## Fidelity target + evidence

- **`checked`** — the commuting-square oracle under `π` on a corpus.
- Certificates lift discharged questions to `proved`.

## Soundness story

Lowering vs. witness replay cross-check under `π`; the shared eBPF
interpreter is anchored to **CertrBPF** (the Coq rBPF reference) or the
kernel interpreter ([`languages/ebpf`](../../languages/ebpf/README.md),
[`PAIRING.md`](../../PAIRING.md) §6). For `CALL` the soundness story is the
**helper-return-as-input over-approximation** above: `T` and `I_s` read the
same free helper input at each call, so the square commutes deterministically;
the abstraction is sound for safety (no real bug missed) at the cost of
possible false positives, each carried back as a concrete helper-input witness.

## Notes for the implementing agent

- Reuse the BTOR2 core; contribute the shared eBPF interpreter validated
  against CertrBPF.
- Keep malformed/out-of-scope encodings a hard load-time abort — never a
  silent unsound lowering. (`CALL` is *in scope* and modeled uniformly; it is
  not an abort.)
- Model a helper return as a program input, not a specific helper's semantics:
  one free `input` per call site (per cycle), mirrored in `I_s`, `T`, `L`.
