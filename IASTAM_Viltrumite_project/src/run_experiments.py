"""
Final Phase-3 experiment runner: runs the 4-strategy comparison on the
realistic SGP4-propagated constellation, across a robustness sweep, plus the
disruption-recovery-time metric, and saves all results + plots.

Run: python3 run_experiments.py
"""
import random
import json
import time
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from orbital_network import RealisticSatelliteNetwork
from routing import (run_naive, run_cgr, run_epidemic, run_hybrid,
                      total_contact_opportunities, recovery_time)

OUT_DIR = "../results"


def main():
    t0 = time.time()
    net = RealisticSatelliteNetwork(n_planes=4, sats_per_plane=8,
                                     horizon_steps=120, step_seconds=30,
                                     base_failure_p=0.05)
    sched = net.build_time_expanded_schedule()
    opp = total_contact_opportunities(sched)
    print(f"Network built: {len(net.sat_names)} satellites, "
          f"{len(net.ground_names)} ground stations, "
          f"{opp} total contact opportunities over {net.horizon} steps.")

    # ---------------- Baseline (nominal conditions) ----------------
    random.seed(42); naive0 = run_naive(net, n_messages=60, total_opportunities=opp)
    random.seed(42); cgr0 = run_cgr(net, sched, n_messages=60, total_opportunities=opp)
    random.seed(42); epi0 = run_epidemic(net, n_messages=60, total_opportunities=opp)
    random.seed(42); hyb0 = run_hybrid(net, sched, n_messages=60, total_opportunities=opp)

    print("\n=== Baseline (nominal conditions, 60 messages) ===")
    for r in (naive0, cgr0, epi0, hyb0):
        print(f"  {r['strategy']:<28} delivery={r['delivery_rate']*100:5.1f}%  "
              f"latency={r['avg_latency_s'] or 0:7.1f}s  tx={r['transmissions']:4d}  "
              f"util={r['network_utilization']*100:5.2f}%")

    # ---------------- Robustness sweep ----------------
    failure_levels = [0.0, 0.1, 0.2, 0.3, 0.4]
    sweep = {"Naive": [], "CGR-lite": [], "Epidemic": [], "Hybrid-Adaptive": []}
    print("\n=== Robustness sweep ===")
    for fp in failure_levels:
        random.seed(99); n = run_naive(net, n_messages=40, extra_failure_p=fp, total_opportunities=opp)
        random.seed(99); c = run_cgr(net, sched, n_messages=40, extra_failure_p=fp, total_opportunities=opp)
        random.seed(99); e = run_epidemic(net, n_messages=40, extra_failure_p=fp, total_opportunities=opp)
        random.seed(99); h = run_hybrid(net, sched, n_messages=40, extra_failure_p=fp, total_opportunities=opp)
        sweep["Naive"].append(n); sweep["CGR-lite"].append(c)
        sweep["Epidemic"].append(e); sweep["Hybrid-Adaptive"].append(h)
        print(f"  fp={fp*100:4.0f}%  Naive={n['delivery_rate']*100:5.1f}%  "
              f"CGR={c['delivery_rate']*100:5.1f}%  Epi={e['delivery_rate']*100:5.1f}%  "
              f"Hybrid={h['delivery_rate']*100:5.1f}% (split={h['mode_split']})")

    # ---------------- Recovery time after major disruption ----------------
    print("\n=== Recovery time after major disruption (window t=20..30, severity +70%) ===")
    recovery = {}
    for strat in ("naive", "cgr", "epidemic", "hybrid"):
        random.seed(7)
        rt = recovery_time(net, sched, disruption_window=(20, 30), strategy=strat, disruption_severity=0.7, n_messages=20)
        recovery[strat] = rt
        print(f"  {strat:<10} avg post-disruption delivery delay = {rt:.1f}s" if rt is not None
              else f"  {strat:<10} no messages recovered within horizon")

    # ---------------- Save ----------------
    import os
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(f"{OUT_DIR}/realistic_results.json", "w") as f:
        json.dump({
            "network": {"n_satellites": len(net.sat_names), "n_ground": len(net.ground_names),
                        "contact_opportunities": opp, "horizon_steps": net.horizon,
                        "step_seconds": net.step_seconds},
            "baseline": {r["strategy"]: r for r in (naive0, cgr0, epi0, hyb0)},
            "robustness_sweep": {"failure_levels": failure_levels, **sweep},
            "recovery_time_seconds": recovery,
        }, f, indent=2, default=str)

    # ---------------- Plot ----------------
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6))
    styles = {"Naive": ("x", "#888888"), "CGR-lite": ("o", "#4C72B0"),
              "Epidemic": ("s", "#DD8452"), "Hybrid-Adaptive": ("^", "#2E8B57")}
    for key, (marker, color) in styles.items():
        vals = [r["delivery_rate"] * 100 for r in sweep[key]]
        lw = 2.6 if key == "Hybrid-Adaptive" else 1.4
        axes[0].plot([f * 100 for f in failure_levels], vals, marker=marker, label=key, color=color, linewidth=lw)
    axes[0].set_xlabel("Additional unpredicted failure rate (%)")
    axes[0].set_ylabel("Delivery rate (%)")
    axes[0].set_title("Realistic SGP4 constellation: delivery vs. disruption")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)

    for key, (marker, color) in styles.items():
        vals = [r["transmissions"] for r in sweep[key]]
        lw = 2.6 if key == "Hybrid-Adaptive" else 1.4
        axes[1].plot([f * 100 for f in failure_levels], vals, marker=marker, label=key, color=color, linewidth=lw)
    axes[1].set_xlabel("Additional unpredicted failure rate (%)")
    axes[1].set_ylabel("Total transmissions")
    axes[1].set_title("Resource usage vs. disruption")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(f"{OUT_DIR}/realistic_comparison.png", dpi=150)
    print(f"\nSaved results to {OUT_DIR}/realistic_results.json and {OUT_DIR}/realistic_comparison.png")
    print(f"Total experiment time: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
