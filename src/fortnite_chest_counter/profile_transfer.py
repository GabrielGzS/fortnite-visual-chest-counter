"""
Profile export / import: ONE profile in ONE .fccprofile file, to move it to another PC.

    manifest.json     {"format", "version", "app", "exported_at", "profile": {...}, "files": {name: {"sha256", "size"}}}
    counter.json      the profile's counter file (CERTAIN / APPROX / last chest / chest types)
    history/<file>    the profile's history folder: matches.jsonl (runs, matches, corrections, estimates), chests.jsonl,
                      predictions.jsonl - every plain .jsonl / .json file in it

"profile" holds what belongs to the profile itself: name, id, created date, HUD Scale, its own overlay wording, a livestream
link it counted from, and its Remote Sharing channel with the SHA-256 of its viewer links. Never in the file: global settings
(config.toml), other profiles, logs, recordings, the publisher key, viewer-link tokens or the secret they are made from.

Import checks everything before touching anything (format and version, file names, sizes, every file's SHA-256, the counter
values, the profile data), writes into a staging folder next to the profiles, then moves it in. A failure leaves the PC as it
was. It never merges: a profile that already exists is either replaced (its data is set aside, never erased, as Delete does)
or the file becomes a separate copy. An imported profile never shares by itself: Remote Sharing starts off, and a copy whose
channel another profile on this PC already uses gets none. History rows keep their ids, so importing the same file again
(Replace) never counts anything twice.
"""

import hashlib

import json
import os
import re
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from fortnite_chest_counter import profiles
from fortnite_chest_counter.settings import HUD_VALUES

FORMAT = "fortnite-visual-chest-counter-profile"
VERSION = 1
SUFFIX = ".fccprofile"
HISTORY_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}\.(jsonl|json)$")
MAX_PACKAGE = 256 * 1024 * 1024          # the .fccprofile file itself
MAX_ENTRY = 256 * 1024 * 1024            # one file inside, unpacked
MAX_TOTAL = 512 * 1024 * 1024            # everything inside, unpacked (a zip bomb is refused before it is unpacked)
MAX_ENTRIES = 64


class TransferError(ValueError):
    """The export or import cannot be done; the message is meant for the user."""


@dataclass
class Package:
    path: Path
    manifest: dict
    profile: dict
    files: dict = field(default_factory=dict)              # "counter.json" / "history/<name>" -> bytes
    summary: dict = field(default_factory=dict)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _counts(data):
    """(certain, approx) from counter-file bytes, or raises TransferError."""
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise TransferError("its counter file is damaged") from None
    certain, approx = (raw.get("certain"), raw.get("approximate")) if isinstance(raw, dict) else (None, None)
    if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in (certain, approx)):
        raise TransferError("its counter file has no valid CERTAIN / APPROX counts")
    return certain, max(approx, certain)


def _portable_source(source):
    """Only a livestream link travels: devices, monitors and windows belong to the PC that counted."""
    source = source or {}
    if source.get("source") == "stream" and source.get("url"):
        return {k: source[k] for k in ("source", "url", "stream_stability") if source.get(k)}
    return {}


def _summary(profile, files):
    certain, approx = _counts(files["counter.json"])
    kinds = {}
    for name, data in files.items():
        if name.endswith(".jsonl"):
            for line in data.decode("utf-8").splitlines():
                try:
                    kind = json.loads(line).get("kind")
                except (ValueError, AttributeError):
                    continue
                kinds[kind] = kinds.get(kind, 0) + 1
    remote = profile.get("remote") or {}
    return {"certain": certain, "approx": approx, "matches": kinds.get("match_closed", 0),
            "corrections": kinds.get("chest_correction", 0), "estimates": kinds.get("chest_estimate", 0),
            "history_files": sorted(n.split("/", 1)[1] for n in files if n.startswith("history/")),
            "links": sum(not link.get("revoked") for link in remote.get("links", [])), "own_wording": bool(profile.get("display"))}


# ==================================================================
# export
# ==================================================================

def export_profile(base_state_path, profile_id, dest, app_version=""):
    """Write the profile to `dest` (a .fccprofile file; replaced only once complete). -> the summary shown to the user."""
    reg = profiles.load(base_state_path)
    entry = profiles.get(reg, profile_id)
    files = {}
    counter = profiles.profile_state_path(base_state_path, profile_id)
    if counter.exists():
        files["counter.json"] = counter.read_bytes()
    else:                                              # a profile that never counted
        files["counter.json"] = json.dumps({"certain": 0, "approximate": 0}).encode("utf-8")
    _counts(files["counter.json"])                     # never export a damaged counter
    history = profiles.history_folder(base_state_path, profile_id)
    if history.is_dir():
        for path in sorted(history.iterdir()):
            if path.is_file() and HISTORY_NAME.match(path.name):
                files[f"history/{path.name}"] = path.read_bytes()
    profile = {"id": entry["id"], "name": entry["name"], "created_at": entry.get("created_at"),
               "source": _portable_source(entry.get("source"))}
    for key in ("hud", "display"):
        if entry.get(key):
            profile[key] = entry[key]
    if entry.get("remote"):
        profile["remote"] = {"channel": entry["remote"]["channel"], "links": entry["remote"]["links"]}   # hashes only
    manifest = {"format": FORMAT, "version": VERSION, "app": app_version, "exported_at": _now(), "profile": profile,
                "files": {name: {"sha256": _sha(data), "size": len(data)} for name, data in files.items()}}
    dest = Path(dest)
    part = dest.with_name(dest.name + ".part")
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            for name, data in files.items():
                z.writestr(name, data)
        os.replace(part, dest)
    except OSError:
        part.unlink(missing_ok=True)
        raise
    return _summary(profile, files)


# ==================================================================
# import: read and check (nothing is written)
# ==================================================================

def read_package(path):
    """Open and check a .fccprofile completely. -> Package. Raises TransferError (and writes nothing) if anything is wrong."""
    path = Path(path)
    try:
        if path.stat().st_size > MAX_PACKAGE:
            raise TransferError("the file is far too large for a profile")
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        raise TransferError("it is not a profile file (.fccprofile), or it could not be read") from None
    with z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        if len(infos) > MAX_ENTRIES or len(set(names)) != len(names) or "manifest.json" not in names:
            raise TransferError("it is not a valid profile file")
        for info in infos:
            name = info.filename
            allowed = name in ("manifest.json", "counter.json") or (
                name.startswith("history/") and HISTORY_NAME.match(name[len("history/"):]) is not None)
            if not allowed or info.is_dir() or info.file_size > MAX_ENTRY:
                raise TransferError(f"it contains something a profile file never has ({name[:60]})")
        if sum(i.file_size for i in infos) > MAX_TOTAL:
            raise TransferError("it unpacks to far too much data for a profile")
        try:
            manifest = json.loads(z.read("manifest.json").decode("utf-8"))
        except (UnicodeDecodeError, ValueError, zipfile.BadZipFile):
            raise TransferError("its contents list is damaged") from None
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT or not isinstance(manifest.get("version"), int):
            raise TransferError("it is not a profile file of this app")
        if manifest["version"] > VERSION:
            raise TransferError("it was made by a newer version of the app. Update this PC's app first, then import it")
        declared = manifest.get("files")
        if not isinstance(declared, dict) or set(declared) != set(names) - {"manifest.json"} or "counter.json" not in declared:
            raise TransferError("its contents do not match its contents list")
        files = {}
        for name, meta in declared.items():
            try:
                data = z.read(name)
            except (zipfile.BadZipFile, OSError, RuntimeError):
                raise TransferError(f"{name} inside it is damaged") from None
            if not isinstance(meta, dict) or meta.get("size") != len(data) or meta.get("sha256") != _sha(data):
                raise TransferError(f"{name} inside it is damaged or was changed (its fingerprint does not match)")
            if name.endswith((".jsonl", ".json")):
                try:
                    data.decode("utf-8")
                except UnicodeDecodeError:
                    raise TransferError(f"{name} inside it is not readable text") from None
            files[name] = data
    profile = _clean_profile(manifest.get("profile"))
    return Package(path=path, manifest=manifest, profile=profile, files=files, summary=_summary(profile, files))


def _clean_profile(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not " ".join(raw["name"].split()):
        raise TransferError("its profile has no name")
    pid = raw.get("id") if isinstance(raw.get("id"), str) else ""
    if pid != profiles.DEFAULT_ID and profiles.slug(pid) != pid:
        pid = profiles.slug(raw["name"])
    profile = {"id": pid, "name": " ".join(raw["name"].split())[:profiles.MAX_NAME],
               "created_at": raw.get("created_at") if isinstance(raw.get("created_at"), str) else None,
               "source": _portable_source(raw.get("source") if isinstance(raw.get("source"), dict) else {})}
    if raw.get("hud") in HUD_VALUES:
        profile["hud"] = raw["hud"]
    display = profiles._clean_display(raw.get("display"))
    if display:
        profile["display"] = display
    remote = profiles._clean_remote({**raw["remote"], "enabled": False}) if isinstance(raw.get("remote"), dict) else None
    if remote is not None:
        profile["remote"] = remote                    # never shares by itself on the new PC
    return profile


def existing(base_state_path, package):
    """The profile on this PC the file would collide with (same id or same name), or None."""
    reg = profiles.load(base_state_path)
    name = package.profile["name"].casefold()
    return next((p for p in reg["profiles"] if p["id"] == package.profile["id"] or p["name"].casefold() == name), None)


def free_name(base_state_path, name):
    """`name`, or "name (imported)", "name (imported 2)", ... - the first not used by a profile here."""
    taken = {p["name"].casefold() for p in profiles.load(base_state_path)["profiles"]}
    if name.casefold() not in taken:
        return name
    n = 1
    while True:
        candidate = f"{name} (imported{'' if n == 1 else f' {n}'})"[:profiles.MAX_NAME]
        if candidate.casefold() not in taken:
            return candidate
        n += 1


# ==================================================================
# import: write
# ==================================================================

def import_profile(base_state_path, package, mode, name=None):
    """mode "copy": a new profile (name: `name`, or the file's name if free). mode "replace": the profile existing() found gets
    the file's data; its old counter and history are set aside (state/profiles/deleted, state/history/deleted), never erased.
    All or nothing. -> the profile entry now in profiles.json."""
    if mode not in ("copy", "replace"):
        raise ValueError(mode)
    reg = profiles.load(base_state_path)
    target = existing(base_state_path, package) if mode == "replace" else None
    if mode == "replace" and target is None:
        raise TransferError("there is no profile here to replace")
    if mode == "copy":
        if len(reg["profiles"]) >= profiles.MAX_PROFILES:
            raise TransferError(f"this PC already has {profiles.MAX_PROFILES} profiles; delete one first")
        try:
            clean = profiles.check_name(name or package.profile["name"], reg)
        except profiles.ProfileError as error:
            raise TransferError(str(error)) from None
        taken = {p["id"] for p in reg["profiles"]}
        pid = profiles.slug(clean, taken)
        while profiles.profile_state_path(base_state_path, pid).exists() or profiles.history_folder(base_state_path, pid).exists():
            taken.add(pid)                            # files left behind by hand: never overwrite them
            pid = profiles.slug(clean, taken)
    else:
        pid = target["id"]
        others = {p["name"].casefold() for p in reg["profiles"] if p["id"] != pid}
        clean = package.profile["name"] if package.profile["name"].casefold() not in others else target["name"]
    remote = package.profile.get("remote")
    if remote and any((p.get("remote") or {}).get("channel") == remote["channel"] for p in reg["profiles"] if p["id"] != pid):
        remote = None                                 # a copy next to its original: its own channel later, never a shared one

    base_dir = Path(base_state_path).parent
    staging = base_dir / f"import-{time.strftime('%Y%m%d_%H%M%S')}-{os.getpid()}"
    counter = profiles.profile_state_path(base_state_path, pid)
    history = profiles.history_folder(base_state_path, pid)
    set_aside_counter = set_aside_history = None
    placed_counter = placed_history = False
    try:
        (staging / "history").mkdir(parents=True)
        for name_, data in package.files.items():
            out = staging / name_
            with open(out, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        if mode == "replace":
            set_aside_history = profiles._set_history_aside(base_state_path, pid)
            if counter.exists():
                folder = counter.parent / "deleted" if pid != profiles.DEFAULT_ID else counter.parent / "profiles" / "deleted"
                folder.mkdir(parents=True, exist_ok=True)
                set_aside_counter = folder / f"{pid}-{time.strftime('%Y%m%d_%H%M%S')}.json"
                counter.replace(set_aside_counter)
        elif history.exists():
            raise TransferError("a history folder for this profile already exists")
        counter.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging / "counter.json", counter)
        placed_counter = True
        history.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging / "history", history)
        placed_history = True
        reg = profiles.load(base_state_path)
        entry = {"id": pid, "name": clean, "created_at": package.profile.get("created_at") or _now(),
                 "source": package.profile.get("source") or {}}
        for key in ("hud", "display"):
            if package.profile.get(key):
                entry[key] = package.profile[key]
        if remote:
            entry["remote"] = {**remote, "enabled": False}
        if mode == "replace":
            reg["profiles"] = [entry if p["id"] == pid else p for p in reg["profiles"]]
        else:
            reg["profiles"].append(entry)
        profiles.save(base_state_path, reg)
        return entry
    except Exception as error:
        # put everything back as it was (best effort, in reverse order); the staging folder goes below
        if placed_history:
            shutil.rmtree(history, ignore_errors=True)
        if placed_counter:
            try:
                counter.unlink()
            except OSError:
                pass
        if set_aside_counter is not None:
            try:
                set_aside_counter.replace(counter)
            except OSError:
                pass
        if set_aside_history is not None:
            try:
                set_aside_history.replace(history)
            except OSError:
                pass
        if isinstance(error, TransferError):
            raise
        if isinstance(error, (OSError, profiles.ProfileError)):
            raise TransferError(f"it could not be written ({error}). Nothing was changed") from error
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
