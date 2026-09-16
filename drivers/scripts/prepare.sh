#!/usr/bin/env bash
#
# prepare.sh - DKMS PRE_BUILD hook for yoga-duet-ipu6-cameras
#
# Reconstructs the four camera driver .c files from an upstream baseline plus
# our custom patches, so the package stays in sync with kernel updates without
# shipping full copies of the kernel tree.
#
# For the two in-kernel drivers (ipu-bridge, int3472) the baseline is fetched
# by kernel version (e.g. 7.2.3 -> v7.2.3) from the linux-stable repo
# (gregkh/linux).  Missing baselines for already-known tags are re-fetched only
# if offline(-capable) cache exists; a local copy is kept under baseline-cache/
# so later builds work even without network.
#
# ov5678 and gc5035 are vendored inside baseline-cache/ and never track the
# kernel version.  ov5678 is a standalone driver derived from the in-kernel
# ov5675 driver (renamed symbols, OV5678 golden PLL/VTS values, OVTI5678-only
# ACPI match); keeping its full source here guarantees it cannot drift with or
# interfere with the in-kernel ov5675 driver.  gc5035 is NOT in the kernel tree
# (Intel ipu6-drivers only).  Both are copied verbatim from baseline-cache/
# each build; no patch is applied on top of them.
#
# This script is idempotent: it only re-generates files when the baseline or
# the kernel version changes, and it bails loudly (never silently) on failure.
#
# Exit codes:
#   0  success (all source files present & patched)
#   1  one or more required baseline files could not be obtained
#   2  a patch failed to apply cleanly

set -u

# --- resolve directories ---------------------------------------------------
# DKMS runs PRE_BUILD with the working directory *above* dkms.conf's source
# dir; prefer an explicit DKMS_BUILD_ROOT env, else fall back to realpath.
# NOTE: under 'dkms build' this is the *per-kernel copy* at
#   /var/lib/dkms/<pkg>/<ver>/build/
# which dkms deletes again after 'dkms install'.  SRC_DIR and PATCHES_DIR must
# stay rooted here (that is exactly the tree 'make' compiles from), but the
# baseline cache must NOT - see CACHE_DIR below.
DKMS_BUILD_ROOT="${DKMS_BUILD_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
PATCHES_DIR="$DKMS_BUILD_ROOT/patches"
SRC_DIR="$DKMS_BUILD_ROOT/src"

# Persistent baseline cache.  dkms copies the registered source tree into a
# throwaway build/ dir, runs PRE_BUILD there and removes it after install, so a
# cache written under build/ would silently vanish after every install (and the
# next offline build would fail).  The registered source tree survives; dkms
# exposes it as the sibling 'source' symlink
#   /var/lib/dkms/<pkg>/<ver>/source -> /usr/src/<pkg>-<ver>
# Prefer that.  When run by hand from /usr/src (no such symlink) fall back to
# the script's own tree.  DKMS_CACHE_DIR overrides everything.
if [ -z "${DKMS_CACHE_DIR:-}" ]; then
  _srclink="$DKMS_BUILD_ROOT/../source"
  if [ -L "$_srclink" ] && [ -d "$_srclink" ]; then
    CACHE_DIR="$(cd "$_srclink" && pwd)/baseline-cache"
  else
    CACHE_DIR="$DKMS_BUILD_ROOT/baseline-cache"
  fi
else
  CACHE_DIR="$DKMS_CACHE_DIR"
fi

# --- resolve kernel version -> upstream tag --------------------------------
# kernelver comes from DKMS as e.g. '7.2.3-1-cachyos' or '7.2.3'.  We only
# need the first three numeric components -> '7.2.3' -> tag 'v7.2.3'.
KVER_RAW="${kernelver:-$(uname -r)}"
KVER="$(printf '%s\n' "$KVER_RAW" | sed -E 's/^([0-9]+\.[0-9]+\.[0-9]+).*/\1/')"
TAG="v${KVER}"

# --- baseline definition ---------------------------------------------------
# in-kernel baselines are fetched from gregkh/linux by tag; ov5678 and gc5035
# are vendored (copied verbatim from baseline-cache/, no patch applied).
declare -A BASELINE=( )
# int3472 needs 4 files but only discrete.c is patched; the other three are
# used verbatim.

# Files to fetch per source dir (relative to the kernel tree).
IPU_BRIDGE_FETCH=( "drivers/media/pci/intel/ipu-bridge.c" )
INT3472_FETCH=(
  "drivers/platform/x86/intel/int3472/discrete.c"
  "drivers/platform/x86/intel/int3472/discrete_quirks.c"
  "drivers/platform/x86/intel/int3472/clk_and_regulator.c"
  "drivers/platform/x86/intel/int3472/led.c"
)

UPSTREAM="https://raw.githubusercontent.com/gregkh/linux/${TAG}"

log() { printf '[prepare] %s\n' "$*"; }
die()  { printf '[prepare] ERROR: %s\n' "$*" >&2; exit "${2:-1}"; }

# --- helper: download one file, tolerating IPv6-only environments ----------
# Many hosts resolve raw.githubusercontent.com to IPv6 first, but have no
# working IPv6 route (TLS connect then fails with "unexpected eof").  Try the
# system default first, then force IPv4.  Sets $FETCH_RETRY_IPV4=1 when the
# IPv4 fallback was the one that succeeded.
# $1 = upstream URL, $2 = destination path
curl_fetch() {
  local url="$1" dest="$2"
  if curl -fsSL --max-time 60 "$url" -o "$dest" 2>/dev/null; then
    return 0
  fi
  if curl -4 -fsSL --max-time 60 "$url" -o "$dest" 2>/dev/null; then
    FETCH_RETRY_IPV4=1
    return 0
  fi
  return 1
}

# --- helper: find the closest cached baseline version -----------------------
# Returns the largest cached version <= $KVER (e.g. 7.2.3 when 7.2.5 is not
# cached yet), preferring an exact match.  Prints nothing if none exist.
find_nearest_cache() {
  local subdir="$1" dest="$2" v best=""
  for v in $(ls -1 "$CACHE_DIR" 2>/dev/null | sort -V); do
    [ -s "$CACHE_DIR/$v/$subdir/$dest" ] || continue
    best="$v"
    [ "$v" = "$KVER" ] && break
  done
  [ -n "$best" ] && printf '%s\n' "$best"
}

# --- helper: fetch a single baseline file -----------------------------------
# $1 = subdir in src/ where the file lands
# $2 = destination file name in that dir
# $3 = upstream path (or empty for vendored gc5035)
fetch_baseline() {
  local subdir="$1" dest="$2" upstream_path="$3"
  local dest_path="$SRC_DIR/$subdir/$dest"
  local cache_path="$CACHE_DIR/$KVER/$subdir/$dest"

  # 1) fresh online fetch (overwrites anything stale)
  if [ -n "$upstream_path" ]; then
    # Distinguish a write/permission failure (target dir not writable, e.g.
    # running as non-root into /usr/src) from a genuine network/download
    # failure.  curl -o writes the file itself, so a failed download *and* an
    # unwritable target both make `curl` return non-zero; the two must not be
    # conflated into a misleading "network offline" message.
    if [ ! -d "$SRC_DIR/$subdir" ]; then
      die "cannot write baseline: $SRC_DIR/$subdir does not exist or is not writable by $(id -un) (DKMS builds run as root; running manually? use sudo)"
    fi
    mkdir -p "$SRC_DIR/$subdir"
    FETCH_RETRY_IPV4=0
    if curl_fetch "$UPSTREAM/$upstream_path" "$dest_path"; then
      if [ ! -s "$dest_path" ]; then
        die "downloaded $upstream_path is empty; likely a server error for ${TAG}"
      fi
      mkdir -p "$(dirname "$cache_path")"
      if cp -f "$dest_path" "$cache_path" 2>/dev/null; then
        :
      else
        log "WARNING: could not seed baseline cache at $cache_path (not fatal; offline rebuilds may need network)"
      fi
      if [ "$FETCH_RETRY_IPV4" = 1 ]; then
        log "fetched $upstream_path (${TAG}) via IPv4 fallback -> $subdir/$dest"
      else
        log "fetched $upstream_path (${TAG}) -> $subdir/$dest"
      fi
      return 0
    fi
    if [ ! -w "$SRC_DIR/$subdir" ]; then
      die "online download succeeded but could not write $dest_path (directory $SRC_DIR/$subdir not writable by $(id -un)); run as root or check permissions"
    fi
    log "online fetch failed for $upstream_path (network down, IPv6-only route, or ${TAG} missing upstream); falling back to cache"
  fi

  # 2) exact-version cache fallback (works offline)
  if [ -s "$cache_path" ]; then
    mkdir -p "$SRC_DIR/$subdir"
    cp -f "$cache_path" "$dest_path"
    log "using cached baseline $subdir/$dest ($KVER)"
    return 0
  fi

  # 3) nearest older cached version (forward-compatible in practice: the
  #    baselines are stable across stable point releases).  Enabling this
  #    avoids having to build once online just to seed a new kernel's cache.
  #    If the subsequent patch no longer applies, apply_patch() errors out and
  #    tells you to regenerate it - so this fallback never silently ships a
  #    wrong driver.
  if [ -n "$upstream_path" ]; then
    local near
    near="$(find_nearest_cache "$subdir" "$dest")"
    if [ -n "$near" ]; then
      mkdir -p "$SRC_DIR/$subdir"
      cp -f "$CACHE_DIR/$near/$subdir/$dest" "$dest_path"
      log "WARNING: no baseline for ${KVER}; using nearest cached ${near} for $subdir/$dest - verify the patch still applies"
      return 0
    fi
  fi

  # NOTE: gc5035 is handled separately (vendored baseline), never reaches here.
  die "no baseline available for $subdir/$dest (network offline and no cache) - run once with network, or vendor the ${KVER} baseline"
}

# --- helper: apply a patch with fuzz tolerance ------------------------------
# $1 = patch file
# $2 = directory where the target file lives
#
# Because fetch_baseline() ALWAYS overwrites the target from a pristine
# baseline (network or cache) just before this runs, "already applied" should
# never happen in normal operation.  A clean -p1 apply is attempted first;
# on failure we retry with a small fuzz to absorb minor line-drift from newer
# kernels.  Any remaining reject leaves a .rej file -> hard error.
apply_patch() {
  local patch="$1" dir="$2"
  rm -f "$dir"/*.rej "$dir"/*.orig 2>/dev/null || true
  if ! ( cd "$dir" && patch -p1 -f --no-backup-if-mismatch < "$patch" ) >/dev/null 2>&1; then
    # try with fuzz for slightly-drifting baselines
    if ! ( cd "$dir" && patch -p1 -f -F 3 --no-backup-if-mismatch < "$patch" ) >/dev/null 2>&1; then
      if ls "$dir"/*.rej >/dev/null 2>&1; then
        die "patch $(basename "$patch") did not apply cleanly (rejects in $dir) - baseline may have drifted for kernel $TAG; regenerate the patch from the new baseline or pin KVER"
      else
        die "patch $(basename "$patch") did not apply (too much drift for kernel $TAG)"
      fi
    fi
  fi
  rm -f "$dir"/*.orig "$dir"/*.rej 2>/dev/null || true
  log "applied $(basename "$patch")"
}

# --- main -------------------------------------------------------------------
mkdir -p "$SRC_DIR/ov5678" "$SRC_DIR/gc5035" "$SRC_DIR/ipu_bridge" "$SRC_DIR/int3472"

# -- ov5678 (vendored standalone driver, always local; always overwrite so
#    re-runs are idempotent against the pristine vendored source) --
mkdir -p "$SRC_DIR/ov5678"
if [ -s "$CACHE_DIR/ov5678/ov5678.c" ]; then
  cp -f "$CACHE_DIR/ov5678/ov5678.c" "$SRC_DIR/ov5678/ov5678.c"
else
  die "vendored ov5678 driver is missing ($CACHE_DIR/ov5678/ov5678.c)"
fi

# -- ipu-bridge (in-kernel) --
fetch_baseline ipu_bridge ipu-bridge.c "drivers/media/pci/intel/ipu-bridge.c"
apply_patch "$PATCHES_DIR/002-ipu-bridge.patch" "$SRC_DIR/ipu_bridge"

# -- int3472: four files, only discrete.c is patched --
for f in "${INT3472_FETCH[@]}"; do
  base="$(basename "$f")"
  fetch_baseline int3472 "$base" "$f"
done
apply_patch "$PATCHES_DIR/003-int3472-discrete.patch" "$SRC_DIR/int3472"

# -- gc5035 (vendored baseline, always local; always overwrite so re-runs are
#    idempotent against the pristine baseline rather than a previously-patched
#    file) --
mkdir -p "$SRC_DIR/gc5035"
if [ -s "$CACHE_DIR/gc5035/gc5035.c" ]; then
  cp -f "$CACHE_DIR/gc5035/gc5035.c" "$SRC_DIR/gc5035/gc5035.c"
else
  die "vendored gc5035 baseline is missing ($CACHE_DIR/gc5035/gc5035.c)"
fi
apply_patch "$PATCHES_DIR/004-gc5035.patch" "$SRC_DIR/gc5035"

log "all source files prepared: ov5678.c ipu-bridge.c int3472/*.c gc5035.c"
exit 0
