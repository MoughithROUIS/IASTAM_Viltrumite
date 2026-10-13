"""Multi-seed evaluation: N independent seeds, paired design (same seed for all four strategies
within a condition), FIXED orbital epoch for exact reproducibility. Reports mean and std.
Run: python3 run_multiseed.py [n_seeds]"""
import json, os, random, sys, statistics as st
from datetime import datetime, timezone
from multiprocessing import Pool
from orbital_network import RealisticSatelliteNetwork
from routing import (run_naive, run_cgr, run_epidemic, run_hybrid, total_contact_opportunities, recovery_time)

EPOCH = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
LEVELS = [float(x) for x in os.environ.get('LEVELS', '0,0.1,0.2,0.3,0.4').split(',')]
NAMES = ["Naive", "Epidemic", "CGR-lite", "Hybrid-Adaptive"]

def one_seed(seed):
    net = RealisticSatelliteNetwork(n_planes=4, sats_per_plane=8, horizon_steps=120, step_seconds=30,
                                    base_failure_p=0.05, epoch_dt=EPOCH)
    sched = net.build_time_expanded_schedule(); opp = total_contact_opportunities(sched)
    def run(name, n, fp, s):
        random.seed(s)
        if name == "Naive": return run_naive(net, n, fp, total_opportunities=opp)
        if name == "Epidemic": return run_epidemic(net, n, fp, total_opportunities=opp)
        if name == "CGR-lite": return run_cgr(net, sched, n, fp, total_opportunities=opp)
        return run_hybrid(net, sched, n, fp, total_opportunities=opp)
    out = {"baseline": {}, "sweep": {}, "recovery": {}}
    for nm in NAMES:
        r = run(nm, 60, 0.0, 1000 * seed + 1)
        out["baseline"][nm] = {k: r[k] for k in ("delivery_rate", "avg_latency_s", "transmissions", "network_utilization")}
        out["sweep"][nm] = [run(nm, 40, fp, 1000 * seed + 10 + i)["delivery_rate"] for i, fp in enumerate(LEVELS)]
        random.seed(1000 * seed + 99)
        key = {"Naive": "naive", "Epidemic": "epidemic", "CGR-lite": "cgr", "Hybrid-Adaptive": "hybrid"}[nm]
        out["recovery"][nm] = recovery_time(net, sched, (20, 30), key, 0.7, 20)
    return out

def agg(xs):
    xs = [x for x in xs if x is not None]
    return {"mean": st.mean(xs), "std": st.stdev(xs) if len(xs) > 1 else 0.0, "n": len(xs)} if xs else None

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    with Pool() as pool: res = pool.map(one_seed, range(n))
    R = {"n_seeds": n, "epoch": EPOCH.isoformat(), "levels": LEVELS, "baseline": {}, "sweep": {}, "recovery": {}}
    for nm in NAMES:
        R["baseline"][nm] = {m: agg([r["baseline"][nm][m] for r in res]) for m in ("delivery_rate", "avg_latency_s", "transmissions", "network_utilization")}
        R["sweep"][nm] = [agg([r["sweep"][nm][i] for r in res]) for i in range(len(LEVELS))]
        R["recovery"][nm] = agg([r["recovery"][nm] for r in res])
    json.dump(R, open("../results/" + os.environ.get("OUT", "multiseed_results.json"), "w"), indent=2)
    print("done", n, "seeds")
