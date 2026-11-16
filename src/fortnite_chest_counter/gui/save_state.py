"""
One Save for a whole settings page (Settings, Overlay): what the page showed when it was last loaded or saved, compared with what
it shows now.

The page reads its editable settings into a dict, {name: value} in saved units, and draws the status this decides:
    clean     "All changes saved"            nothing to save
    unsaved   "Unsaved changes"              something differs from what is saved (on any tab of the page)
    saved     "Settings saved"               just saved and read back
    error     "Not saved: <why>"             the last save failed; the changes are still on the page

Qt-free on purpose (the page wires its widgets to changed() and draws the status), so the rules are tested on their own:
switching tabs is not a change, changing a value back to the saved one is not a change, a failed save keeps everything, and a
setting changed outside the page (OBS renamed the source, and the app saved that) moves the saved value without touching the
user's own unsaved edits.
"""

CLEAN, UNSAVED, SAVED, ERROR = "clean", "unsaved", "saved", "error"
_MISSING = object()


class SaveState:
    def __init__(self, read_values, show):
        self._read = read_values            # () -> {name: value} of every editable setting, as the page shows it now
        self._show = show                   # (status, text) -> None: the page draws the status
        self._saved = None                  # {name: value} when last loaded or saved; None while the page fills its widgets
        self.status = CLEAN

    def _set(self, status, text=""):
        self.status = status
        self._show(status, text)

    def loading(self):
        """The page is about to fill its widgets from the saved settings: what they do meanwhile is not a change."""
        self._saved = None

    def loaded(self):
        """The widgets show the saved settings now."""
        self._saved = dict(self._read())
        self._set(CLEAN)

    def is_dirty(self):
        return self._saved is not None and self._read() != self._saved

    def changes(self):
        """{name: value on the page} for every setting that differs from what is saved."""
        if self._saved is None:
            return {}
        return {name: value for name, value in self._read().items() if self._saved.get(name, _MISSING) != value}

    def saved_value(self, name):
        return None if self._saved is None else self._saved.get(name)

    def changed(self, *_):
        """A widget changed (or the user changed it back)."""
        if self._saved is None:
            return
        if self.is_dirty():
            self._set(UNSAVED)
        elif self.status in (UNSAVED, ERROR):              # back to exactly what is saved
            self._set(CLEAN)

    def saved(self, text=""):
        """Everything on the page was written and read back."""
        self._saved = dict(self._read())
        self._set(SAVED, text)

    def failed(self, text):
        """The save did not happen (or was undone): the changes stay on the page, unsaved."""
        self._set(ERROR, text)

    def rebase(self, name, value):
        """`name` was saved as `value` outside the page. Its saved value moves; the user's unsaved edits stay as they are."""
        if self._saved is None:
            return
        self._saved[name] = value
        self.changed()
