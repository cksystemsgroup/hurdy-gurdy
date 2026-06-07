# `evm-btor2` benchmark scope

This is the §9.1 instantiation of [BENCHMARKING.md](../../BENCHMARKING.md)
for the `evm-btor2` pair. It defines what the benchmark covers and,
just as importantly, what it does not.

## 1. Source language and dialect

- **Spec**: Ethereum Virtual Machine, Yellow Paper + EIPs.
- **Target hard fork**: Shanghai (PUSH0 / EIP-3855 enabled) at P1.
  Cancun (BLOBHASH, MCOPY, transient storage) deferred to a
  schema-bump P14+.
- **Subset in scope (P1 schema v1.0.0)**:
  - All arithmetic opcodes (`ADD`, `MUL`, `SUB`, `DIV`, `SDIV`,
    `MOD`, `SMOD`, `ADDMOD`, `MULMOD`, `EXP`, `SIGNEXTEND`).
  - All comparison and bitwise (`LT`, `GT`, `SLT`, `SGT`, `EQ`,
    `ISZERO`, `AND`, `OR`, `XOR`, `NOT`, `BYTE`, `SHL`, `SHR`,
    `SAR`).
  - SHA3 / KECCAK256 (modeled as an uninterpreted function with
    injectivity axiom; spec may pin concrete inputs).
  - Environment opcodes (`ADDRESS`, `BALANCE`, `ORIGIN`, `CALLER`,
    `CALLVALUE`, `CALLDATALOAD`, `CALLDATASIZE`, `CALLDATACOPY`,
    `CODESIZE`, `CODECOPY`, `GASPRICE`, `CHAINID`, `SELFBALANCE`,
    `BASEFEE`) — pinned by spec or `Free`.
  - Block opcodes (`BLOCKHASH`, `COINBASE`, `TIMESTAMP`, `NUMBER`,
    `PREVRANDAO`, `GASLIMIT`) — `Free` or pinned.
  - Stack / memory / storage (`POP`, `MLOAD`, `MSTORE`, `MSTORE8`,
    `SLOAD`, `SSTORE`, `MSIZE`, `JUMP`, `JUMPI`, `PC`, `GAS`,
    `JUMPDEST`, `PUSH0`–`PUSH32`, `DUP1`–`DUP16`, `SWAP1`–`SWAP16`).
  - `LOG0`–`LOG4` (observable side effect; recorded in trace).
  - `RETURN`, `REVERT`, `STOP`, `INVALID`, `SELFDESTRUCT`.
- **Out of scope at P1** (stable exclusions, lift with schema bumps):
  - `CALL`, `CALLCODE`, `DELEGATECALL`, `STATICCALL`,
    `CREATE`, `CREATE2` — deferred to P11. Modeled as
    uninterpreted functions over storage / return data.
  - Precompiles beyond identity (modeled as `Free` imports).
  - Cancun opcodes (`MCOPY`, `BLOBHASH`, `TLOAD`, `TSTORE`).
  - Multi-transaction sequences (only single-transaction
    properties at P1).
- **Source artifact**: deployed bytecode (`bytes`), plus an
  `AnalysisScope` selecting the entry function selector and an
  optional `included_callees` set (function selectors within the
  same contract reachable via internal `JUMP`).

## 2. Reasoning language and solver inventory

- **Reasoning language**: BTOR2, schema version `1.0.0`. Layered
  shape (header / machine / library / dispatch / init / constraint
  / bad / binding) with an EVM-specific machine layer:
  - **Stack**: modeled as `Array bv8 bv256` (1024-deep) with
    explicit SP, or unrolled to fixed depth when bound is small.
  - **Memory**: `Array bv256 bv8` (byte-addressed, expandable).
  - **Storage**: `Array bv256 bv256`. Per-contract.
  - **Calldata**: `Array bv256 bv8` plus a `calldatasize bv256`.
  - **PC**: `bv32` (32-bit instruction offset is overkill but
    matches EVM's max contract size 24 KiB easily).
  - **Gas**: `bv256` (or `bv64` if the corpus doesn't exercise
    huge gas).
  - **Trap flag**: `bv1`. Set on invalid jumpdest, OOG,
    stack overflow/underflow, `REVERT`, `INVALID`.

- **Solver inventory** (target):

| Engine        | Backend          | Role |
|---------------|------------------|------|
| `z3-bmc`      | z3 4.16.0        | BMC; default. |
| `z3-spacer`   | z3 4.16.0        | Inductive (Horn). |
| `bitwuzla`    | 0.9.0+           | **Likely primary**: 256-bit bv arithmetic is bitwuzla's strongest suit. |
| `cvc5`        | 1.3.3+           | BMC alternative; second-vendor cross-check. |
| `pono`        | 2.0.0-beta+      | Subprocess BMC + k-induction. |

The §9.12 cross oracle dispatches every task on every compatible
engine.

## 3. Property language

A `QuestionSpec` for `evm-btor2` targets one of:

- **`reach(revert)`** — does the contract `REVERT` within
  `bound` opcodes?
- **`reach(storage_predicate)`** — does a storage slot ever
  satisfy a predicate (e.g., `storage[balanceOf[attacker]] >
  10^18`)?
- **`reach(log_predicate)`** — does a `LOG` event ever fire
  matching a predicate (e.g., `Transfer(from, to, amount)` with
  attacker-controlled `to`)?
- **`safety(invariant)`** — does an invariant hold at every step?
  Inductive engines required. Example: total supply conservation.

Witness format: a sequence of `(input_binding, opcode_index)`
pairs naming the calldata / caller / value / storage cells the
lifter reads.

## 4. Corpus structure

```
bench/evm-btor2/corpus/
  seed/
    0001-pre-0.8-overflow/
      task.toml         # ground truth, expected, notes
      task.bin          # deployed bytecode hex
      task.source.sol   # source (kept for review only)
      task.solc-version # pinned solc version
      task.spec.json    # the QuestionSpec
    0002-storage-pack-aliasing/
    ...
  external/
    etherscan-0x.../    # streamed verified-source contracts
    ...
```

Seed tasks pinpoint a single wedge claim (Solidity↔EVM gap).
External tasks come from Etherscan verified-source contracts via
the streaming recipe.

## 5. SOTA baselines

Mandatory comparison baselines:

- **Solidity SMTChecker** — built into `solc`. Source-level.
  Adapter compiles via pinned solc and invokes `solc --model-checker-engine bmc`.
- **hevm** — best-effort install (Haskell). Closest thesis competitor;
  bytecode-level symbolic execution.
- **Manticore-EVM** — `pip install manticore`. Skip-with-note if
  not on PATH.
- **Mythril** — `pip install mythril`. Bug-finding baseline.

Each baseline gets one adapter under `bench/evm-btor2/baselines/`.

## 6. The wedge class to chase

The Solidity↔EVM semantic-gap class — the analogue of
`riscv-btor2`'s C-UB-but-RV64-defined cluster. Examples:

- **Pre-0.8 overflow**: `a + b` silently wraps in solc ≤ 0.7;
  SMTChecker (with default config and pre-0.8 source) may treat
  the operation as unbounded. Bytecode level shows the modular
  wrap.
- **Storage packing**: two `uint128` co-located in one slot;
  source-level reasoning loses the bit-precise aliasing.
- **`delegatecall` storage collision**: caller's storage layout
  != callee's; source-level cannot see the layout mismatch.
- **ABI decoding**: short calldata, malformed dynamic arrays;
  source-level often assumes well-formed inputs.
- **PUSH0 vs no-PUSH0**: same Solidity source compiled with
  different EVM versions; different bytecode, different
  verification answer.
- **Inline-assembly Yul blocks**: SMTChecker explicitly skips;
  bytecode-level catches them.

For each, the corpus must contain at least one task where the
source-level verifier produces a wrong verdict (or a "don't
know") while hurdy-gurdy on the bytecode produces the correct
verdict.

## 7. Out-of-scope properties

- **Gas-bound properties (timing)** — modeled but not the
  primary target until P10+. EVM gas is a defined quantity, so
  this is in scope eventually.
- **Inter-contract state-machine properties** — single contract
  only at P1; multi-contract via a future schema bump (P11).
- **Block-level / multi-transaction properties** — single
  transaction at P1.
- **MEV-style attacks** (front-running, sandwich) — out of scope.
- **Cryptographic properties** (signature soundness,
  zk-proof verification) — out of scope; modeled as `Free`.
