#!/bin/sh
set -eu

umask 077

# Raw retention is handled by the worker itself: it knows which session files
# are still protected (recording/captured/processing or a pending retry) and
# must not be deleted here by an unguarded find.
exec python -m racelens.recorder.worker
