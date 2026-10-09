"""CLI entrypoint for running the evaluation harness [S5.4]."""

import argparse
import asyncio
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings
from evaluation.metrics import compute_metrics
from evaluation.runner import run_case, setup_eval_context
from evaluation.validate_dataset import load_all_datasets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("eval.run")


def get_git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode("utf-8").strip()
    except Exception:
        return "unknown"


def is_git_dirty() -> bool:
    try:
        return bool(subprocess.check_output(["git", "status", "--porcelain"]).strip())
    except Exception:
        return False


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="Run the evaluation harness.")
    parser.add_argument("--split", type=str, required=True, choices=["dev", "test"], help="Dataset split to evaluate")
    parser.add_argument("--config", type=str, default="configs/default.yaml", help="Path to config file")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of cases to run")
    parser.add_argument("--cache", type=str, default="off", choices=["record", "replay", "off"], help="Cache mode")
    parser.add_argument("--concurrency", type=int, default=2, help="Number of concurrent cases to run")
    args = parser.parse_args()

    # Load dataset
    datasets_dir = Path(__file__).resolve().parent / "datasets"
    all_cases = load_all_datasets(datasets_dir)
    cases = [c for c in all_cases if c.split == args.split]

    if args.limit:
        cases = cases[:args.limit]

    logger.info(f"Loaded {len(cases)} cases for split '{args.split}'")

    # Setup context
    settings = Settings()
    ctx = await setup_eval_context(settings)

    # Run cases with concurrency limit
    semaphore = asyncio.Semaphore(args.concurrency)
    
    async def _run_with_semaphore(case):
        async with semaphore:
            logger.info(f"Running case {case.id}...")
            return await run_case(ctx, case)

    tasks = [_run_with_semaphore(c) for c in cases]
    results = await asyncio.gather(*tasks)

    # Compute metrics
    report = compute_metrics(results)
    
    # Save reports
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    git_sha = get_git_sha()
    dirty = "_dirty" if is_git_dirty() else ""
    report_name = f"{timestamp}_{git_sha}{dirty}_{args.split}"
    
    reports_dir = Path(__file__).resolve().parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # Save JSON
    json_path = reports_dir / f"{report_name}.json"
    json_data = {
        "metadata": {
            "timestamp": timestamp,
            "git_sha": git_sha,
            "is_dirty": is_git_dirty(),
            "split": args.split,
            "config": args.config,
            "models": {"llm": settings.FAST_MODEL},
        },
        "metrics": report.as_dict(),
        "cases": [
            {
                "id": r.case_id,
                "success": r.success,
                "accuracy": r.accuracy,
                "lenient_accuracy": r.lenient_accuracy,
                "retries": r.retries,
                "latency_total": r.latency_total,
                "tokens": r.tokens,
                "cost": r.cost,
                "error": r.error,
                "reason": r.reason,
            }
            for r in results
        ]
    }
    json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
    
    # Save Markdown
    md_path = reports_dir / f"{report_name}.md"
    md_lines = [
        f"# Evaluation Report: {args.split.upper()}",
        "",
        f"**Date:** {timestamp}  ",
        f"**Commit:** {git_sha}{' (dirty)' if is_git_dirty() else ''}  ",
        f"**Model:** {settings.FAST_MODEL}  ",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Cases | {report.total} |",
        f"| Success Rate | {report.success_rate:.1%} |",
        f"| Execution Accuracy | {report.execution_accuracy:.1%} |",
        f"| Self-Correction Rate | {report.self_correction_rate:.1%} |",
        f"| Avg Retries | {report.avg_retries:.2f} |",
        f"| Latency p50 | {report.latency_p50:.2f}s |",
        f"| Latency p95 | {report.latency_p95:.2f}s |",
        f"| Total Tokens | {report.total_tokens} |",
        f"| Total Cost | ${report.total_cost:.4f} |",
        "",
        "## Case Details",
        "",
        "| ID | Acc | Retries | Latency | Tokens | Reason |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        acc_str = "✅" if r.accuracy else "❌"
        md_lines.append(f"| {r.case_id} | {acc_str} | {r.retries} | {r.latency_total:.1f}s | {r.tokens} | {r.reason} |")
        
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    
    logger.info(f"Saved reports to {json_path} and {md_path}")
    logger.info(f"Execution Accuracy: {report.execution_accuracy:.1%}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
