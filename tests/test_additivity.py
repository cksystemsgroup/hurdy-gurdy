"""The syntactic additivity checker (tools/additivity.py) — Phase 5 of the
scaling rollout (SCALING.md §6, Lane A). The core is a pure
``(old_src, new_src) -> verdict`` function, so these tests are git-free and
stable across rebases.
"""

import importlib.util
import pathlib
import sys
import textwrap
import unittest


def _load():
    path = pathlib.Path(__file__).resolve().parent.parent / "tools" / "additivity.py"
    spec = importlib.util.spec_from_file_location("additivity", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["additivity"] = mod
    spec.loader.exec_module(mod)
    return mod


def _src(s: str) -> str:
    return textwrap.dedent(s).strip() + "\n"


class TestAdditivity(unittest.TestCase):
    def setUp(self):
        self.ad = _load()

    def classify(self, old, new):
        return self.ad.classify_source(_src(old), _src(new))

    # --- additive cases (Lane A) ------------------------------------------

    def test_new_toplevel_def_and_binding_is_additive(self):
        r = self.classify(
            "X = 1\ndef f():\n    return X",
            "X = 1\nY = 2\ndef f():\n    return X\ndef g():\n    return Y")
        self.assertTrue(r["additive"])
        self.assertEqual(r["reasons"], [])
        joined = " ".join(r["additions"])
        self.assertIn("bind Y", joined)
        self.assertIn("def g", joined)

    def test_new_guard_clause_branch_is_additive(self):
        # The exact shape of an opcode widening: a new `if` block inserted before
        # the final raise, existing branches untouched.
        r = self.classify(
            """
            def dispatch(op):
                if op == 1:
                    return "a"
                raise ValueError(op)
            """,
            """
            def dispatch(op):
                if op == 1:
                    return "a"
                if op == 2:
                    return "b"
                raise ValueError(op)
            """)
        self.assertTrue(r["additive"], r["reasons"])
        self.assertTrue(any("If@" in a for a in r["additions"]))
        self.assertTrue(any("dispatch" in a for a in r["additions"]))

    def test_version_bump_is_allowed(self):
        r = self.classify('INTERP_VERSION = "0.9"', 'INTERP_VERSION = "0.10"')
        self.assertTrue(r["additive"])
        self.assertTrue(any("version bump" in a for a in r["additions"]))

    def test_docstring_edit_is_ignored(self):
        r = self.classify(
            'def f():\n    "old doc"\n    return 1',
            'def f():\n    "new and longer doc"\n    return 1')
        self.assertTrue(r["additive"])
        self.assertEqual(r["additions"], [])   # no behavioural change at all

    def test_module_docstring_edit_is_ignored(self):
        r = self.classify('"""old module doc"""\nX = 1',
                          '"""new module doc"""\nX = 1')
        self.assertTrue(r["additive"])

    def test_new_shared_file_is_additive(self):
        r = self.ad.classify_source("", _src("def f():\n    return 1"), "new.py")
        self.assertTrue(r["additive"])
        self.assertTrue(any("def f" in a for a in r["additions"]))

    def test_comment_and_whitespace_reflow_is_additive(self):
        # AST-equality tolerates comment/blank-line reflow of an untouched path.
        r = self.classify(
            "def f():\n    return 1  # old comment",
            "def f():\n\n    return 1  # new comment, reflowed\n")
        self.assertTrue(r["additive"])
        self.assertEqual(r["additions"], [])

    # --- non-additive cases (Lane B) --------------------------------------

    def test_folded_dispatch_tuple_is_non_additive(self):
        # Folding a new opcode into an existing `if op in (...)` edits an existing
        # path — Lane B even though it is semantically monotone.
        r = self.classify(
            "def dispatch(op):\n    if op in (1, 2):\n        return 'x'",
            "def dispatch(op):\n    if op in (1, 2, 3):\n        return 'x'")
        self.assertFalse(r["additive"])
        self.assertTrue(any("dispatch" in reason for reason in r["reasons"]))

    def test_rebound_aggregate_is_non_additive(self):
        r = self.classify("OPS = frozenset((1, 2))",
                          "OPS = frozenset((1, 2)) | EXTRA")
        self.assertFalse(r["additive"])
        self.assertTrue(any("OPS" in reason and "rebound" in reason
                            for reason in r["reasons"]))

    def test_non_version_rebind_is_non_additive(self):
        r = self.classify('LIMIT = 10', 'LIMIT = 20')
        self.assertFalse(r["additive"])

    def test_signature_change_is_non_additive(self):
        r = self.classify("def f(a):\n    return a",
                          "def f(a, b):\n    return a")
        self.assertFalse(r["additive"])
        self.assertTrue(any("signature" in reason for reason in r["reasons"]))

    def test_modified_body_statement_is_non_additive(self):
        r = self.classify("def f():\n    return 1",
                          "def f():\n    return 2")
        self.assertFalse(r["additive"])

    def test_deleted_statement_is_non_additive(self):
        r = self.classify("def f():\n    return 1\ndef g():\n    return 2",
                          "def f():\n    return 1")
        self.assertFalse(r["additive"])
        self.assertTrue(any("removed" in reason and "g" in reason
                            for reason in r["reasons"]))

    def test_reordered_defs_is_non_additive(self):
        r = self.classify("def f():\n    return 1\ndef g():\n    return 2",
                          "def g():\n    return 2\ndef f():\n    return 1")
        self.assertFalse(r["additive"])

    def test_syntax_error_in_new_is_non_additive(self):
        r = self.ad.classify_source("X = 1\n", "X = = 1\n", "broken.py")
        self.assertFalse(r["additive"])
        self.assertTrue(any("does not parse" in reason for reason in r["reasons"]))

    def test_added_branch_inside_existing_branch_is_non_additive(self):
        # Inserting a statement *inside* an existing branch body changes that
        # path — not a sibling insertion.
        r = self.classify(
            "def f(x):\n    if x:\n        return 1",
            "def f(x):\n    if x:\n        log(x)\n        return 1")
        self.assertFalse(r["additive"])

    # --- shared-layer boundary --------------------------------------------

    def test_is_shared_boundary(self):
        self.assertTrue(self.ad.is_shared("gurdy/languages/evm/interp.py"))
        self.assertTrue(self.ad.is_shared("gurdy/core/coverage.py"))
        self.assertTrue(self.ad.is_shared("gurdy/solvers/z3_backend.py"))
        self.assertFalse(self.ad.is_shared("gurdy/pairs/evm_btor2/translate.py"))
        self.assertFalse(self.ad.is_shared("tools/pr_manifest.py"))
        self.assertFalse(self.ad.is_shared("gurdy/languages/evm/SPEC.md"))

    # --- class recursion ---------------------------------------------------

    def test_new_method_is_additive_but_changed_method_is_not(self):
        add = self.classify(
            "class C:\n    def a(self):\n        return 1",
            "class C:\n    def a(self):\n        return 1\n    def b(self):\n        return 2")
        self.assertTrue(add["additive"], add["reasons"])
        chg = self.classify(
            "class C:\n    def a(self):\n        return 1",
            "class C:\n    def a(self):\n        return 99")
        self.assertFalse(chg["additive"])


if __name__ == "__main__":
    unittest.main()
