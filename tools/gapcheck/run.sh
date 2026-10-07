#!/usr/bin/env bash
# Cron wrapper for gapcheck. Logs to out/gapcheck.log and prints the summary
# only when there is something to look at (changes or an error), so a cron
# MAILTO, if you have one, stays quiet on uneventful weeks.
set -u
cd "$(dirname "$(readlink -f "$0")")"
mkdir -p out
log=out/gapcheck.log
summary=$(./.venv/bin/python gapcheck.py "$@" 2>>"$log")
rc=$?
{ echo "=== $(date -Is) exit=$rc"; echo "$summary"; } >>"$log"
[ "$rc" -ne 0 ] && echo "$summary"
case $rc in
  0|3) exit 0 ;;   # 3 = new candidate list written; not a failure
  *)   echo "gapcheck failed (exit $rc), see $(pwd)/$log"; exit "$rc" ;;
esac
