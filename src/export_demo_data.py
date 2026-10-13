"""
Exports everything the live jury-demo page needs as a single JSON blob:
  - per-timestep lat/lon of every satellite and ground station
  - per-timestep contact graph (ISL + downlink edges), under a fixed
    disruption scenario (severe outage during t=20..30)
  - a recorded routing trace for one example message under both CGR-lite
    and Hybrid-Adaptive, for the SAME disruption scenario, so the demo can
    play them back and visually contrast the two strategies.

No live computation happens in the browser -- everything is precomputed
here from the real SGP4 + Earth-occlusion model and embedded as static data,
since a published page cannot run Python or call back into this environment.
"""
import json
import random
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from skyfield.api import wgs84
from orbital_network import RealisticSatelliteNetwork
from routing import _cgr_next_hop, _estimate_reliability

random.seed(2026)

HORIZON = 90          # 45 minutes at 30s/step - enough to show ~half an orbit
DISRUPTION = (20, 32)  # severe-outage window (steps)
SEVERITY = 0.85


def fp_schedule(t):
    return SEVERITY if DISRUPTION[0] <= t < DISRUPTION[1] else 0.0


def export():
    net = RealisticSatelliteNetwork(n_planes=4, sats_per_plane=8,
                                     horizon_steps=HORIZON, step_seconds=30,
                                     base_failure_p=0.05)

    # ---------------- positions per timestep ----------------
    frames = []
    for t in range(HORIZON):
        sat_points = {}
        for name in net.sat_names:
            sp = wgs84.subpoint(net.sats[name].at(net.time_at(t)))
            sat_points[name] = [round(sp.latitude.degrees, 2), round(sp.longitude.degrees, 2)]
        frames.append(sat_points)

    ground_points = {g: [net.ground_topos[g].latitude.degrees, net.ground_topos[g].longitude.degrees]
                      for g in net.ground_names}

    # ---------------- contact graphs per timestep (under the disruption scenario) ----------------
    edge_frames = []
    rng = random.Random(2026)
    actual_graphs = []
    for t in range(HORIZON):
        G = net.actual_contact_graph(t, fp_schedule, rng)
        actual_graphs.append(G)
        edges = [[u, v, G.edges[u, v].get("kind", "ISL")] for u, v in G.edges()]
        edge_frames.append(edges)

    predicted_schedule = net.build_time_expanded_schedule()

    # ---------------- pick a demo source/destination pair ----------------
    rng2 = random.Random(7)
    source, dest = "SIM-SAT-0-0", "SIM-SAT-2-4"

    # ---------------- Trace 1: pure CGR-lite ----------------
    def trace_cgr():
        trace = []
        current, t, hops = source, DISRUPTION[0], 0
        while current != dest and t < HORIZON and hops < 25:
            next_hop, planned_t = _cgr_next_hop(net, predicted_schedule, current, dest, t)
            if next_hop is None:
                trace.append({"t": t, "node": current, "status": "stalled"})
                break
            G = actual_graphs[planned_t] if planned_t < len(actual_graphs) else None
            if G is not None and G.has_edge(current, next_hop):
                trace.append({"t": planned_t, "from": current, "to": next_hop, "mode": "cgr", "status": "hop"})
                current, t, hops = next_hop, planned_t + 1, hops + 1
            else:
                trace.append({"t": planned_t, "node": current, "status": "blocked", "attempted": next_hop})
                t = planned_t + 1
        trace.append({"t": t, "node": current, "status": "delivered" if current == dest else "failed"})
        return trace

    # ---------------- Trace 2: Hybrid-Adaptive ----------------
    def trace_hybrid():
        trace = []
        current, t, hops = source, DISRUPTION[0], 0
        while current != dest and t < HORIZON and hops < 25:
            reliability = _estimate_reliability(net, t, 4, fp_schedule, rng2)
            mode = "cgr" if reliability >= 0.5 else "epidemic"
            if mode == "cgr":
                next_hop, planned_t = _cgr_next_hop(net, predicted_schedule, current, dest, t)
                if next_hop is None:
                    trace.append({"t": t, "node": current, "status": "stalled", "reliability": round(reliability, 2)})
                    break
                G = actual_graphs[planned_t] if planned_t < len(actual_graphs) else None
                if G is not None and G.has_edge(current, next_hop):
                    trace.append({"t": planned_t, "from": current, "to": next_hop, "mode": "cgr",
                                  "status": "hop", "reliability": round(reliability, 2)})
                    current, t, hops = next_hop, planned_t + 1, hops + 1
                else:
                    trace.append({"t": planned_t, "node": current, "status": "blocked",
                                  "attempted": next_hop, "reliability": round(reliability, 2)})
                    t = planned_t + 1
            else:
                # epidemic: advance one step, flood to all current neighbors (for visualization,
                # just record the broadcast neighbors; routing resumes CGR once one of them is closer)
                G = actual_graphs[t] if t < len(actual_graphs) else None
                neighbors = list(G.neighbors(current)) if (G is not None and current in G) else []
                trace.append({"t": t, "node": current, "status": "flood", "neighbors": neighbors,
                              "mode": "epidemic", "reliability": round(reliability, 2)})
                if dest in neighbors:
                    trace.append({"t": t + 1, "from": current, "to": dest, "mode": "epidemic", "status": "hop"})
                    current, t = dest, t + 1
                elif neighbors:
                    current, t = rng2.choice(neighbors), t + 1
                else:
                    t += 1
                hops += 1
        trace.append({"t": t, "node": current, "status": "delivered" if current == dest else "failed"})
        return trace

    cgr_trace = trace_cgr()
    hybrid_trace = trace_hybrid()

    data = {
        "horizon": HORIZON,
        "step_seconds": net.step_seconds,
        "disruption_window": list(DISRUPTION),
        "sat_names": net.sat_names,
        "ground_names": net.ground_names,
        "ground_points": ground_points,
        "frames": frames,            # [t] -> {sat_name: [lat, lon]}
        "edge_frames": edge_frames,  # [t] -> [[u, v, kind], ...]
        "source": source,
        "dest": dest,
        "cgr_trace": cgr_trace,
        "hybrid_trace": hybrid_trace,
        "baseline_metrics": json.load(open("../results/realistic_results.json"))["baseline"],
        "sweep_metrics": json.load(open("../results/realistic_results.json"))["robustness_sweep"],
    }

    with open("../results/demo_data.json", "w") as f:
        json.dump(data, f)
    print(f"Exported demo data: {HORIZON} frames, "
          f"{len(cgr_trace)} CGR trace events, {len(hybrid_trace)} hybrid trace events")
    print("CGR final status:", cgr_trace[-1])
    print("Hybrid final status:", hybrid_trace[-1])


if __name__ == "__main__":
    export()
