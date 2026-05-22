"""Linux in-kernel eBPF verifier baseline adapter.  P14+.

Loads programs via bpf(BPF_PROG_LOAD) for verifier feedback only.
Never attaches to live hooks.  Skips with note when CAP_BPF is absent.
"""
# Not implemented yet — see V2_BOOTSTRAP.md §6 P14 and §11.
raise NotImplementedError("kernel_verifier baseline not implemented (P14+)")
