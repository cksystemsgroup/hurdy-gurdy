"""The append-only registry (KERNEL.md §10): the content pin as the
specification defines it, re-verified on load; changed bytes and
pinless stamps refused; names bound to the highest admitted revision;
entries and stamps written once."""

from __future__ import annotations

import glob
import hashlib
import json
import os
import shutil
import tempfile
import unittest

from kernel import registry

REG = "registry"


def pin_per_spec(entry_dir: str) -> str:
    """KERNEL.md §10, transcribed: over every regular file under the
    entry — the top-level manifest.json, dotfiles, __pycache__ and
    .pyc excluded — the map path -> sha256, serialized with sorted keys
    and the separators ', ' and ': ', hashed once more."""
    tree = {}
    for base, dirs, files in os.walk(entry_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")
                   and d != "__pycache__"]
        for fn in files:
            if fn.startswith(".") or fn.endswith(".pyc"):
                continue
            if fn == "manifest.json" and base == entry_dir:
                continue
            path = os.path.join(base, fn)
            with open(path, "rb") as fh:
                tree[os.path.relpath(path, entry_dir)] = \
                    hashlib.sha256(fh.read()).hexdigest()
    text = json.dumps(tree, sort_keys=True, separators=(", ", ": "))
    return hashlib.sha256(text.encode()).hexdigest()


class ContentPin(unittest.TestCase):
    def test_every_stamp_pins_its_bytes_as_the_spec_defines(self):
        entries = sorted(glob.glob(os.path.join(REG, "*", "*",
                                                "manifest.json")))
        self.assertGreater(len(entries), 0)
        for mpath in entries:
            entry = os.path.dirname(mpath)
            with open(mpath, encoding="utf-8") as fh:
                manifest = json.load(fh)
            stamp = manifest.get("admission")
            self.assertIsNotNone(stamp, entry)
            self.assertIn("tree", stamp, entry)
            self.assertEqual(stamp["tree"], pin_per_spec(entry), entry)
            self.assertEqual(stamp["tree"], registry.tree_hash(entry), entry)

    def test_the_registry_loads_and_binds_highest_admitted_revision(self):
        reg = registry.load(REG)
        for sub in ("languages", "pairs", "searches", "domains"):
            for name, m in reg[sub].items():
                siblings = [json.load(open(p, encoding="utf-8"))
                            for p in glob.glob(os.path.join(
                                REG, sub, f"{name}@*", "manifest.json"))
                            + [os.path.join(REG, sub, name, "manifest.json")]
                            if os.path.isfile(p)]
                admitted = [s.get("revision", 1) for s in siblings
                            if "admission" in s]
                self.assertEqual(m.get("revision", 1), max(admitted),
                                 f"{sub}/{name}")


class ChangedBytesRefused(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # domains are the cheapest entries to copy: manifest only
        shutil.copytree(os.path.join(REG, "domains"),
                        os.path.join(self.tmp, "domains"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_intact_copy_loads(self):
        self.assertIn("hardware", registry.load(self.tmp)["domains"])

    def test_added_file_breaks_the_pin(self):
        with open(os.path.join(self.tmp, "domains", "hardware", "note.txt"),
                  "w") as fh:
            fh.write("one more byte than was admitted\n")
        with self.assertRaises(registry.RegistryError):
            registry.load(self.tmp)

    def test_pinless_stamp_is_refused(self):
        mpath = os.path.join(self.tmp, "domains", "hardware", "manifest.json")
        m = json.load(open(mpath, encoding="utf-8"))
        del m["admission"]["tree"]
        json.dump(m, open(mpath, "w", encoding="utf-8"))
        with self.assertRaises(registry.RegistryError):
            registry.load(self.tmp)

    def test_hidden_and_cache_files_do_not_count(self):
        d = os.path.join(self.tmp, "domains", "hardware")
        os.makedirs(os.path.join(d, "__pycache__"))
        open(os.path.join(d, "__pycache__", "x.pyc"), "wb").write(b"\0")
        open(os.path.join(d, ".DS_Store"), "wb").write(b"\0")
        self.assertIn("hardware", registry.load(self.tmp)["domains"])


class AppendOnly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_empty_registry_is_the_kernel_shipping_state(self):
        reg = registry.load(self.tmp)
        self.assertEqual(reg, {"languages": {}, "pairs": {}, "searches": {},
                               "domains": {}})

    def test_entries_and_stamps_are_written_once(self):
        m = {"kind": "language", "name": "l"}
        entry = registry.register(self.tmp, m, {"interp.py": b"print(1)\n"})
        with self.assertRaises(registry.RegistryError):
            registry.register(self.tmp, m, {})
        # unadmitted: present, unstamped, and not binding over admitted
        self.assertNotIn("admission", registry.load(self.tmp)["languages"]["l"])
        registry.stamp_admission(entry, {"checked": "language"})
        with self.assertRaises(registry.RegistryError):
            registry.stamp_admission(entry, {"checked": "language"})
        reg = registry.load(self.tmp)
        self.assertEqual(reg["languages"]["l"]["admission"]["tree"],
                         registry.tree_hash(entry))

    def test_revisions_bind_only_when_admitted(self):
        m1 = {"kind": "language", "name": "l"}
        e1 = registry.register(self.tmp, m1, {"interp.py": b"1\n"})
        registry.stamp_admission(e1, {"checked": "language"})
        m2 = {"kind": "language", "name": "l", "revision": 2,
              "previous": registry.tree_hash(e1)}
        e2 = registry.register(self.tmp, m2, {"interp.py": b"2\n"})
        self.assertTrue(e2.endswith("l@2"))
        self.assertEqual(registry.load(self.tmp)["languages"]["l"].get(
            "revision", 1), 1)
        registry.stamp_admission(e2, {"checked": "language"})
        self.assertEqual(registry.load(self.tmp)["languages"]["l"][
            "revision"], 2)
        self.assertEqual(registry.load(self.tmp)["languages"]["l"][
            "previous"], registry.tree_hash(e1))

    def test_two_entries_at_one_revision_are_refused(self):
        m = {"kind": "language", "name": "l"}
        e1 = registry.register(self.tmp, m, {"interp.py": b"1\n"})
        registry.stamp_admission(e1, {"checked": "language"})
        # a second directory claiming the same name and revision
        os.makedirs(os.path.join(self.tmp, "languages", "l-twin"))
        shutil.copy(os.path.join(e1, "manifest.json"),
                    os.path.join(self.tmp, "languages", "l-twin"))
        with self.assertRaises(registry.RegistryError):
            registry.load(self.tmp)

    def test_unknown_kind_and_missing_fields_refused(self):
        with self.assertRaises(registry.RegistryError):
            registry.register(self.tmp, {"kind": "engine", "name": "z"}, {})
        with self.assertRaises(registry.RegistryError):
            registry.register(self.tmp, {"kind": "pair", "id": "a--b"}, {})
