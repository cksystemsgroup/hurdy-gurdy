# Software

Hurdy-gurdy was co-developed at the Department of Computer Sciences of the University of Salzburg and at the Faculty of Information Technology of the Czech Technical University in Prague (CTU), where it was developed under the project Robotics and Advanced Industrial Production (Roboprox, reg. no. CZ.02.01.01/00/22_008/0004590), research objective RO 12.1.

## Hurdy-gurdy

- **Title of output:** Hurdy-gurdy – a checker-trusted platform for LLM-generated translators and solvers between formal languages
- **Registration number / Internal identifier:** V3S registration pending, to be submitted under the title "Hurdy-gurdy – a checker-trusted platform for LLM-generated translators and solvers between formal languages"
- **Version:** main branch (no tagged release)
- **Project title:** Robotics and Advanced Industrial Production
- **Project registration number:** CZ.02.01.01/00/22_008/0004590
- **Type of result:** software
- **Date of publication:** 28.04.2026
- **Authors and contributors:** Christoph Kirsch, University of Salzburg, Department of Computer Sciences, and Czech Technical University in Prague, Faculty of Information Technology, ORCID 0000-0002-0961-0564; contact: christoph.kirsch@fit.cvut.cz
- **Keywords:** formal verification; model checking; large language models; BTOR2; SMT-LIB; RISC-V; certified translation; Lean
- **URL of storage location:** https://github.com/cksystemsgroup/hurdy-gurdy

**Description (originality and distinctiveness):**

Hurdy-gurdy is a platform in which LLM agents generate translators between formal languages (C, RISC-V, BTOR2, SMT-LIB and others) as well as solving procedures, while all generated code is treated as untrusted. Correctness is established only by checking results through interpreters and certificate checkers, so answers remain trustworthy even though their authors are not. The core calculus of fidelity-graded translations is mechanized in Lean. Applied to 110 hardware model checking benchmarks, the platform answered 82 of them. Hurdy-gurdy generalizes our earlier Roboprox tools Rotor (RISC-V-to-BTOR2 model generator) and Bitme (bounded model checker).

**Relevance to the project (RO 12.1 – Scalable Symbolic Execution through Bounded Model Checking):**

RO 12.1 aims at scalable symbolic execution of machine code by translating it into bounded model checking problems and serving as a platform for engaging symbolic reasoning technology. Hurdy-gurdy generalizes our RO 12.1 toolchain (Rotor and Bitme) from a fixed RISC-V-to-BTOR2 pipeline to arbitrary translation routes between code and reasoning languages, generated automatically by LLM agents. Because every result is checked independently, the platform scales the range of code and solvers that can be engaged without compromising the guarantee that dangerous states are never reached.

- **Link to technical documentation:** https://github.com/cksystemsgroup/hurdy-gurdy/blob/main/README.md and https://github.com/cksystemsgroup/hurdy-gurdy/blob/main/KERNEL.md
- **License:** MIT License
- **System requirements:** Python 3 (kernel uses the standard library only); Lean 4 for the mechanized proofs; optional C/Rust accelerators; benchmark oracles (btormc, clang, Sail RISC-V model) for reproducing campaigns; Linux or macOS.
- **Type of interface/API:** command-line interface (`python3 -m kernel.driver admit | play | regrade | report | graph | base`)
- **Links to related publications and/or datasets:** "Untrusted Authors, Trusted Answers: A Calculus of Fidelity-Graded Translations", arXiv:2607.14137 (2026); benchmarks: HWMCC'24, SV-COMP'25
- **Naming convention of files/software:** repository `hurdy-gurdy`; kernel in `kernel/`, Lean mechanization in `kernel/mechanization/`, benchmark oracles in `oracles/bench/`, campaign runs in `runs/<name>`
