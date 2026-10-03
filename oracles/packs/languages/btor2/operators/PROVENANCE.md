# `btor2` operator tables — recorded testimony (2026-10-03)

- **What**: `checks.jsonl`, 301 checks. Each is one BTOR2 operator on
  constants compared with the value SMT-LIB's QF_BV definitions give
  it; `build.py` computes the expected values from those definitions
  and from no interpreter in the registry.
- **Oracle**: `btormc` 3.2.4 on the host, `-kmax 0`, outside the seal.
  Every check was written as a machine of its own, twice — bad when
  the operator equals the expected value, bad when it differs. btormc
  reports the first reachable (`sat`) and the second not (no output)
  on all 301. No dispute.
- **Why**: fault injection (`kernel/faults`, 2026-10-03) left 20 of 100
  sampled mutants of `btor2@5`'s interpreter unrefused: operators no
  vector observed and corners none reached.
- **Where it entered**: `registry/languages/btor2@6`, by revision.
  Vectors 012-017 are the six families, each the conjunction of its
  checks as the bad property. The same tables over states frozen at
  the constants, bad negated, are certificate vectors for both
  checkers (`induction` 007-018, `clauses` 005-010); btormc reaches no
  bad within two frames on any of them.
- **Not from btormc**: vector 018 (one half-and-half array reached
  from either default, equal by extensionality). btormc refuses a
  positive equality over two constant arrays; z3 4.13.0 (python
  module, host) says `a != b` is unsat for the two store chains.
- **Status**: testimony (`KERNEL.md` §6). Nothing here executes in the
  kernel. Re-derive by running `build.py` on a host with btormc.
