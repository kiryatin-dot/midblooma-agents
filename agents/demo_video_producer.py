"""
AGENT 9 — Demo Video Producer
Turns a company URL + a short blurb into a fully rendered 30-90 second
narrated demo video (MP4): screen-captured visuals, an AI-written script,
ElevenLabs voiceover, and an ffmpeg-assembled Ken Burns / caption edit.

Trigger:  On-demand — call with { url, company_name, company_info }
Receives: No upstream envelope. This agent is an entry point (e.g. sales /
          prospecting tooling), not part of the daily/weekly content chain.
Sends to: Nobody automatically — returns the rendered video path/duration
          for a human to review and share.

Pipeline:
  1. Capture  — headless-browser screenshots of the homepage (+ a couple of
                same-domain internal pages) and the page's visible text.
  2. Script   — Claude writes a scene-by-scene voiceover script sized to the
                target runtime (30-90s), choosing which captured screenshot
                each scene shows.
  3. Voice    — ElevenLabs turns each scene's narration into an MP3. The
                *actual* audio duration (not a word-count guess) drives the
                video timing.
  4. Render   — ffmpeg builds a Ken Burns pan/zoom + caption clip per scene,
                a title card and an outro card, and concatenates everything
                into one MP4.

Failure handling: each stage is isolated so a partial failure downgrades the
envelope to "needs_review" / "blocked" with a clear note instead of losing
work — e.g. if rendering fails, the script and narration audio already
produced are still returned in the payload for a human to finish by hand.

External dependencies (only required at call time, not import time):
  - ANTHROPIC_API_KEY   — script generation (agents.shared, same as every
                           other agent in this repo)
  - ELEVENLABS_API_KEY  — narration voiceover
  - A Chromium binary for Playwright, and the `ffmpeg`/`ffprobe` binaries,
    available on PATH (see Dockerfile / DEMO_VIDEO_PRODUCER.md for how the
    deploy provisions these).

Every real external call (browser, ElevenLabs, ffmpeg) happens through the
`_capture_site`, `_synthesize_narration`, and `_render_video` seams so tests
can mock each one independently — see tests/test_demo_video_producer.py.
"""
import json
import os
import subprocess
import tempfile
from typing import Any

import anthropic
import requests

from .shared.constants import DEFAULT_MODEL
from .shared.envelope import make_envelope, new_run_id, parse_json_response

AGENT_ID = "demo_video_producer"

# ─────────────────────────────────────────────
# Tunables
# ─────────────────────────────────────────────
MIN_DURATION_SECONDS = 30
MAX_DURATION_SECONDS = 90
DEFAULT_DURATION_SECONDS = 60
MAX_SCENES = 6
WORDS_PER_SECOND = 2.4  # ~144 wpm, a comfortable narration pace

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30

DEFAULT_ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs "Rachel"
ELEVENLABS_MODEL_ID = "eleven_turbo_v2_5"

TITLE_CARD_BG = "#4f46e5"
OUTRO_CARD_BG = "#0f172a"

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

SYSTEM_PROMPT = """
You are the Demo Video Producer. You write tight, sales-ready voiceover
scripts for short (30-90 second) product demo videos, based on a company's
own website content.

You will be given: the company's name, a short blurb about it, its
homepage URL, the page's visible text, and a list of screenshot labels that
were actually captured from the site (e.g. "hero", "section_2",
"pricing_hero"). You may ONLY reference visuals from that exact list — never
invent a label that wasn't given to you.

Write a scene-by-scene script:
- Scene 1 is always the intro: role "intro", visual "title_card". Hook the
  viewer in one punchy sentence — what the company does and who it's for.
- The middle scenes each cover one concrete feature or benefit found in the
  page text, paired with one of the given screenshot labels (reuse a label
  if you have more scenes than screenshots).
- The final scene is always the outro: role "outro", visual "title_card".
  A clear, short call to action.

RULES:
- Total narration across all scenes must read aloud in close to the target
  duration at a natural pace (~2.4 words/second). Err toward slightly under,
  never over.
- Narration is spoken text: no markdown, no emoji, no parentheticals.
- Caption is a short on-screen text overlay for the same scene (max 8 words,
  punchy, not just a repeat of the narration).
- Never invent features, numbers, customers, or claims that aren't
  supported by the page text you were given.
- Plain, confident, human voice — like a founder walking someone through
  their own product, not an ad.

Output ONLY valid JSON, no prose outside the JSON:
{
  "video_title": "string",
  "voice_style": "energetic | professional | warm | confident",
  "scenes": [
    {
      "scene_id": 1,
      "role": "intro | feature | outro",
      "visual": "title_card | <one of the given screenshot labels>",
      "narration": "string — spoken text for this scene",
      "caption": "string — short on-screen text, max 8 words"
    }
  ]
}
""".strip()


# ─────────────────────────────────────────────
# Stage 1 — Capture
# ─────────────────────────────────────────────
def _capture_site(
    url: str,
    out_dir: str,
    max_scenes: int = MAX_SCENES,
    timeout_ms: int = 30000,
) -> dict[str, Any]:
    """
    Screenshot the homepage (scrolled at even offsets) plus a couple of
    same-domain internal pages, and extract the homepage's visible text.

    Returns:
        {
          "site_title": str,
          "page_text": str,
          "screenshots": [{"label": str, "path": str, "page_url": str}, ...],
        }
    """
    from playwright.sync_api import sync_playwright  # imported lazily
    from urllib.parse import urljoin, urlparse

    executable_path = os.environ.get("CHROMIUM_EXECUTABLE_PATH") or None
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    launch_proxy = (
        {"server": proxy_url, "bypass": "localhost,127.0.0.1,::1"}
        if proxy_url
        else None
    )

    screenshots: list[dict[str, str]] = []
    page_text = ""
    site_title = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=executable_path,
            headless=True,
            proxy=launch_proxy,
        )
        try:
            page = browser.new_page(
                viewport={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT}
            )
            response = page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            if response is None or not response.ok:
                status = response.status if response else "no response"
                raise RuntimeError(f"Navigation to {url} failed (HTTP {status}).")
            site_title = page.title()
            page_text = page.inner_text("body")[:6000]

            # Hero shot
            hero_path = os.path.join(out_dir, "shot_hero.png")
            page.screenshot(path=hero_path)
            screenshots.append({"label": "hero", "path": hero_path, "page_url": url})

            # A few more shots scrolled down the homepage
            full_height = page.evaluate("document.body.scrollHeight") or VIDEO_HEIGHT
            remaining = max(max_scenes - 1, 0)
            homepage_extra = min(remaining, 3)
            for i in range(1, homepage_extra + 1):
                offset = int(full_height * i / (homepage_extra + 1))
                page.evaluate(f"window.scrollTo(0, {offset})")
                page.wait_for_timeout(250)
                shot_path = os.path.join(out_dir, f"shot_section_{i}.png")
                page.screenshot(path=shot_path)
                screenshots.append(
                    {"label": f"section_{i}", "path": shot_path, "page_url": url}
                )

            # A couple of same-domain internal pages, if we have scene budget left
            budget = max_scenes - len(screenshots)
            if budget > 0:
                domain = urlparse(url).netloc
                hrefs = page.eval_on_selector_all(
                    "a[href]", "els => els.map(e => e.getAttribute('href'))"
                )
                keywords = ("pricing", "feature", "product", "about", "demo")
                candidates = []
                seen = set()
                for href in hrefs or []:
                    if not href:
                        continue
                    full = urljoin(url, href)
                    if urlparse(full).netloc != domain:
                        continue
                    if full in seen or full.rstrip("/") == url.rstrip("/"):
                        continue
                    if any(kw in href.lower() for kw in keywords):
                        seen.add(full)
                        candidates.append(full)

                for j, sub_url in enumerate(candidates[:budget], start=1):
                    try:
                        sub_response = page.goto(
                            sub_url, wait_until="networkidle", timeout=timeout_ms
                        )
                        if sub_response is None or not sub_response.ok:
                            continue  # a broken internal link shouldn't sink the run
                        shot_path = os.path.join(out_dir, f"shot_page_{j}.png")
                        page.screenshot(path=shot_path)
                        screenshots.append(
                            {"label": f"page_{j}", "path": shot_path, "page_url": sub_url}
                        )
                    except Exception:
                        continue  # a broken internal link shouldn't sink the run
        finally:
            browser.close()

    return {"site_title": site_title, "page_text": page_text, "screenshots": screenshots}


# ─────────────────────────────────────────────
# Stage 2 — Script
# ─────────────────────────────────────────────
def _generate_script(
    company_name: str,
    company_info: str,
    url: str,
    site_title: str,
    page_text: str,
    screenshot_labels: list[str],
    target_duration_seconds: int,
) -> dict[str, Any]:
    target_words = int(target_duration_seconds * WORDS_PER_SECOND)

    user_message = (
        f"Company name: {company_name}\n"
        f"Company blurb: {company_info or '(none provided)'}\n"
        f"URL: {url}\n"
        f"Page title: {site_title}\n"
        f"Target video duration: {target_duration_seconds} seconds "
        f"(~{target_words} words of narration total)\n"
        f"Captured screenshot labels (only use these): {json.dumps(screenshot_labels)}\n\n"
        f"Homepage visible text:\n{page_text}\n\n"
        "Write the scene-by-scene script now. Return only valid JSON."
    )

    client = anthropic.Anthropic()
    with client.messages.stream(
        model=DEFAULT_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        response = stream.get_final_message()

    text = next((b.text for b in response.content if b.type == "text"), "")
    script = parse_json_response(text)  # may raise json.JSONDecodeError

    # Clamp every scene's visual to a label we actually captured or "title_card"
    valid_visuals = set(screenshot_labels) | {"title_card"}
    fallback_visual = screenshot_labels[0] if screenshot_labels else "title_card"
    for scene in script.get("scenes", []):
        if scene.get("visual") not in valid_visuals:
            scene["visual"] = fallback_visual

    return script


# ─────────────────────────────────────────────
# Stage 3 — Voice
# ─────────────────────────────────────────────
def _probe_audio_duration(path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", path,
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def _synthesize_narration(
    scenes: list[dict[str, Any]],
    out_dir: str,
    voice_id: str | None = None,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """
    Calls ElevenLabs once per scene and writes the MP3 to out_dir.
    Mutates and returns `scenes` with "audio_path" and "duration_seconds" added.
    """
    api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is not set — cannot synthesize narration."
        )
    voice_id = voice_id or DEFAULT_ELEVENLABS_VOICE_ID

    for scene in scenes:
        text = scene.get("narration", "").strip()
        if not text:
            raise RuntimeError(f"Scene {scene.get('scene_id')} has no narration text.")

        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": ELEVENLABS_MODEL_ID,
                "voice_settings": {"stability": 0.45, "similarity_boost": 0.8},
            },
            timeout=60,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"ElevenLabs TTS failed for scene {scene.get('scene_id')}: "
                f"{response.status_code} {response.text[:300]}"
            )

        audio_path = os.path.join(out_dir, f"narration_{scene['scene_id']}.mp3")
        with open(audio_path, "wb") as f:
            f.write(response.content)

        scene["audio_path"] = audio_path
        scene["duration_seconds"] = _probe_audio_duration(audio_path)

    return scenes


# ─────────────────────────────────────────────
# Stage 4 — Render
# ─────────────────────────────────────────────
def _resolve_font() -> str | None:
    for candidate in FONT_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    return None


def _ffmpeg_run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-2000:]}")


def _drawtext_filter(caption_path: str, y_expr: str, fontsize: int) -> str:
    font_clause = ""
    fontfile = _resolve_font()
    if fontfile:
        font_clause = f"fontfile='{fontfile}':"
    return (
        f"drawtext={font_clause}textfile='{caption_path}':fontcolor=white:"
        f"fontsize={fontsize}:box=1:boxcolor=black@0.55:boxborderw=16:"
        f"x=(w-text_w)/2:y={y_expr}"
    )


def _render_scene_clip(
    image_path: str, audio_path: str, duration: float, caption: str, out_path: str, work_dir: str
) -> None:
    caption_path = os.path.join(work_dir, os.path.basename(out_path) + ".caption.txt")
    with open(caption_path, "w") as f:
        f.write(caption)

    frames = max(int(duration * VIDEO_FPS), 1)
    zoom_expr = f"zoompan=z='min(zoom+0.0012,1.15)':d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}"
    caption_filter = _drawtext_filter(caption_path, "h-160", 42)
    filter_complex = (
        f"[0:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},{zoom_expr},{caption_filter}[v]"
    )
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-t", str(duration), "-i", image_path,
        "-i", audio_path,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-r", str(VIDEO_FPS), "-shortest", "-t", str(duration),
        out_path,
    ]
    _ffmpeg_run(cmd)


def _render_title_card(
    title: str, subtitle: str, audio_path: str, duration: float, out_path: str, work_dir: str, bg: str
) -> None:
    title_path = os.path.join(work_dir, os.path.basename(out_path) + ".title.txt")
    sub_path = os.path.join(work_dir, os.path.basename(out_path) + ".sub.txt")
    with open(title_path, "w") as f:
        f.write(title)
    with open(sub_path, "w") as f:
        f.write(subtitle)

    title_filter = _drawtext_filter(title_path, "(h-text_h)/2-40", 88).replace(
        "box=1:boxcolor=black@0.55:boxborderw=16:", ""
    )
    sub_filter = _drawtext_filter(sub_path, "(h/2)+70", 40).replace(
        "box=1:boxcolor=black@0.55:boxborderw=16:", ""
    )
    filter_complex = (
        f"color=c={bg}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={duration}[bg];"
        f"[bg]{title_filter},{sub_filter}[v]"
    )
    cmd = [
        "ffmpeg", "-y", "-i", audio_path,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-r", str(VIDEO_FPS), "-shortest", "-t", str(duration),
        out_path,
    ]
    _ffmpeg_run(cmd)


def _render_video(
    scenes: list[dict[str, Any]],
    screenshot_map: dict[str, str],
    out_path: str,
    company_name: str,
    url: str,
    work_dir: str,
) -> float:
    """
    Renders every scene to its own clip, then concatenates them into out_path.
    Returns the total duration in seconds.
    """
    clip_paths = []
    total_duration = 0.0

    for scene in scenes:
        duration = scene.get("duration_seconds")
        audio_path = scene.get("audio_path")
        if not duration or not audio_path:
            raise RuntimeError(
                f"Scene {scene.get('scene_id')} is missing narration audio/duration."
            )

        clip_path = os.path.join(work_dir, f"clip_{scene['scene_id']}.mp4")
        role = scene.get("role")
        visual = scene.get("visual")

        if role == "intro":
            _render_title_card(
                company_name, scene.get("caption", ""), audio_path, duration,
                clip_path, work_dir, TITLE_CARD_BG,
            )
        elif role == "outro":
            _render_title_card(
                scene.get("caption", "Learn more"), url, audio_path, duration,
                clip_path, work_dir, OUTRO_CARD_BG,
            )
        else:
            image_path = screenshot_map.get(visual) or next(iter(screenshot_map.values()), None)
            if not image_path:
                raise RuntimeError("No screenshots available to render feature scenes.")
            _render_scene_clip(
                image_path, audio_path, duration, scene.get("caption", ""), clip_path, work_dir
            )

        clip_paths.append(clip_path)
        total_duration += duration

    concat_list_path = os.path.join(work_dir, "concat_list.txt")
    with open(concat_list_path, "w") as f:
        for clip_path in clip_paths:
            f.write(f"file '{clip_path}'\n")

    _ffmpeg_run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_list_path, "-c", "copy", out_path,
    ])

    return total_duration


# ─────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────
def run(
    url: str,
    company_name: str,
    company_info: str = "",
    run_id: str | None = None,
    target_duration_seconds: int = DEFAULT_DURATION_SECONDS,
    voice_id: str | None = None,
    max_scenes: int = MAX_SCENES,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """
    Execute the full capture -> script -> voice -> render pipeline and
    return a handoff envelope. On a partial failure, whatever artifacts
    were already produced (script, narration audio) are kept in the
    payload rather than discarded.
    """
    if not url:
        raise ValueError("demo_video_producer.run() requires a url")
    if not company_name:
        raise ValueError("demo_video_producer.run() requires a company_name")

    run_id = run_id or new_run_id()
    target_duration_seconds = max(
        MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, target_duration_seconds)
    )
    work_dir = output_dir or tempfile.mkdtemp(prefix=f"demo_video_{run_id}_")
    os.makedirs(work_dir, exist_ok=True)

    # ---- Stage 1: Capture ----
    try:
        capture = _capture_site(url, work_dir, max_scenes=max_scenes)
    except Exception as e:
        return make_envelope(
            agent_id=AGENT_ID, run_id=run_id, cadence="daily", status="blocked",
            payload={"stage_failed": "capture", "url": url},
            notes=f"Could not capture {url}: {e}",
        )

    screenshot_labels = [s["label"] for s in capture["screenshots"]]
    if not screenshot_labels:
        return make_envelope(
            agent_id=AGENT_ID, run_id=run_id, cadence="daily", status="blocked",
            payload={"stage_failed": "capture", "url": url},
            notes=f"No screenshots could be captured from {url}.",
        )

    # ---- Stage 2: Script ----
    try:
        script = _generate_script(
            company_name=company_name,
            company_info=company_info,
            url=url,
            site_title=capture["site_title"],
            page_text=capture["page_text"],
            screenshot_labels=screenshot_labels,
            target_duration_seconds=target_duration_seconds,
        )
    except json.JSONDecodeError as e:
        return make_envelope(
            agent_id=AGENT_ID, run_id=run_id, cadence="daily", status="needs_review",
            payload={"stage_failed": "script", "url": url},
            notes=f"Script generation returned unparseable JSON: {e}",
        )

    scenes = script.get("scenes", [])
    if not scenes:
        return make_envelope(
            agent_id=AGENT_ID, run_id=run_id, cadence="daily", status="needs_review",
            payload={"stage_failed": "script", "url": url, "script": script},
            notes="Script generation returned zero scenes.",
        )

    # ---- Stage 3: Voice ----
    try:
        scenes = _synthesize_narration(scenes, work_dir, voice_id=voice_id)
    except Exception as e:
        return make_envelope(
            agent_id=AGENT_ID, run_id=run_id, cadence="daily", status="needs_review",
            payload={"stage_failed": "voice", "url": url, "script": script},
            notes=f"Narration synthesis failed: {e}",
        )

    # ---- Stage 4: Render ----
    screenshot_map = {s["label"]: s["path"] for s in capture["screenshots"]}
    video_path = os.path.join(work_dir, "demo_video.mp4")
    try:
        duration = _render_video(
            scenes, screenshot_map, video_path, company_name, url, work_dir
        )
    except Exception as e:
        return make_envelope(
            agent_id=AGENT_ID, run_id=run_id, cadence="daily", status="needs_review",
            payload={
                "stage_failed": "render", "url": url, "script": script,
                "narration_audio": [
                    {"scene_id": s["scene_id"], "audio_path": s.get("audio_path")}
                    for s in scenes
                ],
            },
            notes=f"Video rendering failed after narration was generated: {e}",
        )

    payload = {
        "video_path": video_path,
        "duration_seconds": round(duration, 1),
        "scene_count": len(scenes),
        "screenshots_captured": len(capture["screenshots"]),
        "source_url": url,
        "script": script,
    }
    notes = (
        f"Rendered a {round(duration, 1)}s demo video for {company_name} "
        f"from {len(capture['screenshots'])} screenshots and {len(scenes)} scenes."
    )
    return make_envelope(
        agent_id=AGENT_ID, run_id=run_id, cadence="daily", status="ok",
        payload=payload, notes=notes,
    )


if __name__ == "__main__":
    # Manual smoke test — requires ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, and
    # a Chromium + ffmpeg available on this machine. See DEMO_VIDEO_PRODUCER.md.
    result = run(
        url="https://example.com",
        company_name="Example Co",
        company_info="A placeholder company used for smoke-testing this agent.",
        target_duration_seconds=45,
    )
    print(json.dumps({k: v for k, v in result.items() if k != "payload"}, indent=2))
    print("payload keys:", list(result.get("payload", {}).keys()))
