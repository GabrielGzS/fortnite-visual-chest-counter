#!/bin/sh
set -eu

cd -- "$(dirname -- "$0")"

if [ -x .venv/bin/python ]; then
    exec .venv/bin/python -m fortnite_chest_counter.gui "$@"
fi

if [ -x .venv/Scripts/python.exe ]; then
    exec .venv/Scripts/python.exe -m fortnite_chest_counter.gui "$@"
fi

printf '%s\n' 'Set up the local Python environment first. See Development in README.md.' >&2
exit 1
