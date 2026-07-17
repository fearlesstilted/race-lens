#!/bin/sh
set -eu

umask 077
base=${RACELENS_RECORDER_DATA:-/var/lib/race-lens-recorder}
retention_days=${RECORDER_RAW_RETENTION_DAYS:-14}

case "$retention_days" in
    ''|*[!0-9]*) echo "RECORDER_RAW_RETENTION_DAYS must be an integer" >&2; exit 2 ;;
esac

find "$base/raw" -xdev -type f -mtime "+$retention_days" -delete
exec python -m racelens.recorder.worker
