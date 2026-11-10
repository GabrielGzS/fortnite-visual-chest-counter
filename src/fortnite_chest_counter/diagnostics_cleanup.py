"""Find and remove local diagnostic artifacts created by the counter."""

import re
import shutil
import stat

from fortnite_chest_counter import profiles

_SESSION = re.compile(r"session_\d{8}_\d{6}")
_CRASH = re.compile(r"crash_app_\d{8}_\d{6}\.txt")
_CAPTURE = re.compile(r"\d{8}_\d{6}(?:_[2-9]|_\d{2,})?")


def _is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _children(folder):
    if not folder.is_dir() or _is_link(folder):
        return ()
    return tuple(path for path in folder.iterdir() if not _is_link(path))


def counter_states(root, config):
    """State paths for both sources, across the configured profiles."""
    base = root / config["profile"]["state_base"]
    states = {}
    for profile in profiles.load(base)["profiles"]:
        state = profiles.profile_state_path(base, profile["id"])
        states[state] = None
        states[profiles.secondary_state_path(state)] = None
    # Deleted profiles can still have a secondary diagnostic directory.
    for folder in _children(base.parent / "profiles"):
        if folder.is_dir() and folder.name.endswith("-secondary"):
            name = folder.name.removesuffix("-secondary")
            states[folder / f"{name}.json"] = None
    return tuple(states)


def diagnostic_artifacts(root, config):
    """Return only recognized files or session directories, including custom output locations."""
    logs = root / config["logging"]["dir"]
    captures = root / config["capture"]["dir"]
    log_folders = dict.fromkeys((logs, root / "logs", *(state.parent / "logs" for state in counter_states(root, config)
                                                       if state.parent.name.endswith("-secondary"))))
    found = []
    for folder in log_folders:
        for path in _children(folder):
            if path.is_file() and (path.name == "diagnostics.txt" or _CRASH.fullmatch(path.name)
                                   or (path.suffix == ".jsonl" and _SESSION.fullmatch(path.stem))):
                found.append(path)
        if not folder.exists() or not _is_link(folder):
            for path in _children(folder / "snapshots"):
                if path.is_dir() and _SESSION.fullmatch(path.name):
                    found.append(path)
    for path in _children(captures):
        if path.is_dir() and _CAPTURE.fullmatch(path.name) and (path / "capture.json").is_file():
            found.append(path)
    return list(dict.fromkeys(found))


def remove_diagnostic_artifacts(artifacts):
    removed, failed = 0, []
    for path in artifacts:
        try:
            if _is_link(path):
                failed.append(path)
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            failed.append(path)
    return removed, failed
