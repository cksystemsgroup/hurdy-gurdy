"""The append-only registry of generated content (KERNEL.md §10).

Four kinds of entry, one directory each — the two primitive kinds and
the two bookkeeping ones:

- ``registry/languages/<name>/``  — syntax + interpreter + the
  language's evidence judges under ``evidence/<schema>/``
- ``registry/pairs/<src>--<tgt>/`` — one correspondence: the transports
  of its declared channel set
- ``registry/searches/<name>/``   — the one partial transport,
  ``L -> Evidence(L)``
- ``registry/domains/<name>/``    — a root language and its anchors

Each entry is a manifest plus generated implementations; admission
evidence is stamped by the checker, never self-reported. The registry
is one space: a domain owns nothing beyond its root and anchors, so
every admitted language, pair, and search serves every domain
(KERNEL.md §7). During a run the registry only grows; pruning is a
human act between runs.

Extension is revision, not mutation (KERNEL.md §10): an entry may be
extended by a new entry ``<name>@<r>`` carrying the same name, a
``revision`` number, and ``previous`` — the content hash of its
predecessor. Every stamp pins the admitted bytes (``tree``); loading
verifies the pin, and a name binds to its highest admitted revision.
Predecessors stay in the tree, so the log's citations keep meaning.
Adding a channel to an admitted pair is the intended common case.
"""

from __future__ import annotations

import hashlib
import json
import os

#: kind -> (subdirectory, key field, required manifest fields)
_KINDS = {
    "language": ("languages", "name", {"kind", "name"}),
    "pair": ("pairs", "id",
             {"kind", "id", "src", "tgt", "direction", "keeps",
              "channels"}),
    "search": ("searches", "name",
               {"kind", "name", "language", "targets"}),
    "domain": ("domains", "name", {"kind", "name", "root", "anchors"}),
}


class RegistryError(Exception):
    pass


def _read_manifest(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _skip(name: str) -> bool:
    return (name.startswith(".") or name.endswith(".pyc")
            or name == "__pycache__")


def tree_hash(entry_dir: str) -> str:
    """The content pin: one sha256 over the entry's files (manifest
    excluded — the stamp lives there — along with caches and
    dotfiles), so an admitted entry can be checked against its stamp
    and a revision can name its predecessor's exact bytes."""
    tree: dict[str, str] = {}
    for base, dirs, files in os.walk(entry_dir):
        dirs[:] = sorted(d for d in dirs if not _skip(d))
        for fn in sorted(files):
            if _skip(fn) or (fn == "manifest.json" and base == entry_dir):
                continue
            path = os.path.join(base, fn)
            rel = os.path.relpath(path, entry_dir)
            with open(path, "rb") as fh:
                tree[rel] = hashlib.sha256(fh.read()).hexdigest()
    return hashlib.sha256(
        json.dumps(tree, sort_keys=True).encode()).hexdigest()


def schemas(lang_manifest: dict) -> list[str]:
    """The certificate schemas a language ships judges for — read from
    the entry's ``evidence/`` directory, the directory being the truth
    (KERNEL.md §3). The witness schema is free for every language and
    never listed: its judge is the interpreter itself."""
    base = os.path.join(lang_manifest["_dir"], "evidence")
    if not os.path.isdir(base):
        return []
    return sorted(
        d for d in os.listdir(base)
        if not _skip(d)
        and os.path.isfile(os.path.join(base, d, "check.py")))


def _binds_over(new: dict, cur: dict) -> bool:
    """Binding order for one name: admitted beats unadmitted, then the
    higher revision wins."""
    na, ca = "admission" in new, "admission" in cur
    if na != ca:
        return na
    return new.get("revision", 1) > cur.get("revision", 1)


def load(root: str) -> dict:
    """Load the registry: ``{"languages": {name: manifest}, "pairs":
    {id: manifest}, "searches": {name: manifest}, "domains": {name:
    manifest}}``, each manifest carrying its ``_dir``. A missing
    directory is the empty registry — the kernel ships that way. A
    name with several revisions binds to the highest admitted one, and
    every stamped content pin is verified — an admitted entry whose
    bytes changed is a hard error, not a warning."""
    root = os.path.abspath(root)
    reg: dict = {}
    for kind, (sub, key, _) in _KINDS.items():
        table: dict[str, dict] = {}
        base = os.path.join(root, sub)
        for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            mpath = os.path.join(base, name, "manifest.json")
            if not os.path.isfile(mpath):
                continue
            manifest = _read_manifest(mpath)
            manifest["_dir"] = os.path.join(base, name)
            stamp = manifest.get("admission")
            if stamp is not None:
                # the pin is defined in KERNEL.md §10; a stamp without
                # one is refused exactly as changed bytes are — an
                # admission that cannot be re-verified is no admission
                if "tree" not in stamp:
                    raise RegistryError(
                        f"{manifest['_dir']}: admission stamp carries no "
                        "content pin")
                if tree_hash(manifest["_dir"]) != stamp["tree"]:
                    raise RegistryError(
                        f"{manifest['_dir']}: admitted content no longer "
                        "matches its stamp")
            k = manifest[key]
            if k in table and (manifest.get("revision", 1)
                               == table[k].get("revision", 1)):
                raise RegistryError(
                    f"{manifest['_dir']}: two entries claim {k!r} at "
                    f"revision {manifest.get('revision', 1)} — a name "
                    "binds to exactly one entry per revision")
            if k not in table or _binds_over(manifest, table[k]):
                table[k] = manifest
        reg[sub] = table
    return reg


def register(root: str, manifest: dict, files: dict[str, bytes]) -> str:
    """Write a new entry directory. Append-only: an existing entry is
    never overwritten — re-admission is a new entry, not an edit."""
    kind = manifest.get("kind")
    if kind not in _KINDS:
        raise RegistryError(f"unknown kind {kind!r}")
    sub, key, required = _KINDS[kind]
    missing = required - set(manifest)
    if missing:
        raise RegistryError(f"manifest missing {sorted(missing)}")
    rev = manifest.get("revision", 1)
    dirname = manifest[key] if rev == 1 else f"{manifest[key]}@{rev}"
    entry = os.path.join(root, sub, dirname)
    if os.path.exists(entry):
        raise RegistryError(f"registry is append-only: {entry} exists")
    os.makedirs(entry)
    for rel, data in files.items():
        path = os.path.join(entry, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
    with open(os.path.join(entry, "manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return entry


def stamp_admission(entry_dir: str, evidence: dict) -> None:
    """The checker's stamp: admission evidence written into the entry,
    together with the content pin of the bytes that were checked.
    Overwriting an existing stamp is refused — re-admission is a new
    entry (or a new revision), not an edit."""
    mpath = os.path.join(entry_dir, "manifest.json")
    manifest = _read_manifest(mpath)
    if "admission" in manifest:
        raise RegistryError(f"{entry_dir} already admitted")
    evidence = dict(evidence)
    evidence["tree"] = tree_hash(entry_dir)
    manifest["admission"] = evidence
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
