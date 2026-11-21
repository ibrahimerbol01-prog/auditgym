#!/bin/sh
# AuditGym one-line installer for macOS and Linux.
#
#   curl -fsSL is.gd/auditgym_sh | sh
#
# (the short link points at https://github.com/ibrahimerbol01-prog/auditgym-releases/releases/latest/download/install.sh;
#  the source repo is private, builds are published to that public releases-only repo by the Release workflow)
#   Team, newest CI build of a branch (GitHub CLI logged in):
#     gh api "repos/ibrahimerbol01-prog/auditgym/contents/desktop/install.sh?ref=main" -H "Accept: application/vnd.github.raw" | AUDITGYM_BRANCH=main sh
#
# Installs into your home folder (no sudo), checks the download against the release's SHA256SUMS.txt, and adds
# the app to Applications (macOS) or to the desktop menu (Linux).
# Options (environment variables): AUDITGYM_VERSION=v1.0.0 (default: latest release), AUDITGYM_NO_LAUNCH=1,
# AUDITGYM_BRANCH=<branch> (the newest successful "Desktop app" CI build of that branch instead of a release),
# AUDITGYM_ZIP=/path/AuditGym-<os>-<arch>.zip (install a local build, for testing), AUDITGYM_BASE_URL=<mirror>.
set -eu

REPO="ibrahimerbol01-prog/auditgym"            # private source: CI branch builds (AUDITGYM_BRANCH, needs gh)
PUBLIC="ibrahimerbol01-prog/auditgym-releases"  # public releases: the default, plain HTTPS, no login
VERSION="${AUDITGYM_VERSION:-latest}"

say() { printf '%s\n' "AuditGym installer: $*"; }
fail() { printf '%s\n' "AuditGym installer: error: $*" >&2; exit 1; }

case "$(uname -s)" in
  Darwin) OS=macos ;;
  Linux) OS=linux ;;
  *) fail "this script is for macOS and Linux; on Windows use install.ps1" ;;
esac
case "$(uname -m)" in
  x86_64|amd64) ARCH=x64 ;;
  arm64|aarch64) ARCH=arm64 ;;
  *) fail "unsupported processor $(uname -m)" ;;
esac
ASSET="AuditGym-$OS-$ARCH.zip"
if [ "$OS" = macos ] && [ "$ARCH" = x64 ]; then
  fail "no build for Intel Macs yet; run from source instead: see desktop/README.md"
fi
if [ "$OS" = linux ] && [ "$ARCH" = arm64 ]; then
  fail "no build for Linux on ARM yet; run from source instead: see desktop/README.md"
fi
command -v unzip >/dev/null 2>&1 || fail "please install unzip first"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

if [ -n "${AUDITGYM_ZIP:-}" ]; then
  say "installing local build $AUDITGYM_ZIP"
  cp "$AUDITGYM_ZIP" "$TMP/$ASSET"
elif [ -n "${AUDITGYM_BRANCH:-}" ]; then
  command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1 || fail "installing a branch build needs the GitHub CLI, logged in (gh auth login)"
  RUN="$(gh run list -R "$REPO" --workflow desktop.yml --branch "$AUDITGYM_BRANCH" --status success --limit 1 --json databaseId --jq '.[0].databaseId')" || RUN=""
  [ -n "$RUN" ] || fail "no successful desktop build of branch '$AUDITGYM_BRANCH' yet (see the Actions tab)"
  say "downloading $ASSET from the newest build of branch '$AUDITGYM_BRANCH' (run $RUN)"
  gh run download "$RUN" -R "$REPO" -n "${ASSET%.zip}" -D "$TMP" && [ -f "$TMP/$ASSET" ] || fail "run $RUN has no $ASSET (it may have expired; push again or run the workflow)"
else
  if [ -n "${AUDITGYM_BASE_URL:-}" ]; then BASE="$AUDITGYM_BASE_URL"
  elif [ "$VERSION" = latest ]; then BASE="https://github.com/$PUBLIC/releases/latest/download"
  else BASE="https://github.com/$PUBLIC/releases/download/$VERSION"; fi
  say "downloading $ASSET ($VERSION)"
  curl -fsSL "$BASE/$ASSET" -o "$TMP/$ASSET" || fail "download failed from $BASE"
  curl -fsSL "$BASE/SHA256SUMS.txt" -o "$TMP/SHA256SUMS.txt" || fail "could not download SHA256SUMS.txt"
fi

if [ -f "$TMP/SHA256SUMS.txt" ]; then
  want="$(grep " $ASSET\$" "$TMP/SHA256SUMS.txt" | cut -d' ' -f1)"
  [ -n "$want" ] || fail "$ASSET is not listed in SHA256SUMS.txt"
  [ "$(sha256 "$TMP/$ASSET")" = "$want" ] || fail "checksum mismatch for $ASSET; not installing"
  say "checksum OK"
fi

unzip -q "$TMP/$ASSET" -d "$TMP/x"

if [ "$OS" = macos ]; then
  DEST="$HOME/Applications"
  mkdir -p "$DEST"
  rm -rf "$DEST/AuditGym.app"
  mv "$TMP/x/AuditGym.app" "$DEST/AuditGym.app"
  APP="$DEST/AuditGym.app"
  say "installed $APP"
  if [ -d "$TMP/x/auditgym-cli" ]; then
    CLI="${XDG_DATA_HOME:-$HOME/.local/share}/auditgym-cli"
    BIN="$HOME/.local/bin"
    mkdir -p "$(dirname "$CLI")" "$BIN"
    rm -rf "$CLI"
    mv "$TMP/x/auditgym-cli" "$CLI"
    ln -sf "$CLI/auditgym" "$BIN/auditgym"
    say "terminal command: auditgym   (try: auditgym run-agent --policy reconcile)"
    case ":$PATH:" in *":$BIN:"*) ;; *) say "add $BIN to your PATH: echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc" ;; esac
  fi
  say "it is not notarised: if macOS blocks it, right-click AuditGym in Applications and choose Open once"
  [ -n "${AUDITGYM_NO_LAUNCH:-}" ] || open "$APP"
else
  DEST="${XDG_DATA_HOME:-$HOME/.local/share}/auditgym"
  BIN="$HOME/.local/bin"
  mkdir -p "$DEST" "$BIN"
  rm -rf "$DEST/AuditGym"
  mv "$TMP/x/AuditGym" "$DEST/AuditGym"
  chmod +x "$DEST/AuditGym/AuditGym"
  ln -sf "$DEST/AuditGym/AuditGym" "$BIN/auditgym-app"
  if [ -x "$DEST/AuditGym/cli/auditgym" ]; then
    ln -sf "$DEST/AuditGym/cli/auditgym" "$BIN/auditgym"
    say "terminal command: auditgym   (try: auditgym run-agent --policy reconcile)"
  fi
  APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
  mkdir -p "$APPS"
  cat > "$APPS/auditgym.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=AuditGym
Comment=RL environment for audit agents (offline)
Exec=$DEST/AuditGym/AuditGym
Icon=$DEST/AuditGym/_internal/data/icon.png
Terminal=false
Categories=Education;Development;
EOF
  say "installed $DEST/AuditGym (command: auditgym-app)"
  case ":$PATH:" in *":$BIN:"*) ;; *) say "add $BIN to your PATH to use the auditgym and auditgym-app commands" ;; esac
  [ -n "${AUDITGYM_NO_LAUNCH:-}" ] || (nohup "$DEST/AuditGym/AuditGym" >/dev/null 2>&1 &)
fi
if [ -f "$TMP/BUILD.txt" ]; then say "version: $(cat "$TMP/BUILD.txt")"; elif [ -z "${AUDITGYM_ZIP:-}" ]; then say "version: $VERSION release"; fi
say "done"
