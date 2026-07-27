# Sourcing the video — getting a downloadable file

The pipeline needs a local video file. Everything downstream is solved; getting the file is where real jobs fail. This page covers the failures you'll actually hit.

## Rights check first

Only clip footage you own or have permission to use. Re-cutting a third party's video and reposting it gets accounts struck on every platform. If the source is someone else's channel, stop and confirm rights before rendering anything.

## The two YouTube failure modes (they look similar, they are not)

### A. "Only images are available for download"

```
web: WARNING: Only images are available for download. use --list-formats to see them
ERROR: [youtube] <ID>: Requested format is not available. Use --list-formats for a list of available formats
```

**What it means:** YouTube returned a player response containing *only storyboard thumbnails* (`sb0`, `sb1`, …) and no audio/video streams. `-f` then can't match anything, so yt-dlp reports "requested format is not available." The format selector is not the problem — do not go hunting for a different `-f` string, there is nothing to select.

**Cause:** the request lacked a valid **GVS PO token** (proof-of-origin), or yt-dlp couldn't solve YouTube's JavaScript challenge. YouTube withholds stream URLs from clients it can't verify.

**Fix, in order:**

1. **Update yt-dlp.** YouTube changes this often; a build a few weeks old is already stale.
   ```bash
   pip install -U yt-dlp        # or: yt-dlp -U
   ```
2. **Install a JavaScript runtime.** yt-dlp needs one to solve the challenge. Only Deno is enabled by default; point it at Node explicitly if that's what you have.
   ```bash
   yt-dlp --js-runtimes node:/usr/bin/node ...
   ```
   Without a runtime you get: `No supported JavaScript runtime could be found`.
3. **Run a PO token provider.** This is the actual fix for "only images." Install the plugin and its server:
   ```bash
   pip install bgutil-ytdlp-pot-provider
   git clone --depth 1 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git
   cd bgutil-ytdlp-pot-provider/server && npm install && npx tsc
   node build/main.js          # listens on 127.0.0.1:4416
   ```
   The plugin auto-discovers the server at `http://127.0.0.1:4416` — no yt-dlp flags needed. Verify before retrying:
   ```bash
   curl -s http://127.0.0.1:4416/ping
   curl -s -X POST http://127.0.0.1:4416/get_pot \
     -H "Content-Type: application/json" -d '{"content_binding":"<VIDEO_ID>"}'
   ```
   A JSON body with a `poToken` field means it's working. An HTTP 500 means it isn't — check the server's own log, not yt-dlp's.
4. **Confirm it took** with `yt-dlp -v`, which prints the provider status:
   ```
   [debug] [youtube] [pot] PO Token Providers: bgutil:http-1.3.1 (external)
   [youtube] [pot:bgutil:http] Generating a gvs PO Token for web client
   ```

### B. "Sign in to confirm you're not a bot" / HTTP 429

```
ERROR: [youtube] <ID>: Sign in to confirm you're not a bot.
WARNING: Unable to download webpage: HTTP Error 429: Too Many Requests
```

**Different problem — IP reputation, not tokens.** A PO token provider will not fix this. YouTube is rate-limiting or blocking the source IP.

- Datacenter and cloud IPs (AWS, GCP, CI runners, most VPS) are flagged aggressively. A home or residential IP usually is not.
- Repeated failed attempts from one IP escalate it. Back off rather than retrying in a loop — retries make it worse.
- Run the download from a residential connection, or pass cookies from a signed-in browser session:
  ```bash
  yt-dlp --cookies-from-browser firefox ...
  ```

**Read the error text carefully:** "only images" means tokens, "sign in to confirm" or 429 means IP. Fixing the wrong one wastes hours.

### C. "This video is DRM protected"

Emitted when using the `tv` client. YouTube applies DRM to some sessions on that client. Drop `tv` from `player_client` and use the default clients instead. Do not attempt to circumvent DRM.

## Running the token server behind an HTTP proxy

If your machine routes outbound traffic through a proxy, the bgutil server can fail with:

```
Could not get BotGuard challenge (caused by ... status code 405)
```

Its HTTP client picks up `HTTP_PROXY`/`HTTPS_PROXY` and sends plain `GET https://...` requests to the proxy instead of opening a `CONNECT` tunnel; a correct proxy rejects those. Fix by telling axios to stay out of it and use the proxy-aware agent already configured — in `server/build/session_manager.js`, add `proxy: false` to the axios options:

```js
const axiosOpt = {
    headers: options?.headers,
    params: options?.params,
    httpsAgent: proxySpec.asDispatcher(logger),
    proxy: false,          // <-- use the agent's CONNECT tunnel, not axios' own proxy handling
};
```

Also give Node your proxy's CA so TLS verification passes, otherwise the solver script download fails with `CERTIFICATE_VERIFY_FAILED`:

```bash
NODE_EXTRA_CA_CERTS=/path/to/ca-bundle.crt node build/main.js
```

Never disable TLS verification to get around this.

## Keeping the server alive

The token server is a long-running daemon. Started with `&` from a short-lived shell it dies with that shell, and the next download fails with a connection-refused that looks like a yt-dlp bug. Run it under systemd, Docker, `tmux`, or your process manager, and health-check `/ping` before each batch.

## Skipping the download entirely

Cleanest path when it's your own content: use the original file. Export from your recorder (Riverside, Zoom, OBS, StreamYard) and feed the pipeline directly — no bot detection, no tokens, and better source quality than a re-encoded YouTube stream.
