"""The append-only registry of generated content (KERNEL.md §9).

Languages live at ``registry/languages/<name>/``, pairs at
``registry/pairs/<src>--<tgt>/`` (solver pairs at
``registry/pairs/<src>--result-<solver>/``). Each entry is a manifest
plus executables; admission evidence is stamped by the checker, never
self-reported. During a run the registry only grows; pruning is a
human act between runs.
"""

from __future__ import annotations

import json
import os

_LANG_KEYS = {"kind", "name"}
_PAIR_KEYS = {"kind", "id", "src", "pair_kind"}


class RegistryError(Exception):
    pass


def _read_manifest(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load(root: str) -> dict:
    """Load the registry: {"languages": {name: manifest},
    "pairs": {id: manifest}}, each manifest carrying its ``_dir``."""
    root = os.path.abspath(root)
    reg = {"languages": {}, "pairs": {}}
    for kind, sub in (("languages", "languages"), ("pairs", "pairs")):
        base = os.path.join(root, sub)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            mpath = os.path.join(base, name, "manifest.json")
            if not os.path.isfile(mpath):
                continue
            manifest = _read_manifest(mpath)
            manifest["_dir"] = os.path.join(base, name)
            key = manifest["name"] if kind == "languages" else manifest["id"]
            reg[kind][key] = manifest
    return reg


def _register(base: str, name: str, manifest: dict, files: dict[str, bytes],
              required: set[str]) -> str:
    missing = required - set(manifest)
    if missing:
        raise RegistryError(f"manifest missing {sorted(missing)}")
    entry = os.path.join(base, name)
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


def register_language(root: str, manifest: dict,
                      files: dict[str, bytes]) -> str:
    if manifest.get("kind") != "language":
        raise RegistryError("kind must be 'language'")
    return _register(os.path.join(root, "languages"), manifest["name"],
                     manifest, files, _LANG_KEYS)


def register_pair(root: str, manifest: dict, files: dict[str, bytes]) -> str:
    if manifest.get("kind") != "pair":
        raise RegistryError("kind must be 'pair'")
    return _register(os.path.join(root, "pairs"), manifest["id"],
                     manifest, files, _PAIR_KEYS)


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
