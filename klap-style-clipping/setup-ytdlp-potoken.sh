#!/usr/bin/env bash
# Fix "Only images are available for download" / "Requested format is not available"
# by installing and starting a PO token provider for yt-dlp.
#
# Run this ON THE MACHINE THAT ACTUALLY RUNS yt-dlp. If your clipper runs in
# Docker, run it INSIDE that container, or see the compose notes at the bottom.
#
#   bash setup-ytdlp-potoken.sh [VIDEO_ID_TO_TEST]
#
# Safe to re-run. Installs to ~/.bgutil-pot, starts the server on 127.0.0.1:4416.

set -uo pipefail

TEST_ID="${1:-yB05HiKCCuI}"
INSTALL_DIR="${BGUTIL_DIR:-$HOME/.bgutil-pot}"
PORT="${BGUTIL_PORT:-4416}"
LOG="$INSTALL_DIR/server.log"

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; }
info() { printf '\n\033[1m%s\033[0m\n' "$1"; }

FAILED=0

info "1. Checking prerequisites"

if command -v node >/dev/null 2>&1; then
  NODE_BIN="$(command -v node)"
  ok "node $(node --version) at $NODE_BIN"
else
  bad "node not found — install Node.js 18+ and re-run"
  exit 1
fi

command -v npm >/dev/null 2>&1 && ok "npm $(npm --version)" || { bad "npm not found"; exit 1; }
command -v git >/dev/null 2>&1 && ok "git present" || { bad "git not found"; exit 1; }

PIP=""
for c in pip3 pip; do command -v "$c" >/dev/null 2>&1 && { PIP="$c"; break; }; done
[ -n "$PIP" ] && ok "$PIP present" || { bad "pip not found"; exit 1; }

info "2. Updating yt-dlp and installing the PO token plugin"

# --break-system-packages is needed on Debian/Ubuntu PEP668 systems; harmless elsewhere.
PIPFLAGS=""
$PIP install --dry-run --break-system-packages pip >/dev/null 2>&1 && PIPFLAGS="--break-system-packages"

$PIP install -q -U $PIPFLAGS yt-dlp            && ok "yt-dlp $(yt-dlp --version)" || { bad "yt-dlp update failed"; FAILED=1; }
$PIP install -q -U $PIPFLAGS bgutil-ytdlp-pot-provider && ok "bgutil plugin installed" || { bad "plugin install failed"; FAILED=1; }

info "3. Building the token server"

if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull -q --ff-only && ok "repo updated" || ok "repo present (pull skipped)"
else
  rm -rf "$INSTALL_DIR"
  git clone -q --depth 1 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git "$INSTALL_DIR" \
    && ok "cloned to $INSTALL_DIR" || { bad "clone failed"; exit 1; }
fi

cd "$INSTALL_DIR/server" || exit 1
npm install --silent >/dev/null 2>&1 && ok "npm deps installed" || { bad "npm install failed"; FAILED=1; }
npx --yes tsc >/dev/null 2>&1
[ -f build/main.js ] && ok "server built" || { bad "build failed — no build/main.js"; exit 1; }

info "4. Patching for HTTP proxy environments"

# If the box routes outbound traffic through a proxy, axios sends plain
# GET https://... to it instead of opening a CONNECT tunnel, and the proxy
# answers 405. Forcing proxy:false makes it use the proxy-aware agent instead.
if grep -q "proxy: false" build/session_manager.js 2>/dev/null; then
  ok "proxy patch already applied"
elif grep -q "httpsAgent: proxySpec.asDispatcher(logger)," build/session_manager.js 2>/dev/null; then
  sed -i 's/httpsAgent: proxySpec.asDispatcher(logger),/httpsAgent: proxySpec.asDispatcher(logger),\n                        proxy: false,/' build/session_manager.js \
    && ok "proxy patch applied" || bad "proxy patch failed (usually harmless)"
else
  ok "no proxy patch needed for this version"
fi

info "5. Starting the server on 127.0.0.1:$PORT"

# Kill any previous instance of THIS server only (matched by its install path).
pkill -f "$INSTALL_DIR/server/build/main.js" >/dev/null 2>&1 && sleep 1

CA_ARG=""
for ca in /etc/ssl/certs/ca-certificates.crt "${NODE_EXTRA_CA_CERTS:-}"; do
  [ -n "$ca" ] && [ -f "$ca" ] && CA_ARG="$ca" && break
done

NODE_EXTRA_CA_CERTS="$CA_ARG" setsid nohup "$NODE_BIN" "$INSTALL_DIR/server/build/main.js" \
  --port "$PORT" > "$LOG" 2>&1 < /dev/null &
sleep 4

if curl -sf -m 10 "http://127.0.0.1:$PORT/ping" >/dev/null 2>&1; then
  ok "server responding on port $PORT (log: $LOG)"
else
  bad "server not responding — check $LOG"
  tail -5 "$LOG" 2>/dev/null | sed 's/^/      /'
  FAILED=1
fi

info "6. Verifying token generation"

POT=$(curl -s -m 120 -X POST "http://127.0.0.1:$PORT/get_pot" \
  -H "Content-Type: application/json" -d "{\"content_binding\":\"$TEST_ID\"}" 2>/dev/null)

if printf '%s' "$POT" | grep -q '"poToken"'; then
  ok "minted a PO token for $TEST_ID"
else
  bad "token generation FAILED — this is the real problem"
  printf '      response: %s\n' "$(printf '%s' "$POT" | head -c 200)"
  printf '      server log:\n'; tail -8 "$LOG" 2>/dev/null | sed 's/^/      /'
  FAILED=1
fi

info "7. End-to-end test: can yt-dlp see real formats?"

OUT=$(yt-dlp --js-runtimes "node:$NODE_BIN" -F --no-playlist \
  "https://www.youtube.com/watch?v=$TEST_ID" 2>&1)

if printf '%s' "$OUT" | grep -qE "video only|audio only"; then
  ok "real video/audio formats returned — FIXED"
  printf '%s\n' "$OUT" | grep -E "1080|720" | tail -2 | sed 's/^/      /'
elif printf '%s' "$OUT" | grep -q "Only images are available"; then
  bad "STILL only images — the token provider is not reaching yt-dlp"
  printf '      Run: yt-dlp -v -F "https://www.youtube.com/watch?v=%s" 2>&1 | grep pot\n' "$TEST_ID"
  printf '      That line shows whether the provider is loaded at all.\n'
  FAILED=1
elif printf '%s' "$OUT" | grep -qE "not a bot|429"; then
  bad "IP blocked (bot check / 429) — a DIFFERENT problem, tokens will not fix it"
  printf '      This IP is rate-limited by YouTube. Use a residential IP or\n'
  printf '      pass --cookies-from-browser <browser>.\n'
  FAILED=1
else
  bad "unexpected result:"
  printf '%s\n' "$OUT" | tail -4 | sed 's/^/      /'
  FAILED=1
fi

info "Result"
if [ "$FAILED" -eq 0 ]; then
  printf '  \033[32mAll checks passed.\033[0m Restart your clipper service so it picks up the new yt-dlp.\n'
  printf '  Keep the token server running — it must stay up for every job.\n\n'
else
  printf '  \033[31mSomething is still broken.\033[0m See the ✗ lines above.\n'
  printf '  Server log: %s\n\n' "$LOG"
fi
exit "$FAILED"
