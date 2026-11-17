"""
Profile export / import (Milestone C): one profile, one .fccprofile file, between two app folders standing in for PC A and PC B.
What travels (counts, history byte for byte, own wording, the channel and link fingerprints) and what never does (settings, other
profiles, keys, tokens); Remote Sharing always arrives off; a clash is replaced (old data set aside) or imported as a copy (never
merged, never a shared channel); a damaged, changed, hostile or newer file is refused before anything is written; a failure
half way puts everything back.
Run:   python tests/test_profile_transfer.py     (or pytest)
"""
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "src"))   # run without installing

import json
import tempfile
import zipfile
from pathlib import Path

from fortnite_chest_counter import counter, profiles
from fortnite_chest_counter import profile_transfer as T
from fortnite_chest_counter.remote import sharing

NL = chr(10)


class Creds:
    def __init__(self):
        self.store = {}

    def load_password(self, target=""):
        return self.store.get(target, "")

    def save_password(self, password, target="", comment="", username=""):
        self.store[target] = password

    def forget_password(self, target=""):
        self.store.pop(target, None)


def pc():
    """A throwaway app folder: -> the base counter path (state/chest_state.json)."""
    base = Path(tempfile.mkdtemp()) / "state" / "chest_state.json"
    base.parent.mkdir(parents=True)
    counter.save_state(base, counter.fresh_state())
    return base


def counts(base, pid, certain, approx):
    path = profiles.profile_state_path(base, pid)
    state = counter.fresh_state()
    state.update(certain=certain, approximate=approx)
    counter.save_state(path, state)


def history(base, pid, matches=3):
    folder = profiles.history_folder(base, pid)
    folder.mkdir(parents=True, exist_ok=True)
    rows = [{"kind": "match_closed", "schema": 1, "id": f"m{i}", "run_id": "r1", "match_number": i} for i in range(matches)]
    rows.append({"kind": "chest_estimate", "schema": 1, "id": "e1", "run_id": "r1"})
    (folder / "matches.jsonl").write_text(NL.join(json.dumps(r) for r in rows) + NL, encoding="utf-8")
    (folder / "chests.jsonl").write_text(json.dumps({"kind": "chest_correction", "schema": 1, "id": "c1"}) + NL, encoding="utf-8")
    (folder / "predictions.jsonl").write_text(json.dumps({"kind": "action", "id": "p1"}) + NL, encoding="utf-8")
    (folder / "notes.tmp").write_text("not history", encoding="utf-8")       # not a history file: never exported
    return folder


def streamer_on_pc_a():
    """PC A: Default + "Streamer B" with counts, history, own wording, a livestream source, sharing on and a viewer link."""
    a = pc()
    profiles.create(a, "Streamer B", activate=False)
    counts(a, "streamer-b", 1200, 3456)
    history(a, "streamer-b")
    profiles.set_display(a, "streamer-b", {"show": "approx", "approx_text": "CHESTS OPENED ≈ {count}"})
    profiles.remember_source(a, "streamer-b", {"source": "stream", "url": "https://www.twitch.tv/someone", "device": "Cam"})
    sharing.set_enabled(a, "streamer-b", True)
    link_id, token = sharing.add_link(a, "streamer-b", "OBS")
    counts(a, "default", 5, 9)
    return a, link_id, token


def export(a, pid="streamer-b"):
    dest = Path(tempfile.mkdtemp()) / f"{pid}{T.SUFFIX}"
    T.export_profile(a, pid, dest, "test")
    return dest


def files_of(folder):
    return {p.name: p.read_bytes() for p in Path(folder).iterdir() if p.is_file()} if Path(folder).exists() else {}


def setup_module(module=None):
    sharing.credentials = Creds()


# ==================================================================

def test_export_holds_exactly_the_profile_and_never_settings_other_profiles_or_secrets():
    setup_module()
    a, link_id, token = streamer_on_pc_a()
    (a.parent.parent / "config.toml").write_text('[display]\napprox_text = "GLOBAL {count}"\n', encoding="utf-8")
    dest = export(a)
    with zipfile.ZipFile(dest) as z:
        names = sorted(z.namelist())
        raw = b"".join(z.read(n) for n in names)
        manifest = json.loads(z.read("manifest.json"))
    assert names == ["counter.json", "history/chests.jsonl", "history/matches.jsonl", "history/predictions.jsonl", "manifest.json"]
    assert token.encode() not in raw and b"GLOBAL" not in raw and b"publisher" not in raw.lower()
    assert manifest["profile"]["source"] == {"source": "stream", "url": "https://www.twitch.tv/someone"}   # no device
    assert manifest["profile"]["remote"]["links"][0]["id"] == link_id and "enabled" not in manifest["profile"]["remote"]
    package = T.read_package(dest)
    assert package.summary["certain"] == 1200 and package.summary["approx"] == 3456
    assert (package.summary["matches"], package.summary["corrections"], package.summary["estimates"]) == (3, 1, 1)
    assert package.profile["remote"]["enabled"] is False and package.summary["own_wording"]


def test_import_on_another_pc_brings_counts_history_and_wording_and_changes_nothing_else():
    setup_module()
    a, link_id, _ = streamer_on_pc_a()
    b = pc()
    counts(b, "default", 77, 88)
    before_default = profiles.profile_state_path(b, "default").read_bytes()
    package = T.read_package(export(a))
    assert T.existing(b, package) is None
    entry = T.import_profile(b, package, "copy")
    assert entry["id"] == "streamer-b" and entry["name"] == "Streamer B"
    state = json.loads(profiles.profile_state_path(b, "streamer-b").read_text(encoding="utf-8"))
    assert (state["certain"], state["approximate"]) == (1200, 3456)
    assert files_of(profiles.history_folder(b, "streamer-b")) == {k: v for k, v in files_of(profiles.history_folder(a, "streamer-b")).items()
                                                                  if k != "notes.tmp"}
    saved = profiles.get(profiles.load(b), "streamer-b")
    assert saved["display"]["approx_text"] == "CHESTS OPENED ≈ {count}"
    assert saved["remote"]["enabled"] is False and saved["remote"]["links"][0]["id"] == link_id      # off; links' hashes kept
    assert profiles.profile_state_path(b, "default").read_bytes() == before_default                  # Default untouched
    assert profiles.load(b)["active"] == "default"
    assert not list(b.parent.glob("import-*"))                                                         # no staging left


def test_a_clash_is_replaced_with_a_backup_or_imported_as_a_copy_never_merged():
    setup_module()
    a, _, _ = streamer_on_pc_a()
    dest = export(a)
    b = pc()
    T.import_profile(b, T.read_package(dest), "copy")
    counts(b, "streamer-b", 1300, 3600)                                   # counted on PC B since
    package = T.read_package(dest)
    assert T.existing(b, package)["id"] == "streamer-b"
    copy_name = T.free_name(b, package.profile["name"])
    assert copy_name == "Streamer B (imported)"
    copy = T.import_profile(b, package, "copy", copy_name)
    assert copy["id"] != "streamer-b" and "remote" not in copy           # a copy never shares its original's channel
    T.import_profile(b, package, "replace")                               # the same file again: replace, never merge
    matches = (profiles.history_folder(b, "streamer-b") / "matches.jsonl").read_text(encoding="utf-8")
    assert matches == (profiles.history_folder(a, "streamer-b") / "matches.jsonl").read_text(encoding="utf-8")   # not doubled
    state = json.loads(profiles.profile_state_path(b, "streamer-b").read_text(encoding="utf-8"))
    assert state["approximate"] == 3456
    kept = list((profiles.profile_state_path(b, "streamer-b").parent / "deleted").glob("streamer-b-*.json"))
    assert kept and json.loads(kept[0].read_text(encoding="utf-8"))["approximate"] == 3600               # the old counts, kept
    assert list((profiles.history_folder(b, "x").parent / "deleted").glob("streamer-b-*"))
    assert len([p for p in profiles.load(b)["profiles"] if p["name"].startswith("Streamer B")]) == 2


def test_the_default_profile_can_replace_another_pcs_default():
    setup_module()
    a, _, _ = streamer_on_pc_a()
    b = pc()
    counts(b, "default", 1, 1)
    T.import_profile(b, T.read_package(export(a, "default")), "replace")
    state = json.loads(profiles.profile_state_path(b, "default").read_text(encoding="utf-8"))
    assert (state["certain"], state["approximate"]) == (5, 9)
    assert list((b.parent / "profiles" / "deleted").glob("default-*.json"))


def _rewrite(src, dest, change):
    with zipfile.ZipFile(src) as z:
        items = {n: z.read(n) for n in z.namelist()}
    change(items)
    with zipfile.ZipFile(dest, "w") as z:
        for n, data in items.items():
            z.writestr(n, data)


def test_damaged_changed_hostile_or_newer_files_are_refused_and_nothing_is_written():
    setup_module()
    a, _, _ = streamer_on_pc_a()
    good = export(a)
    b = pc()
    before = sorted(str(p.relative_to(b.parent)) for p in b.parent.rglob("*"))
    folder = Path(tempfile.mkdtemp())

    def refused(change, words):
        bad = folder / f"bad{len(list(folder.iterdir()))}{T.SUFFIX}"
        _rewrite(good, bad, change)
        try:
            T.read_package(bad)
        except T.TransferError as error:
            assert words in str(error), (words, str(error))
            return
        raise AssertionError(f"accepted ({words})")

    refused(lambda i: i.__setitem__("counter.json", b'{"certain": 9, "approximate": 99999}'), "fingerprint")
    refused(lambda i: i.__setitem__("../evil.json", b"{}"), "never has")
    refused(lambda i: i.__setitem__("history/run.exe", b"MZ"), "never has")
    refused(lambda i: i.pop("history/chests.jsonl"), "do not match")

    def newer(items):
        m = json.loads(items["manifest.json"])
        m["version"] = T.VERSION + 1
        items["manifest.json"] = json.dumps(m).encode()
    refused(newer, "newer version")
    (folder / "plain.fccprofile").write_text("hello", encoding="utf-8")
    try:
        T.read_package(folder / "plain.fccprofile")
        raise AssertionError("accepted a non-zip")
    except T.TransferError:
        pass
    saved = T.MAX_ENTRY
    T.MAX_ENTRY = 10                                                       # a "zip bomb": refused before unpacking
    try:
        T.read_package(good)
        raise AssertionError("accepted an oversized entry")
    except T.TransferError as error:
        assert "never has" in str(error)
    finally:
        T.MAX_ENTRY = saved
    assert sorted(str(p.relative_to(b.parent)) for p in b.parent.rglob("*")) == before


def test_a_failure_half_way_puts_everything_back():
    setup_module()
    a, _, _ = streamer_on_pc_a()
    b = pc()
    T.import_profile(b, T.read_package(export(a)), "copy")
    counts(b, "streamer-b", 4, 4)
    old_counter = profiles.profile_state_path(b, "streamer-b").read_bytes()
    old_history = files_of(profiles.history_folder(b, "streamer-b"))
    old_registry = profiles.registry_path(b).read_bytes()
    real = profiles.save

    def broken(*args, **kwargs):
        raise OSError("disk full")
    profiles.save = broken
    try:
        T.import_profile(b, T.read_package(export(a)), "replace")
        raise AssertionError("did not fail")
    except T.TransferError as error:
        assert "Nothing was changed" in str(error)
    finally:
        profiles.save = real
    assert profiles.profile_state_path(b, "streamer-b").read_bytes() == old_counter
    assert files_of(profiles.history_folder(b, "streamer-b")) == old_history
    assert profiles.registry_path(b).read_bytes() == old_registry
    assert not list(b.parent.glob("import-*"))


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"ok    {t.__name__}")
        except Exception as error:
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {t.__name__}: {error!r}")
    print(f"{len(tests) - failed}/{len(tests)} profile transfer checks passed")
    raise SystemExit(1 if failed else 0)
