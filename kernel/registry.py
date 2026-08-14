"""The append-only registry of generated content (KERNEL.md §8).

Four kinds of entry, one directory each:

- ``registry/languages/<name>/``  — syntax + interpreter
- ``registry/pairs/<src>--<tgt>/`` — translation edges
- ``registry/terminals/<name>/``  — solving + certifying endpoints
- ``registry/domains/<name>/``    — a root language and its anchors

Each entry is a manifest plus generated implementations; admission
evidence is stamped by the checker, never self-reported. The registry
is one space: a domain owns nothing beyond its root and anchors, so
every admitted pair and terminal is available to every domain
(KERNEL.md §4). During a run the registry only grows; pruning is a
human act between runs.
"""

from __future__ import annotations

import json
import os

#: kind -> (subdirectory, key field, required manifest fields)
_KINDS = {
    "language": ("languages", "name", {"kind", "name"}),
    "pair": ("pairs", "id",
             {"kind", "id", "src", "tgt", "direction", "keeps"}),
    "terminal": ("terminals", "name",
                 {"kind", "name", "language", "decides"}),
    "domain": ("domains", "name", {"kind", "name", "root", "anchors"}),
}


class RegistryError(Exception):
    pass


def _read_manifest(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load(root: str) -> dict:
    """Load the registry: ``{"languages": {name: manifest}, "pairs":
    {id: manifest}, "terminals": {name: manifest}, "domains": {name:
    manifest}}``, each manifest carrying its ``_dir``. A missing
    directory is the empty registry — the kernel ships that way."""
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
            table[manifest[key]] = manifest
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
    entry = os.path.join(root, sub, manifest[key])
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
    """The checker's stamp: admission evidence written into the entry.
    Overwriting an existing stamp is refused — re-admission is a new
    entry, not an edit."""
    mpath = os.path.join(entry_dir, "manifest.json")
    manifest = _read_manifest(mpath)
    if "admission" in manifest:
        raise RegistryError(f"{entry_dir} already admitted")
    manifest["admission"] = evidence
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
