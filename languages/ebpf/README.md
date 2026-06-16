# Language — eBPF

eBPF bytecode: the in-kernel register VM, as a **bytecode** source
language. Source of `ebpf-btor2`. Initial scope is the arithmetic / jump /
load-store core (no `CALL` / helper calls); unsupported opcodes abort
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

## Public benchmarks

Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): the Linux kernel
**BPF selftests** (`tools/testing/selftests/bpf`), pinned to a kernel tag,
including the **verifier reject** cases — which exercise the typed-abort /
rejection boundary, not just accepted programs.

## Pairs over this language

- [`ebpf-btor2`](../../pairs/ebpf-btor2/README.md) — source.
