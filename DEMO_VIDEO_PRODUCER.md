# Demo Video Producer

Turns a company URL + a short blurb into a rendered 30-90 second narrated
demo video (MP4). Agent code: `agents/demo_video_producer.py`. HTTP route:
`server.py` (`/agents/demo-video-producer`).

## Pipeline

1. **Capture** — headless Chromium screenshots the homepage (scrolled at a
   few offsets) plus a couple of same-domain internal pages (pricing /
   features / about / product / demo, if linked from the nav), and grabs
   the homepage's visible text.
2. **Script** — Claude writes a scene-by-scene voiceover script sized to
   the target runtime, choosing which captured screenshot each scene shows.
3. **Voice** — ElevenLabs turns each scene's narration into an MP3. The
   *actual* audio duration drives the video timing (not a word-count guess).
4. **Render** — ffmpeg builds a Ken Burns pan/zoom + caption clip per
   scene, a title card and an outro card, and concatenates everything into
   one MP4.

Each stage is isolated: a partial failure returns a `needs_review` or
`blocked` envelope with a clear note, and keeps whatever was already
produced (e.g. the script + narration audio survive a render failure) so a
human can pick up where it stopped instead of losing the run.

## Required environment variables

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | Script generation (same as every other agent in this repo) |
| `ELEVENLABS_API_KEY` | yes | Narration voiceover |
| `CHROMIUM_EXECUTABLE_PATH` | no | Override the Chromium binary Playwright launches. Unset = Playwright's bundled browser (present in the Docker image). |
| `DEMO_VIDEO_OUTPUT_DIR` | no | Where rendered videos are written, keyed by `run_id`. Defaults to `/tmp/demo_videos`. |

Get an ElevenLabs API key and (optionally) a voice ID at
[elevenlabs.io](https://elevenlabs.io) — pass a voice ID per-request via
`voice_id`, or it falls back to a default built-in voice.

## API usage

```bash
curl -X POST https://<your-deploy>/agents/demo-video-producer \
  -H "Content-Type: application/json" \
  -d '{
        "url": "https://example.com",
        "company_name": "Example Co",
        "company_info": "One or two sentences about what they sell and who it is for.",
        "target_duration_seconds": 60
      }'
```

On `"status": "ok"`, the response payload includes `download_url`
(`/agents/demo-video-producer/download/<run_id>`) — `GET` that path to
fetch the rendered MP4.

## Deploying (Railway)

This repo now includes a `Dockerfile` at the root. Railway auto-detects it
and builds from it instead of Nixpacks — the base image
(`mcr.microsoft.com/playwright/python`) already bundles a matching
Chromium; the Dockerfile adds `ffmpeg` and DejaVu fonts on top. No extra
Railway build config is needed, but:

- The image is meaningfully bigger than before (~2GB) and the build takes
  longer the first time. Expect a couple of minutes.
- Set `ANTHROPIC_API_KEY` and `ELEVENLABS_API_KEY` in Railway's environment
  variables.
- The gunicorn timeout is bumped to 600s (`Dockerfile` `CMD`) — a 60-90s
  video with ~6 scenes typically renders in well under that, but it's a
  single synchronous request end-to-end (capture + TTS + ffmpeg), so leave
  headroom if you raise `max_scenes` or the target duration.
- If `playwright` is ever bumped in `requirements.txt`, bump the
  Dockerfile's base image tag to match (mismatched pip/browser versions
  will fail at launch) — see the comments in both files.

## Local testing

```bash
pip install -r requirements.txt
python -m playwright install --with-deps chromium   # one-time, downloads Chromium
export ANTHROPIC_API_KEY=...
export ELEVENLABS_API_KEY=...
python -m agents.demo_video_producer   # smoke test against example.com
```

`pytest` runs the full mocked unit-test suite
(`tests/test_demo_video_producer.py`) with no browser, ffmpeg, or API keys
needed — every external call is mocked at its seam (`_capture_site`,
`_synthesize_narration`, `_render_video`).

## Known limitations

- Synchronous request/response — there's no job queue yet. Fine for one-off
  or low-volume use; if this needs to scale to many concurrent requests,
  move rendering to a background worker and poll/webhook for completion.
- If you run this behind a corporate/egress HTTP(S) proxy, `_capture_site`
  reads `HTTPS_PROXY` and bypasses it for localhost — it does **not**
  bypass it for the target company's own domain, so a proxy that blocks or
  intercepts that domain will make capture fail loudly (it checks the
  navigation response status rather than silently screenshotting an error
  page).
