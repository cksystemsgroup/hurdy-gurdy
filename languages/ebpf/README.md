# Language — eBPF

eBPF bytecode: the in-kernel register VM, as a **bytecode** source
language. Source of `ebpf-btor2`. Scope is the arithmetic / jump /
load-store core plus byte-swap (`BPF_END`), the legacy `ABS`/`IND` packet
loads, and the `CALL` (helper-call) instruction. A helper return is modeled as
a fresh program input (see the interpreter section); malformed opcodes abort
loading rather than translate unsoundly.

## Formal semantics (source of truth)

The eBPF instruction-set semantics: a 64-bit register machine (`r0`–`r10`),
defined arithmetic (including the wrapping / division-by-zero conventions
the kernel fixes), jumps, and memory access over a bounded stack/maps. The
authoritative behavior is the kernel's eBPF ISA, now also captured by the
mechanized models below.

## Formal model — no Sail, use the Coq mechanization

eBPF is not an ISA Sail targets. Its strongest mechanized references are:

- **CertrBPF / CertFC** — a **Coq/Gallina** semantics of rBPF with a
  *verified interpreter*, refined and extracted to C through CompCert
  (an end-to-end verified VM). The recommended gold oracle.
- **Jitterbug** — a **Rosette** model used to verify eBPF JITs for several
  architectures (specifies JIT correctness rather than a reference
  interpreter).

Use CertrBPF as the external oracle for the shared eBPF interpreter; a
`ebpf → certrbpf-model → …` route is a possible fidelity-raising branch.

## Shared interpreter

**Role: source.** A deterministic eBPF executor over an input binding → a
trace of post-step register/memory states ([`ARCHITECTURE.md`](../../ARCHITECTURE.md)
§5), validated against CertrBPF (or the kernel's own interpreter). Shared by
every eBPF pair.

*Status: **partial** (interpreter **v0.4**) — the ALU / jump / load-store
core plus byte-swap, the legacy `ABS`/`IND` packet loads, and `CALL` is built
(`gurdy/languages/ebpf/`, tests in `tests/test_ebpf_interp.py`): the
11-register machine, ALU64 / ALU32 (with the kernel-defined `DIV`/0 and
`MOD`/0 edges), byte-swap (`BPF_END`: `le`/`be` on ALU, unconditional `bswap`
on ALU64, at 16/32/64, over a fixed little-endian host model), the conditional
jumps + `JA` / `EXIT`, `LDDW`, the MEM-mode loads/stores, the classic
socket-filter packet loads (`LD|{ABS,IND}|{B,H,W}`: big-endian reads into
`r0`, with the out-of-bounds drop edge — `r0`=0, halt), and `CALL`. The
**helper-call model** (v0.4): a `CALL` is modeled uniformly for every helper id
— its return `r0` and the clobbered caller-saved `r1`–`r5` are fresh **program
inputs** read from the per-call `helper_inputs` stream (consumed the same way
the initial registers / the packet are inputs); `r6`–`r9` and the frame pointer
`r10` are preserved; `pc`+1. The id is recorded but does not constrain the
result (a sound over-approximation of any helper). (v0.3 -> v0.4 bump: `CALL`
added additively; v0.2 -> v0.3: `ABS`/`IND` packet loads; v0.1 -> v0.2:
byte-swap; AGENTS.md §3.)*

## Public benchmarks

Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): the Linux kernel
**BPF selftests** (`tools/testing/selftests/bpf`), pinned to a kernel tag,
including the **verifier reject** cases — which exercise the typed-abort /
rejection boundary, not just accepted programs.

## Pairs over this language

- [`ebpf-btor2`](../../pairs/ebpf-btor2/README.md) — source.
