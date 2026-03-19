"""
Daily digest runner.

Runs the two independent daily agents:
  Trend Scout  → (stored to log)
  Performance Watcher → Nufar digest

Run with:
    python run_daily_digest.py

Requires ANTHROPIC_API_KEY in your environment.
"""
import json
import os
import uuid

from agents import trend_scout, performance_watcher

SEPARATOR = "─" * 60


def run_daily(
    today_metrics: dict | None = None,
    seven_day_averages: dict | None = None,
) -> None:
    run_id = str(uuid.uuid4())
    print(f"\nStarting daily digest — run_id: {run_id}\n")

    # Default sample metrics if none provided
    if today_metrics is None:
        today_metrics = {
            "checker_uses": 280,
            "new_members": 12,
            "total_members": 4150,
            "social_reach": 9800,
            "newsletter_open_rate": 0.41,
        }
    if seven_day_averages is None:
        seven_day_averages = {
            "checker_uses": 265,
            "new_members": 14,
            "total_members": 4130,
            "social_reach": 10200,
            "newsletter_open_rate": 0.43,
        }

    # ── Trend Scout ───────────────────────────────────────────────────────
    print("Running Trend Scout...")
    scout_env = trend_scout.run(run_id=run_id, cadence="daily")
    signals = scout_env["payload"].get("signals", [])
    print(f"  {len(signals)} signals found")
    for s in signals:
        print(f"    [{s.get('rank', '?')}] {s.get('title', '')[:70]}")

    # ── Performance Watcher ───────────────────────────────────────────────
    print("\nRunning Performance Watcher...")
    watcher_env = performance_watcher.run(
        today_metrics=today_metrics,
        seven_day_averages=seven_day_averages,
        run_id=run_id,
    )

    digest = watcher_env["payload"].get("digest_summary", "")
    anomalies = watcher_env["payload"].get("anomalies", [])

    print(f"\n{SEPARATOR}")
    print("  NUFAR DAILY DIGEST")
    print(SEPARATOR)
    print(f"\n  {digest}\n")

    if anomalies:
        print("  ANOMALIES FLAGGED:")
        for a in anomalies:
            icon = "↑" if a.get("flag") == "positive" else "⚠"
            print(f"    {icon}  {a['metric']}: {a['delta']} [{a['flag']}]")
    else:
        print("  No anomalies today.")

    print(f"\n{SEPARATOR}")

    # Save output
    output = {
        "run_id": run_id,
        "trend_scout": scout_env,
        "performance_watcher": watcher_env,
    }
    output_path = f"daily_digest_{run_id[:8]}.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Full output saved to: {output_path}")


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.")
        print("Set it with: export ANTHROPIC_API_KEY=your_key_here")
        exit(1)
    run_daily()
