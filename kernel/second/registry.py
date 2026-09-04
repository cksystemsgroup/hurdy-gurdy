"""Registry loading (KERNEL.md §10) for the second lineage.

Four kinds live under ``<root>/{domains,languages,pairs,searches}/<entry>/``.
An entry is admitted iff its ``manifest.json`` carries an ``admission``
stamp; every stamp's ``tree`` pin is re-verified on load, and a mismatch or
a missing pin is a hard error.  A name binds to its highest admitted
revision.  Nothing about an entry's files beyond the manifest and the pin
is read.
"""

import hashlib
import json
import os

KINDS = ("domains", "languages", "pairs", "searches")


class RegistryError(Exception):
    """A hard error while loading the registry (exit status 1)."""


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_pin(entry_dir):
    """The §10 content pin of an entry directory.

    Over every regular file under the entry -- the top-level manifest.json,
    dotfiles, __pycache__ directories and .pyc files excluded -- map the
    entry-relative POSIX path to the sha256 hex digest of the file's bytes,
    serialize as JSON with sorted keys and separators ", " / ": ", and
    sha256 that text once more.
    """
    files = {}
    for dirpath, dirnames, filenames in os.walk(entry_dir):
        dirnames[:] = sorted(
            d for d in dirnames if d != "__pycache__" and not d.startswith(".")
        )
        for fn in sorted(filenames):
            if fn.startswith(".") or fn.endswith(".pyc"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, entry_dir).replace(os.sep, "/")
            if rel == "manifest.json":
                continue
            if not os.path.isfile(full):
                continue
            files[rel] = _sha256_file(full)
    text = json.dumps(files, sort_keys=True, separators=(", ", ": "))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _entry_name_and_revision(kind, manifest, dirname):
    base, _, rev = dirname.partition("@")
    name = manifest.get("name") or manifest.get("id") or base
    revision = manifest.get("revision")
    if revision is None:
        revision = int(rev) if rev.isdigit() else 1
    return name, int(revision)


def load_registry(root):
    """Load the admitted registry: ``{kind: {name: entry}}``.

    Each entry is a dict with ``kind``, ``name``, ``revision``, ``label``
    (the entry directory name, e.g. ``btor2@5``), ``path`` and ``manifest``.
    """
    registry = {kind: {} for kind in KINDS}
    for kind in KINDS:
        kind_dir = os.path.join(root, kind)
        if not os.path.isdir(kind_dir):
            continue
        seen = {}  # (name, revision) -> entry dir: one entry per revision
        for dirname in sorted(os.listdir(kind_dir)):
            entry_dir = os.path.join(kind_dir, dirname)
            manifest_path = os.path.join(entry_dir, "manifest.json")
            if not os.path.isdir(entry_dir) or not os.path.isfile(manifest_path):
                continue
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except (OSError, ValueError) as e:
                raise RegistryError(f"{manifest_path}: unreadable manifest: {e}")
            if not isinstance(manifest, dict) or "admission" not in manifest:
                continue  # not admitted: no trace in routing
            stamp = manifest.get("admission")
            pin = stamp.get("tree") if isinstance(stamp, dict) else None
            if not isinstance(pin, str) or not pin:
                raise RegistryError(
                    f"{entry_dir}: admission stamp carries no content pin (tree); "
                    "refused as if its bytes had changed"
                )
            actual = tree_pin(entry_dir)
            if actual != pin:
                raise RegistryError(
                    f"{entry_dir}: content pin mismatch: stamp {pin}, tree {actual}; "
                    "an admitted entry whose bytes changed is a hard error"
                )
            name, revision = _entry_name_and_revision(kind, manifest, dirname)
            entry = {
                "kind": kind,
                "name": name,
                "revision": revision,
                "label": dirname,
                "path": entry_dir,
                "manifest": manifest,
            }
            if (name, revision) in seen:
                raise RegistryError(
                    f"{entry_dir}: claims name {name!r} at revision {revision}, which "
                    f"{seen[(name, revision)]} already holds; two entries at the same name "
                    "and revision are a hard error, not a choice"
                )
            seen[(name, revision)] = entry_dir
            bound = registry[kind].get(name)
            if bound is None or revision > bound["revision"]:
                registry[kind][name] = entry
    return registry
