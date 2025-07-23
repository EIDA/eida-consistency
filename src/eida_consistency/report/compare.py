"""Compare two JSON consistency reports."""
import json
import sys
from pathlib import Path

def compare_reports(report_path_1, report_path_2):
    """Compare two JSON consistency reports and return a diff summary."""
    def load_report(path):
        with open(path) as f:
            return json.load(f)

    report_a = load_report(report_path_1)
    report_b = load_report(report_path_2)

    summary_a = report_a.get("summary", {})
    summary_b = report_b.get("summary", {})

    # Check seed match
    if summary_a.get("seed") != summary_b.get("seed"):
        print("❌ Reports have different seeds. Cannot compare.")
        print(f"Report 1 Seed: {summary_a.get('seed')}, Report 2 Seed: {summary_b.get('seed')}")
        sys.exit(1)

    print("✅ Same seed found. Proceeding with comparison...\n")

    # Extract results
    def build_indexed_map(report):
        return {
            (r["network"], r["station"], r["location"], r["channel"], r["starttime"], r["endtime"]): r
            for r in report["results"]
        }

    results_a = build_indexed_map(report_a)
    results_b = build_indexed_map(report_b)

    improved = []
    regressed = []
    unchanged = []
    missing = []

    for key, rec_a in results_a.items():
        rec_b = results_b.get(key)
        if not rec_b:
            missing.append(key)
            continue

        if rec_a["consistent"] and not rec_b["consistent"]:
            regressed.append(key)
        elif not rec_a["consistent"] and rec_b["consistent"]:
            improved.append(key)
        else:
            unchanged.append(key)

    print(f"🔎 Total comparisons: {len(results_a)}")
    print(f"📈 Improvements: {len(improved)}")
    print(f"📉 Regressions: {len(regressed)}")
    print(f"➖ Unchanged: {len(unchanged)}")
    print(f"❓ Missing in Report 2: {len(missing)}")

    if improved:
        print("\n✅ Improved entries:")
        for k in improved:
            print(" -", ".".join(k[:4]), f"[{k[4]} → {k[5]})")

    if regressed:
        print("\n❌ Regressed entries:")
        for k in regressed:
            print(" -", ".".join(k[:4]), f"[{k[4]} → {k[5]})")

    if missing:
        print("\n⚠️ Missing entries in Report 2:")
        for k in missing:
            print(" -", ".".join(k[:4]), f"[{k[4]} → {k[5]})")
