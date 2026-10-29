#!/usr/bin/env bash
# Copy the rover-side Python files to a MuSHR car's src/ folder (flat, as the car runs them).
#
# Usage (from anywhere; Git Bash on Windows works):
#   rover/deploy.sh 21                       # robot@192.168.2.21 (rover 1)
#   rover/deploy.sh 22 --restart             # rover 2, then restart radio_daemon.service
#   rover/deploy.sh robot@10.42.0.1 --dry-run   # over the car's own AP; only report what would change
#
# A file that differs from the car's copy is first backed up there as <file>.bak_<YYYYMMDD>
# (once per day). Line endings are converted to LF, so a CRLF checkout can't break the
# shebangs (rover_nav.py is run by roslaunch). --restart opens a second SSH session for sudo.
#
# rover_nav.py / odom_fusion.py are only reloaded when the ROS stack restarts (Stop/Start ROS
# on the dashboard). The MuSHR launcher pair in car/ is not copied; see car/README.md.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
DEST='catkin_ws/src/mushr/mushr_base/mushr_base/mushr_base/src'   # relative to the robot's home
FILES=(
    "$HERE/radio_daemon.py"
    "$HERE/rover_nav.py"
    "$HERE/calib_distance.py"
    "$REPO/common/odom_fusion.py"
    "$REPO/common/relay_brain.py"
    "$REPO/common/route_plan.py"
    "$REPO/common/site_map.py"
)

HOST=''
RESTART=0
DRY=0
for a in "$@"; do
    case "$a" in
        --restart) RESTART=1 ;;
        --dry-run) DRY=1 ;;
        -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
        -*) echo "unknown option $a" >&2; exit 1 ;;
        *) HOST="$a" ;;
    esac
done
[ -n "$HOST" ] || { sed -n '2,15p' "$0"; exit 1; }
case "$HOST" in
    21|22) HOST="robot@192.168.2.$HOST" ;;
    *@*) ;;
    *) HOST="robot@$HOST" ;;
esac

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
for f in "${FILES[@]}"; do
    sed 's/\r$//' "$f" > "$STAGE/$(basename "$f")"
done

# Runs on the car: $1 = dest folder, $2 = backup stamp, $3 = dry run; tar on stdin.
REMOTE='
set -e
dest="$1"; stamp="$2"; dry="$3"
[ -d "$dest" ] || { echo "no $dest on $(hostname)"; exit 1; }
stage="$(mktemp -d)"; trap "rm -rf $stage" EXIT
tar -C "$stage" -xf -
for f in $(ls "$stage"); do
    if [ ! -e "$dest/$f" ]; then state=new
    elif cmp -s "$stage/$f" "$dest/$f"; then echo "  same     $f"; continue
    else state=changed; fi
    if [ "$dry" = 1 ]; then echo "  $state  $f"; continue; fi
    if [ "$state" = changed ] && [ ! -e "$dest/$f.bak_$stamp" ]; then
        cp -p "$dest/$f" "$dest/$f.bak_$stamp"; state="changed (old copy: $f.bak_$stamp)"
    fi
    cp "$stage/$f" "$dest/$f"; echo "  $state  $f"
done
[ "$dry" = 1 ] || chmod +x "$dest/rover_nav.py" "$dest/radio_daemon.py" "$dest/calib_distance.py"
'

echo "$HOST:~/$DEST"
tar -C "$STAGE" -cf - . \
    | ssh "$HOST" "bash -c $(printf '%q' "$REMOTE") _ $DEST $(date +%Y%m%d) $DRY"
[ "$DRY" = 1 ] && exit 0
if [ "$RESTART" = 1 ]; then
    # separate connection: sudo needs a terminal, and the one above carries the tar stream
    ssh -t "$HOST" 'sudo systemctl restart radio_daemon && systemctl --no-pager --lines=0 status radio_daemon | head -3'
else
    echo "radio_daemon.py changes take effect after: sudo systemctl restart radio_daemon (or --restart)"
fi
