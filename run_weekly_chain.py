"""
Full weekly chain integration runner.

Simulates a complete week using synthetic Trend Scout data:
  Trend Scout (x7 days) → Content Strategist → Writer → Health QA
                        → Social Campaign Manager → Campaign Executor
                        → Newsletter Editor

Run with:
    python run_weekly_chain.py

Requires ANTHROPIC_API_KEY in your environment.
"""
import json
import os
import uuid

from agents import (
    trend_scout,
    content_strategist,
    writer,
    health_qa,
    social_campaign_manager,
    campaign_executor,
    newsletter_editor,
)

SEPARATOR = "─" * 60


def print_step(name: str, envelope: dict) -> None:
    status = envelope.get("status", "unknown")
    icon = {"ok": "✓", "blocked": "✗", "needs_review": "⚠"}.get(status, "?")
    print(f"\n{SEPARATOR}")
    print(f"  {icon}  [{name.upper()}]  status={status}")
    if envelope.get("notes"):
        print(f"     notes: {envelope['notes']}")
    print(SEPARATOR)


def run_chain() -> None:
    run_id = str(uuid.uuid4())
    print(f"\nStarting weekly chain — run_id: {run_id}\n")

    # ── Step 1: Simulate 7 days of Trend Scout output ─────────────────────
    print("Step 1/7 — Trend Scout (x7 days)...")
    trend_envelopes = []
    for day in range(7):
        env = trend_scout.run(run_id=run_id, cadence="daily")
        trend_envelopes.append(env)
        print(f"  Day {day + 1}: {len(env['payload'].get('signals', []))} signals found")

    print_step("trend_scout", trend_envelopes[-1])

    # ── Step 2: Content Strategist ────────────────────────────────────────
    print("\nStep 2/7 — Content Strategist...")
    strategist_env = content_strategist.run(
        trend_envelopes=trend_envelopes,
        content_log=["HRT and bone density", "Sleep hygiene tips"],
        run_id=run_id,
    )
    print_step("content_strategist", strategist_env)

    if strategist_env["status"] == "needs_review":
        print("  ⚠  Content Strategist flagged for Nufar review. Continuing anyway for demo.")
    elif strategist_env["status"] == "blocked":
        print("  ✗  Content Strategist blocked. Stopping chain.")
        return

    # ── Step 3: Writer ────────────────────────────────────────────────────
    print("\nStep 3/7 — Writer...")
    writer_env = writer.run(strategist_envelope=strategist_env)
    print_step("writer", writer_env)

    # ── Step 4: Health QA ─────────────────────────────────────────────────
    print("\nStep 4/7 — Health QA...")
    qa_env = health_qa.run(writer_envelope=writer_env)
    print_step("health_qa", qa_env)

    if qa_env["status"] == "blocked":
        issues = qa_env["payload"].get("issues", [])
        print(f"\n  QA BLOCKED — {len(issues)} issue(s):")
        for issue in issues:
            print(f"    [{issue['check']}] {issue['flagged_text'][:80]}")
            print(f"    Fix: {issue['fix_instruction']}")
        print("\n  Content returned to Writer. Chain halted.")
        return

    # ── Step 5: Social Campaign Manager ──────────────────────────────────
    print("\nStep 5/7 — Social Campaign Manager...")
    campaign_env = social_campaign_manager.run(qa_envelope=qa_env)
    print_step("social_campaign_manager", campaign_env)

    # ── Step 6: Campaign Executor ─────────────────────────────────────────
    print("\nStep 6/7 — Campaign Executor (dry run)...")
    executor_env = campaign_executor.run(
        campaign_envelope=campaign_env,
        dry_run=True,
    )
    print_step("campaign_executor", executor_env)

    executed = executor_env["payload"].get("executed", [])
    skipped = executor_env["payload"].get("skipped", [])
    print(f"  Executed: {len(executed)} post(s) | Skipped: {len(skipped)} post(s)")

    # ── Step 7: Newsletter Editor ─────────────────────────────────────────
    print("\nStep 7/7 — Newsletter Editor...")
    newsletter_env = newsletter_editor.run(qa_envelope=qa_env)
    print_step("newsletter_editor", newsletter_env)

    subjects = newsletter_env["payload"].get("subject_options", [])
    if subjects:
        print("  Subject line options:")
        for i, s in enumerate(subjects, 1):
            print(f"    {i}. {s}")

    print(f"\n{SEPARATOR}")
    print("  CHAIN COMPLETE")
    print(f"  run_id: {run_id}")
    print(f"  Newsletter awaiting Nufar approval (status=needs_review)")
    print(SEPARATOR)

    # Save the full chain output
    chain_output = {
        "run_id": run_id,
        "trend_scout": trend_envelopes[-1],
        "content_strategist": strategist_env,
        "writer": writer_env,
        "health_qa": qa_env,
        "social_campaign_manager": campaign_env,
        "campaign_executor": executor_env,
        "newsletter_editor": newsletter_env,
    }

    output_path = f"chain_output_{run_id[:8]}.json"
    with open(output_path, "w") as f:
        json.dump(chain_output, f, indent=2)
    print(f"\n  Full output saved to: {output_path}")


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.")
        print("Set it with: export ANTHROPIC_API_KEY=your_key_here")
        exit(1)
    run_chain()
