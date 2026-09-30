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
BOX=padmint  # the Ubuntu container's name, apart from any the player has

say() { printf '\n== %s\n' "$1"; }

main() {
  set -e
  case "${PREFIX:-}" in
    */com.termux/files/usr) ;;
    *) echo "Run this in the Termux app on your phone or tablet."; exit 1 ;;
  esac

  say "Your files"
  if ! ls /sdcard/Download >/dev/null 2>&1; then
    echo "Android asks whether Termux may use your files: choose Allow."
    termux-setup-storage </dev/null
    tries=0
    until ls /sdcard/Download >/dev/null 2>&1; do
      tries=$((tries + 1))
      if [ "$tries" -gt 90 ]; then
        echo "Termux cannot see your files. Run this line again and choose Allow."
        exit 1
      fi
      sleep 2
    done
  fi
  echo "Put your own game file (for example your .rvz or .iso) in the phone's Download folder."
  # Builds keep running with the screen off; released at the end.
  termux-wake-lock </dev/null || true

  say "Ubuntu inside Termux (the first time takes a few minutes)"
  export DEBIAN_FRONTEND=noninteractive
  # proot-distro 5 (Docker images, --name); older versions are updated first.
  if ! proot-distro install --help 2>&1 | grep -q -- --name; then
    yes | pkg update -y -o Dpkg::Options::=--force-confnew
    yes | pkg install -y -o Dpkg::Options::=--force-confnew proot-distro
  fi
  if [ ! -d "$PREFIX/var/lib/proot-distro/containers/$BOX" ]; then
    proot-distro install --name "$BOX" ubuntu:24.04 </dev/null
  fi

  ref=${PADMINT_REF:-}
  if [ -z "$ref" ]; then
    latest=$(curl -fsSLI -o /dev/null -w '%{url_effective}' "$REPO/releases/latest")
    ref=${latest##*/}
  fi
  say "PadMint $ref"
  proot-distro login "$BOX" -e "PADMINT_REF=$ref" -e "PADMINT_REPO=$REPO" -- /bin/sh -s <<'EOF'
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
exec proot-distro login $BOX --work-dir /root/padmint -- python3 -m padmint "\$@"
EOF
  chmod 755 "$PREFIX/bin/padmint"
  echo "Next time, type: padmint"
  echo "Keep Termux open until PadMint says your game is ready."

  status=0
  padmint </dev/tty || status=$?
  termux-wake-unlock </dev/null || true
  exit "$status"
}

main "$@"
