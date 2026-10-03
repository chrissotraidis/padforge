#!/data/data/com.termux/files/usr/bin/sh
# PadMint on an Android phone or tablet, with no computer. In the Termux app
# (from F-Droid or GitHub; Google Play is unvalidated for PadMint), paste:
#
#   curl -fsSL https://raw.githubusercontent.com/chrissotraidis/padmint/main/launchers/padmint-android.sh | sh
#
# It sets up Ubuntu inside Termux (proot-distro), puts PadMint there, adds a
# "padmint" command to Termux and starts it. Steps already done are skipped, so
# the same line also updates PadMint. PADMINT_REF picks a PadMint branch or tag
# (default: the latest release).

REPO=https://github.com/chrissotraidis/padmint
# Canonical's Ubuntu Base 24.04 for phones whose proot-distro is version 4: its own
# Ubuntu download no longer works (HTTP 403, 3 Oct 2026). Checked against Canonical's SHA256SUMS.
UBUNTU_BASE_URL=https://cdimage.ubuntu.com/ubuntu-base/releases/24.04/release/ubuntu-base-24.04.5-base-arm64.tar.gz
UBUNTU_BASE_SHA256=a91d5a93010193712d346d761372b7c9db6dfcf093893161c64ca107f05914f2
BOX=${PADMINT_BOX:-padmint}  # the Ubuntu container's name, apart from any the player has
HELP="Need help? Post a screenshot of this screen in the KartPad Discord (#help) or at $REPO/issues"
COMPUTER="A Windows, Mac or Linux computer is the easier way: $REPO#android-with-a-computer"
STEP="starting"

say() { STEP=$1; printf '\n== %s\n' "$1"; }

# Most people who reach this script want KartPad, which has a ready-to-play APK again.
kartpad_note() {
  say "Playing KartPad?"
  echo "KartPad has a ready-to-play Android app again. Install KartPad-v...-android.apk from"
  echo "  https://github.com/chrissotraidis/kartpad/releases/latest"
  echo "and you don't need this setup at all."
  echo ""
  echo "This setup installs PadMint on this phone, to build your own copy or to make the"
  echo "KartPad game data folder from your disc. It needs about 25 GB free."
  # A pause to read this on a phone's screen; scripts and tests carry on.
  [ -t 1 ] || return 0
  echo "Continuing in 20 seconds. To stop, tap CTRL, then C."
  sleep 20
}

# A plain ending instead of a wall of tool output.
fail() {
  trap - EXIT
  printf '\n== PadMint setup stopped\n%s\n\n%s\n' "$1" "$HELP"
  exit 1
}

stopped() {
  status=$?
  [ "$status" -eq 0 ] && return
  printf '\n== PadMint setup stopped while: %s\n' "$STEP"
  printf 'Run the same line again: finished steps are kept.\n\n%s\n' "$HELP"
}

# Before downloading gigabytes: a 64-bit phone, room for the build, and enough memory.
phone_check() {
  [ -z "${PADMINT_SKIP_PHONE_CHECK:-}" ] || return 0
  arch=$(uname -m)
  [ "$arch" = aarch64 ] || fail "PadMint needs a 64-bit phone (arm64); this one is $arch.
$COMPUTER"
  free_gb=$(df -k "$PREFIX" | awk 'NR == 2 { print int($4 / 1048576) }')
  [ "${free_gb:-0}" -ge 25 ] || fail "PadMint needs about 25 GB free on this phone; it has ${free_gb:-0} GB.
Free up space and run the same line again, or use a computer.
$COMPUTER"
  memory_gb=$(awk '/^MemTotal/ { print int($2 / 1048576 + 0.5) }' /proc/meminfo)
  [ "${memory_gb:-0}" -ge 7 ] || fail "PadMint needs a phone with about 8 GB of memory; this one has ${memory_gb:-0} GB.
$COMPUTER"
}

# proot-distro 5 names a container with --name; version 4 (still all that some
# Termux mirrors offer) with --override-alias. Prints name, alias or none.
proot_style() {
  help=$(proot-distro install --help 2>&1 || true)
  case "$help" in
    *--name*) echo name ;;
    *--override-alias*) echo alias ;;
    *) echo none ;;
  esac
}

main() {
  set -e
  case "${PREFIX:-}" in
    */com.termux/files/usr) ;;
    *) echo "Run this in the Termux app on your phone or tablet."; exit 1 ;;
  esac
  trap stopped EXIT

  kartpad_note
  say "Checking this phone"
  phone_check
  echo "Ready: 64-bit, enough space and memory."

  say "Your files"
  if ! ls /sdcard/Download >/dev/null 2>&1; then
    echo "Android asks whether Termux may use your files: choose Allow."
    termux-setup-storage </dev/null
    tries=0
    until ls /sdcard/Download >/dev/null 2>&1; do
      tries=$((tries + 1))
      if [ "$tries" -gt 90 ]; then
        fail "Termux cannot see your files. Run the same line again and choose Allow."
      fi
      sleep 2
    done
  fi
  echo "Put your own game file (for example your .rvz or .iso) in the phone's Download folder."
  # Builds keep running with the screen off; released at the end.
  termux-wake-lock </dev/null || true

  say "Ubuntu inside Termux (the first time takes a few minutes)"
  export DEBIAN_FRONTEND=noninteractive
  # proot-distro 5 (Docker images, --name) is preferred: try to update an older one first.
  style=$(proot_style)
  if [ "$style" != name ]; then
    # Parallel mirror probes can exceed Android's child-process limit. Keep
    # Termux's configured server for these calls; package signatures stay checked.
    yes | TERMUX_PKG_NO_MIRROR_SELECT=1 pkg update -y -o Dpkg::Options::=--force-confnew ||
      fail "Termux could not update its packages. Check your internet connection and run the same line again."
    yes | TERMUX_PKG_NO_MIRROR_SELECT=1 pkg install -y -o Dpkg::Options::=--force-confnew proot-distro ||
      fail "Termux could not install proot-distro. Check your internet connection and run the same line again."
    style=$(proot_style)
  fi
  # Some Termux mirrors still offer only proot-distro 4: it works too, with its own options.
  case "$style" in
    name) rootfs=$PREFIX/var/lib/proot-distro/containers/$BOX ;;
    alias) rootfs=$PREFIX/var/lib/proot-distro/installed-rootfs/$BOX ;;
    *) fail "This Termux's proot-distro is too old for PadMint.
Install Termux from F-Droid (https://f-droid.org/packages/com.termux/), not Google Play, and run the same line again." ;;
  esac
  if [ ! -d "$rootfs" ]; then
    if [ "$style" = name ]; then
      proot-distro install --name "$BOX" ubuntu:24.04 </dev/null
    else
      # A plug-in named after the container: Ubuntu Base 24.04, nothing else to set up.
      mkdir -p "$PREFIX/etc/proot-distro"
      cat > "$PREFIX/etc/proot-distro/$BOX.sh" <<PLUGIN
DISTRO_NAME="Ubuntu 24.04 for PadMint"
TARBALL_STRIP_OPT=0
TARBALL_URL['aarch64']="$UBUNTU_BASE_URL"
TARBALL_SHA256['aarch64']="$UBUNTU_BASE_SHA256"
distro_setup() { :; }
PLUGIN
      proot-distro install "$BOX" </dev/null
    fi
  fi

  ref=${PADMINT_REF:-}
  if [ -z "$ref" ]; then
    latest=$(curl -fsSLI -o /dev/null -w '%{url_effective}' "$REPO/releases/latest")
    ref=${latest##*/}
  fi
  say "PadMint $ref"
  proot-distro login "$BOX" --env "PADMINT_REF=$ref" --env "PADMINT_REPO=$REPO" -- /bin/sh -s <<'EOF'
set -e
export DEBIAN_FRONTEND=noninteractive
# LLVM's linker needs libxml2; Git and Python run PadMint and the game's builder.
if ! dpkg -s python3 git ca-certificates libxml2 >/dev/null 2>&1; then
  apt-get update -q
  apt-get install -y -q --no-install-recommends python3 git ca-certificates libxml2
fi
if [ -d /root/padmint/.git ]; then
  git -C /root/padmint fetch -q --depth 1 origin "$PADMINT_REF"
  git -C /root/padmint checkout -q FETCH_HEAD
else
  git clone -q --depth 1 --branch "$PADMINT_REF" "$PADMINT_REPO" /root/padmint
fi
EOF

  cat > "$PREFIX/bin/padmint" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
# PadMint in its Ubuntu inside Termux (set up by padmint-android.sh).
# Ubuntu does not see the phone's language: pass it on (PADMINT_LANG overrides it).
lang=\${PADMINT_LANG:-\$(getprop persist.sys.locale 2>/dev/null)}
exec proot-distro login $BOX --work-dir /root/padmint --env "PADMINT_LANG=\$lang" -- python3 -m padmint "\$@"
EOF
  chmod 755 "$PREFIX/bin/padmint"
  echo "Next time, type: padmint"
  echo "PadMint now opens in your phone's browser. Keep Termux open in the background"
  echo "until the page says your copy is ready. (To answer in Termux instead: padmint start)"

  status=0
  trap - EXIT
  padmint </dev/tty || status=$?
  termux-wake-unlock </dev/null || true
  exit "$status"
}

main "$@"
