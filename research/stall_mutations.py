"""Small, reproducible sabotage checks for the input stall warning.

Mutates private in-memory module copies, never repository files. Each mutation must be rejected by a named test in tests/test_input_stall.py.
Run after that file passes.
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_input_stall as T
from fortnite_chest_counter import gui as gui_package
from fortnite_chest_counter import input as input_package
from fortnite_chest_counter.gui import app as real_app
from fortnite_chest_counter.input import video_sources as real_sources


MUTATIONS = [
    # the source
    ("S", "if self.watch_stalls and not stalled and not self._stop and previous is not None and self.elapsed() - previous >= self.STALL_AFTER:", "if False:", "test_a_stall_warns_once"),
    ("S", "if self.watch_stalls and not stalled and not self._stop", "if self.watch_stalls and not self._stop", "test_a_stall_warns_once"),
    ("S", "if self.watch_stalls and not stalled and not self._stop and previous is not None and self.elapsed() - previous >= self.STALL_AFTER:", "if self.watch_stalls and not stalled and not self._stop and previous is not None:", "test_a_short_hitch_stays_silent"),
    ("S", "if self.watch_stalls and not stalled and", "if not stalled and", "test_a_video_file_is_never_watched"),
    ("S", "\"NOT RECEIVING VIDEO - no new pictures from this source", "\"CAMERA DISCONNECTED - no new pictures from this source", "test_the_warning_says_what_is_known_and_not_why"),
    ("S", "                stalled = False\n                say_source_state(\"live\"", "                say_source_state(\"live\"", "test_a_second_stall_warns_again"),
    ("S", "                say_source_state(\"live\", \"video is coming in again - counting continues.\")\n", "", "test_recovery_clears_it_and_reports_what_may_be_missing"),
    ("S", "                say_source_state(\"incomplete\", f\"about {item[0] - previous:.0f} s of video was not received: chests opened in that part may be \"\n                                               \"missing from the count.\")\n", "", "test_recovery_clears_it_and_reports_what_may_be_missing"),
    ("S", "f\"about {item[0] - previous:.0f} s of video", "f\"about {self.STALL_AFTER:.0f} s of video", "test_the_gap_reported_is_the_real_one"),
    ("S", "            previous = item[0]\n            self.frames_dropped", "            self.frames_dropped", "test_a_stall_warns_once"),
    ("S", "args, fps, watch_stalls=False)", "args, fps)", "test_a_video_file_is_never_watched"),
    ("S", "    STALL_AFTER = 10.0  ", "    STALL_AFTER = 60.0  ", "test_live_inputs_are_watched"),
    ("S", "                    stalled = True\n", "                    stalled = True\n                    self.close(wait=False)\n", "test_a_stall_restarts_nothing"),
    ("S", "                continue\n            if stalled:", "                item = self._latest\n            if stalled:", "test_every_picture_still_arrives_unchanged_and_in_order"),
    ("S", "    elif state in (\"live\", \"caught_up\"):\n        CONSOLE.info(text)\n    else:\n        CONSOLE.warn(text)\n", "    elif state in (\"live\", \"caught_up\"):\n        CONSOLE.info(text)\n", "test_the_terminal_gets_a_warning_too"),
    # the window
    ("G", "                 \"no_video\": (theme.REJECT, \"No video\", \"NO VIDEO\\nthe app is not receiving pictures from this source\")}", "                 }", "test_the_dashboard_says_no_video"),
    ("G", "        if state == \"no_video\":\n            self.last_status = None                     # the last rate is no longer true\n", "", "test_the_old_rate_does_not_come_back_with_the_video"),
    ("G", "            if self.stream_state == \"no_video\":\n                parts.append(\"no new video\")\n            elif s:", "            if s:", "test_the_old_rate_is_not_shown_during_a_stall"),
    ("G", "\"reconnecting\", \"offline\", \"no_video\"):", "\"reconnecting\", \"offline\"):", "test_the_preview_keeps_the_message_not_the_last_picture"),
]


def main():
    caught = 0
    originals = {"S": real_sources, "G": real_app}
    for number, (name, old, new, test_name) in enumerate(MUTATIONS, 1):
        original = originals[name]
        source = Path(original.__file__).read_text(encoding="utf-8")
        if old not in source:
            raise RuntimeError(f"mutation {number} no longer applies; review this check")
        mutant = types.ModuleType(original.__name__ + "_mutated")
        mutant.__file__, mutant.__package__ = original.__file__, original.__package__
        sys.modules[mutant.__name__] = mutant
        exec(compile(source.replace(old, new, 1), original.__file__, "exec"), mutant.__dict__)
        owner, attribute = (input_package, "video_sources") if name == "S" else (gui_package, "app")
        with patch.object(owner, attribute, mutant):
            try:
                getattr(T, test_name)()
            except (AssertionError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, StopIteration) as error:
                caught += 1
                print(f"caught {number:02d}: {test_name} ({type(error).__name__})", flush=True)
            else:
                print(f"SURVIVED {number:02d}: {name}: {test_name}", flush=True)
    print(f"{caught}/{len(MUTATIONS)} stall mutations caught")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
