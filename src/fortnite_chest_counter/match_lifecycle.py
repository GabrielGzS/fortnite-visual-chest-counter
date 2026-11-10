"""Recognize local Battle Royale boundaries in newly appended Fortnite log data."""

import os
import re
from pathlib import Path


_PREFIX = rb"(?:\[\d{4}\.\d\d\.\d\d-\d\d\.\d\d\.\d\d:\d{3}\]\[ *\d{1,3}\])?"
_START = re.compile(_PREFIX + rb"LogBattleRoyaleGamePhaseLogic: HandleGamePhaseChanged\. "
                    rb"OldPhase = EAthenaGamePhase::Setup\. NewPhase = EAthenaGamePhase::Warmup")
_FRONTEND = re.compile(_PREFIX + rb"LogWorld: Bringing World /Game/Maps/Frontend\.Frontend up for play "
                       rb"\(max tick rate \d+\) at \d{4}\.\d\d\.\d\d-\d\d\.\d\d\.\d\d")


def local_log_path():
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return local / "FortniteGame" / "Saved" / "Logs" / "FortniteGame.log"


class LogTail:
    """Read at most one chunk per poll and carry only the current bounded line."""

    READ_SIZE = 256 * 1024
    LINE_LIMIT = 4096
    ANCHOR_SIZE = 128

    def __init__(self, path):
        self.path = path
        self._reset()
        try:
            with path.open("rb") as stream:
                stat = os.fstat(stream.fileno())
                self._identity = (stat.st_dev, stat.st_ino)
                self._offset = stat.st_size
                self._anchor = self._read_anchor(stream)
                self._skip_line = bool(self._anchor and not self._anchor.endswith(b"\n"))
        except FileNotFoundError:
            pass

    def _reset(self):
        self.caught_up = True
        self._identity = None
        self._offset = 0
        self._anchor = b""
        self._partial = b""
        self._skip_line = False

    def _read_anchor(self, stream):
        size = min(self.ANCHOR_SIZE, self._offset)
        stream.seek(self._offset - size)
        return stream.read(size)

    def poll(self):
        """Return a discontinuity flag followed by the ordered markers from this chunk."""
        try:
            with self.path.open("rb") as stream:
                stat = os.fstat(stream.fileno())
                identity = (stat.st_dev, stat.st_ino)
                restarted = self._identity is not None and (
                    identity != self._identity or stat.st_size < self._offset
                    or self._read_anchor(stream) != self._anchor
                )
                if restarted:
                    self._reset()
                self._identity = identity
                stream.seek(self._offset)
                chunk = stream.read(self.READ_SIZE)
                self._offset += len(chunk)
                self.caught_up = self._offset >= stat.st_size
                self._anchor = (self._anchor + chunk)[-self.ANCHOR_SIZE:]
        except FileNotFoundError:
            restarted = self._identity is not None
            self._reset()
            return restarted, []
        if not chunk:
            return restarted, []

        lines = (self._partial + chunk).split(b"\n")
        partial = lines.pop()
        if self._skip_line and lines:
            lines.pop(0)
            self._skip_line = False
        self._skip_line = self._skip_line or len(partial) > self.LINE_LIMIT
        self._partial = b"" if self._skip_line else partial
        events = []
        for line in lines:
            if len(line) > self.LINE_LIMIT:
                continue
            line = line.rstrip(b"\r")
            if _START.fullmatch(line):
                events.append("start")
            elif _FRONTEND.fullmatch(line):
                events.append("finish")
        return restarted, events
