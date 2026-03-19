"""
Midblooma Agent HTTP Server
Wraps all 8 agents as Flask HTTP endpoints so n8n can call them.

Each endpoint:
  - Accepts JSON body (the input envelope or parameters)
  - Calls the corresponding agent run() function
  - Returns the output envelope as JSON

Start with:
    pip install flask
    python server.py

Or with gunicorn (recommended for production):
    gunicorn server:app --timeout 300 --workers 1 --bind 0.0.0.0:5000
"""
import os
import traceback
from flask import Flask, request, jsonify

from agents import (
    trend_scout,
    performance_watcher,
    content_strategist,
    writer,
    health_qa,
    social_campaign_manager,
    campaign_executor,
    newsletter_editor,
)

app = Flask(__name__)


def _err(message: str, status: int = 400):
    return jsonify({"error": message}), status


# ─────────────────────────────────────────────
# AGENT 1 — Trend Scout
# Body (all optional):
#   { "run_id": "...", "cadence": "daily", "context_hint": "" }
# ─────────────────────────────────────────────
@app.route("/agents/trend-scout", methods=["POST"])
def route_trend_scout():
    body = request.get_json(silent=True) or {}
    try:
        result = trend_scout.run(
            run_id=body.get("run_id"),
            cadence=body.get("cadence", "daily"),
            context_hint=body.get("context_hint", ""),
        )
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return _err(str(e), 500)


# ─────────────────────────────────────────────
# AGENT 2 — Performance Watcher
# Body (required):
#   {
#     "today_metrics": { checker_uses, new_members, total_members,
#                        social_reach, newsletter_open_rate },
#     "seven_day_averages": { same keys },
#     "run_id": "..."   (optional)
#   }
# ─────────────────────────────────────────────
@app.route("/agents/performance-watcher", methods=["POST"])
def route_performance_watcher():
    body = request.get_json(silent=True) or {}
    if "today_metrics" not in body:
        return _err("today_metrics is required")
    if "seven_day_averages" not in body:
        return _err("seven_day_averages is required")
    try:
        result = performance_watcher.run(
            today_metrics=body["today_metrics"],
            seven_day_averages=body["seven_day_averages"],
            run_id=body.get("run_id"),
            cadence=body.get("cadence", "daily"),
        )
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return _err(str(e), 500)


# ─────────────────────────────────────────────
# AGENT 3 — Content Strategist
# Body (required):
#   {
#     "trend_envelopes": [ ...7 Trend Scout envelopes... ],
#     "content_log":     [ "topic A", "topic B", ... ],  (optional)
#     "run_id":          "..."                            (optional)
#   }
# ─────────────────────────────────────────────
@app.route("/agents/content-strategist", methods=["POST"])
def route_content_strategist():
    body = request.get_json(silent=True) or {}
    if not body.get("trend_envelopes"):
        return _err("trend_envelopes is required and must be non-empty")
    try:
        result = content_strategist.run(
            trend_envelopes=body["trend_envelopes"],
            content_log=body.get("content_log", []),
            run_id=body.get("run_id"),
        )
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return _err(str(e), 500)


# ─────────────────────────────────────────────
# AGENT 4 — Writer
# Body (required):
#   { "strategist_envelope": { ...full envelope from Content Strategist... } }
# ─────────────────────────────────────────────
@app.route("/agents/writer", methods=["POST"])
def route_writer():
    body = request.get_json(silent=True) or {}
    # Accept envelope directly OR wrapped in {"strategist_envelope": ...}
    envelope = body.get("strategist_envelope") or (body if body.get("agent_id") else None)
    if not envelope:
        return _err("strategist_envelope is required")
    try:
        result = writer.run(
            strategist_envelope=envelope,
            qa_feedback=body.get("qa_feedback"),
        )
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return _err(str(e), 500)


# ─────────────────────────────────────────────
# AGENT 5 — Health QA
# Body (required):
#   { "writer_envelope": { ...full envelope from Writer... } }
# ─────────────────────────────────────────────
@app.route("/agents/health-qa", methods=["POST"])
def route_health_qa():
    body = request.get_json(silent=True) or {}
    envelope = body.get("writer_envelope") or (body if body.get("agent_id") else None)
    if not envelope:
        return _err("writer_envelope is required")
    try:
        result = health_qa.run(writer_envelope=envelope)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return _err(str(e), 500)


# ─────────────────────────────────────────────
# AGENT 6 — Social Campaign Manager
# Body (required):
#   {
#     "qa_envelope": { ...full envelope from Health QA... },
#     "week_of":     "2026-03-17"   (optional — defaults to next Monday)
#   }
# ─────────────────────────────────────────────
@app.route("/agents/social-campaign-manager", methods=["POST"])
def route_social_campaign_manager():
    body = request.get_json(silent=True) or {}
    envelope = body.get("qa_envelope") or (body if body.get("agent_id") else None)
    if not envelope:
        return _err("qa_envelope is required")
    try:
        result = social_campaign_manager.run(
            qa_envelope=envelope,
            week_of=body.get("week_of"),
        )
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return _err(str(e), 500)


# ─────────────────────────────────────────────
# AGENT 7 — Campaign Executor
# Body (required):
#   {
#     "campaign_envelope": { ...full envelope from Campaign Manager... },
#     "dry_run":           false   (optional)
#   }
# ─────────────────────────────────────────────
@app.route("/agents/campaign-executor", methods=["POST"])
def route_campaign_executor():
    body = request.get_json(silent=True) or {}
    envelope = body.get("campaign_envelope") or (body if body.get("agent_id") else None)
    if not envelope:
        return _err("campaign_envelope is required")
    try:
        result = campaign_executor.run(
            campaign_envelope=envelope,
            dry_run=body.get("dry_run", False),
        )
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return _err(str(e), 500)


# ─────────────────────────────────────────────
# AGENT 8 — Newsletter Editor
# Body (required):
#   {
#     "qa_envelope":      { ...full envelope from Health QA... },
#     "watcher_envelope": { ... }   (optional),
#     "top_signal":       { ... }   (optional),
#     "marketplace_data": [ ... ]   (optional),
#     "events_data":      [ ... ]   (optional)
#   }
# ─────────────────────────────────────────────
@app.route("/agents/newsletter-editor", methods=["POST"])
def route_newsletter_editor():
    body = request.get_json(silent=True) or {}
    envelope = body.get("qa_envelope") or (body if body.get("agent_id") else None)
    if not envelope:
        return _err("qa_envelope is required")
    try:
        result = newsletter_editor.run(
            qa_envelope=envelope,
            watcher_envelope=body.get("watcher_envelope"),
            top_signal=body.get("top_signal"),
            marketplace_data=body.get("marketplace_data"),
            events_data=body.get("events_data"),
        )
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return _err(str(e), 500)


# ─────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "agents": [
        "trend-scout", "performance-watcher", "content-strategist",
        "writer", "health-qa", "social-campaign-manager",
        "campaign-executor", "newsletter-editor",
    ]})


# ─────────────────────────────────────────────
# Network diagnostics
# ─────────────────────────────────────────────
@app.route("/diag", methods=["GET"])
def diagnostics():
    import socket
    import ssl
    import sys
    results = {}
    # Python version
    results["python_version"] = sys.version
    # Check API key
    results["api_key_set"] = bool(os.environ.get("ANTHROPIC_API_KEY"))
    results["api_key_prefix"] = os.environ.get("ANTHROPIC_API_KEY", "")[:20]
    # Proxy env vars
    results["http_proxy"] = os.environ.get("HTTP_PROXY", "")
    results["https_proxy"] = os.environ.get("HTTPS_PROXY", "")
    results["all_proxy"] = os.environ.get("ALL_PROXY", "")
    # DNS lookup
    try:
        ip = socket.gethostbyname("api.anthropic.com")
        results["dns_ok"] = True
        results["anthropic_ip"] = ip
    except Exception as e:
        results["dns_ok"] = False
        results["dns_error"] = str(e)
    # TCP connect
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection(("api.anthropic.com", 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname="api.anthropic.com") as ssock:
                results["tcp_ok"] = True
                results["tls_version"] = ssock.version()
    except Exception as e:
        results["tcp_ok"] = False
        results["tcp_error"] = str(e)
    # httpx direct GET to Anthropic
    try:
        import httpx
        r = httpx.get("https://api.anthropic.com", timeout=10)
        results["httpx_ok"] = True
        results["httpx_status"] = r.status_code
    except Exception as e:
        results["httpx_ok"] = False
        results["httpx_error"] = str(e)
    # httpx POST test (mimics what the SDK does)
    try:
        import httpx
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        r2 = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "Say OK"}],
            },
            timeout=15,
        )
        results["httpx_post_ok"] = True
        results["httpx_post_status"] = r2.status_code
        results["httpx_post_body"] = r2.text[:200]
    except Exception as e:
        results["httpx_post_ok"] = False
        results["httpx_post_error"] = str(e)
    # Minimal Anthropic SDK call — forced HTTP/1.1, no HTTP/2
    try:
        import anthropic as ant
        import httpx
        client = ant.Anthropic(http_client=httpx.Client(http2=False))
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=10,
            messages=[{"role": "user", "content": "Say OK"}],
        )
        results["sdk_ok"] = True
        results["sdk_response"] = msg.content[0].text if msg.content else ""
    except Exception as e:
        results["sdk_ok"] = False
        results["sdk_error"] = str(e)
    return jsonify(results)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Midblooma Agent Server starting on port {port}...")
    print(f"Health check: http://localhost:{port}/health")
    app.run(host="0.0.0.0", port=port, debug=False)
