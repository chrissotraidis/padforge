#!/bin/bash
# PadMint for macOS. Double-click to start.
cd "$(dirname "$0")" || exit 1
# Apple's Python: it uses the system's certificates (a python.org Python needs its
# Install Certificates step first) and comes with the command line tools PadMint needs.
PYTHON=/usr/bin/python3
if "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
  "$PYTHON" -m padmint "$@"
else
  echo "PadMint needs Python 3.9 or newer. Apple's command line tools include it (and Git):"
  echo "  xcode-select --install"
fi
echo
read -r -p "Press Enter to close this window. "
