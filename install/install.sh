#!/bin/sh
set -eu

HOLO_HOME="${HOLO_HOME:-$HOME/.holo}"
MANIFEST_URL="${HOLO_INSTALL_MANIFEST_URL:-https://install.hcompany.ai/install/manifest.json}"
INSTALL_TMP="${TMPDIR:-/tmp}/holo-install.$$"

cleanup() {
  rm -rf "$INSTALL_TMP"
}
trap cleanup EXIT INT TERM

info() {
  printf '%s\n' "$*"
}

fail() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

platform_key() {
  system="$(uname -s)"
  machine="$(uname -m)"
  case "$system:$machine" in
    Darwin:arm64) printf 'darwin-arm64' ;;
    Darwin:x86_64) fail "Holo Desktop installer does not support darwin-x86_64 yet because hai-agent-runtime is not published for macOS Intel yet." ;;
    Linux:x86_64) printf 'linux-x86_64' ;;
    Linux:*) fail "Holo Desktop installer does not support linux-$machine yet because hai-agent-runtime is not published for Linux yet." ;;
    *) fail "Holo Desktop installer does not support $system-$machine yet." ;;
  esac
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

linux_build_prerequisites_present() {
  command -v cc >/dev/null 2>&1 &&
    [ -f /usr/include/linux/input.h ] &&
    [ -f /usr/include/linux/input-event-codes.h ]
}

ensure_linux_build_prerequisites() {
  [ "$PLATFORM" = "linux-x86_64" ] || return 0
  linux_build_prerequisites_present && return 0

  command -v apt-get >/dev/null 2>&1 || fail "Linux installation requires a C compiler and Linux input headers. Install your distribution's compiler toolchain and Linux API headers, then rerun the installer."

  info "Installing Linux prerequisites: build-essential linux-libc-dev"
  if [ "$(id -u)" -eq 0 ]; then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends build-essential linux-libc-dev
  elif command -v sudo >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends build-essential linux-libc-dev
  else
    fail "Linux installation requires build-essential and linux-libc-dev. Install them as root, then rerun the installer."
  fi

  linux_build_prerequisites_present || fail "Linux prerequisites were installed, but the C compiler or Linux input headers are still unavailable."
}

download() {
  url="$1"
  dest="$2"
  case "$url" in
    file://*) cp "${url#file://}" "$dest" ;;
    /*) cp "$url" "$dest" ;;
    *) curl -fsSL "$url" -o "$dest" ;;
  esac
}

manifest_value() {
  key="$1"
  field="$2"
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$MANIFEST_PATH" "$key" "$field" <<'PY'
import json
import sys

manifest_path, platform_key, field = sys.argv[1:]
with open(manifest_path, encoding="utf-8") as fh:
    manifest = json.load(fh)
if field in ("holo_version", "python_version", "uv_version"):
    print(manifest[field])
else:
    print(manifest["supported_platforms"][platform_key][field])
PY
  else
    case "$field" in
      holo_version|python_version|uv_version)
        sed -n "s/.*\"$field\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" "$MANIFEST_PATH" | head -n 1
        ;;
      uv_url|uv_sha256)
        sed -n "/\"$key\"[[:space:]]*:/,/}/s/.*\"$field\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" "$MANIFEST_PATH" | head -n 1
        ;;
      *) fail "unsupported manifest field: $field" ;;
    esac
  fi
}

append_path_block() {
  # Write to the rc file the login shell actually sources: zsh on macOS,
  # bash on most Linux; fall back to .profile for anything else.
  case "${SHELL:-}" in
    */zsh) rc_file="$HOME/.zshrc" ;;
    */bash) rc_file="$HOME/.bashrc" ;;
    *) rc_file="$HOME/.profile" ;;
  esac
  path_line="export PATH=\"$HOLO_HOME/bin:\$PATH\""
  mkdir -p "$(dirname "$rc_file")"
  touch "$rc_file"
  if ! grep -Fq "$path_line" "$rc_file"; then
    {
      printf '\n# Holo Desktop\n'
      printf '%s\n' "$path_line"
    } >>"$rc_file"
  fi
}

sha256_of() {
  # sha256sum ships with coreutils on Linux; macOS has shasum instead.
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

verify_sha256() {
  file="$1"
  expected="$2"
  actual="$(sha256_of "$file")"
  [ "$actual" = "$expected" ] || fail "sha256 mismatch for $file: expected $expected, got $actual"
}

need_cmd curl
command -v sha256sum >/dev/null 2>&1 || command -v shasum >/dev/null 2>&1 || fail "missing required command: sha256sum or shasum"
need_cmd tar

PLATFORM="$(platform_key)"
mkdir -p "$INSTALL_TMP" "$HOLO_HOME/bin" "$HOLO_HOME/toolchain/uv"
MANIFEST_PATH="$INSTALL_TMP/manifest.json"

info "Downloading Holo installer manifest..."
download "$MANIFEST_URL" "$MANIFEST_PATH"

HOLO_VERSION="$(manifest_value "$PLATFORM" holo_version)"
PYTHON_VERSION="$(manifest_value "$PLATFORM" python_version)"
UV_URL="$(manifest_value "$PLATFORM" uv_url)"
UV_SHA256="$(manifest_value "$PLATFORM" uv_sha256)"
PACKAGE_SPEC="${HOLO_INSTALL_PACKAGE:-holo-desktop-cli==$HOLO_VERSION}"

[ -n "$HOLO_VERSION" ] || fail "manifest did not include holo_version"
[ -n "$PYTHON_VERSION" ] || fail "manifest did not include python_version"
[ -n "$UV_URL" ] || fail "manifest did not include uv_url for $PLATFORM"
[ -n "$UV_SHA256" ] || fail "manifest did not include uv_sha256 for $PLATFORM"

ensure_linux_build_prerequisites

UV_ARCHIVE="$INSTALL_TMP/uv.tar.gz"
UV_EXTRACT="$INSTALL_TMP/uv"

info "Downloading uv $UV_URL..."
download "$UV_URL" "$UV_ARCHIVE"
verify_sha256 "$UV_ARCHIVE" "$UV_SHA256"
mkdir -p "$UV_EXTRACT"
tar -xzf "$UV_ARCHIVE" -C "$UV_EXTRACT"
UV_FOUND="$(find "$UV_EXTRACT" -type f -name uv -perm -111 2>/dev/null | head -n 1 || true)"
if [ -z "$UV_FOUND" ]; then
  UV_FOUND="$(find "$UV_EXTRACT" -type f -name uv | head -n 1 || true)"
fi
[ -n "$UV_FOUND" ] || fail "downloaded uv archive did not contain a uv executable"
cp "$UV_FOUND" "$HOLO_HOME/toolchain/uv/uv"
chmod 755 "$HOLO_HOME/toolchain/uv/uv"
UV_BIN="$HOLO_HOME/toolchain/uv/uv"

info "Installing Python $PYTHON_VERSION and Holo Desktop CLI..."
UV_PYTHON_INSTALL_DIR="$HOLO_HOME/python" \
UV_TOOL_DIR="$HOLO_HOME/tools" \
UV_TOOL_BIN_DIR="$HOLO_HOME/bin" \
"$UV_BIN" python install "$PYTHON_VERSION" --no-bin

UV_PYTHON_INSTALL_DIR="$HOLO_HOME/python" \
UV_TOOL_DIR="$HOLO_HOME/tools" \
UV_TOOL_BIN_DIR="$HOLO_HOME/bin" \
"$UV_BIN" tool install "$PACKAGE_SPEC" --python "$PYTHON_VERSION" --force --reinstall-package holo-desktop-cli

if [ "${HOLO_INSTALL_SKIP_PATH:-}" != "1" ]; then
  append_path_block
fi

if [ "${HOLO_INSTALL_SKIP_RUN_SETUP:-}" != "1" ]; then
  UV_PYTHON_INSTALL_DIR="$HOLO_HOME/python" \
  UV_TOOL_DIR="$HOLO_HOME/tools" \
  UV_TOOL_BIN_DIR="$HOLO_HOME/bin" \
  "$UV_BIN" run --with "$PACKAGE_SPEC" python -m holo_desktop.installer_bootstrap --yes
fi

info ""
info "Holo installed."
info "Open a new terminal, then run:"
info "  holo login"
info "  holo run \"Open Calculator and compute 2+2\""
info ""
info "Installed command:"
info "  $HOLO_HOME/bin/holo"
