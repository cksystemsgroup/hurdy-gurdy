"""Verify the pair imports and registers cleanly when z3 is absent.

CI environments without z3 must still be able to load the pair —
the BMC backend is gated on z3 at dispatch time, not at import.
"""

import subprocess
import sys
import textwrap


def test_pair_imports_without_z3():
    """Run a subprocess that blocks z3, then imports the pair."""
    script = textwrap.dedent(
        """
        import builtins
        _real_import = builtins.__import__

        def _block_z3(name, *args, **kwargs):
            if name == "z3" or name.startswith("z3."):
                raise ImportError("z3 deliberately blocked for this test")
            return _real_import(name, *args, **kwargs)

        builtins.__import__ = _block_z3

        # Importing the pair must succeed even with z3 absent.
        import gurdy.pairs.riscv_btor2  # noqa: F401
        from gurdy.core.pair import list_pairs

        assert "riscv-btor2" in list_pairs()

        # Dispatching against the Z3 BMC backend with z3 absent must
        # return a structured error, not raise.
        from gurdy.pairs.riscv_btor2.solvers.z3bmc import Z3BMCSolver

        class _D:
            engine = "z3-bmc"
            bound = 5
            timeout = None

        raw = Z3BMCSolver().dispatch(b"", _D())
        assert raw.verdict == "error"
        assert "z3" in (raw.reason or "").lower()
        print("ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, (
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "ok" in result.stdout
