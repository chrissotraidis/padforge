#!/bin/sh
# PadMint for Linux. Run ./padmint.sh (needs Python 3.9+ and Git).
cd "$(dirname "$0")" || exit 1
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
  echo "PadMint needs Python 3.9 or newer, for example: sudo apt install python3 git"
  exit 1
fi
exec python3 -m padmint "$@"
