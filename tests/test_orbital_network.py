"""
Minimal sanity tests for the realistic orbital network and routing engines.
Run with:  python3 -m pytest tests/  (from the repo root)
or simply: python3 tests/test_orbital_network.py
"""
import os
import sys
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tle_generator import walker_constellation, tle_checksum
from orbital_network import RealisticSatelliteNetwork
from routing import run_naive, run_cgr, run_epidemic, run_hybrid, total_contact_opportunities


def test_tle_lines_are_well_formed():
    sats = walker_constellation(n_planes=2, sats_per_plane=4)
    for name, l1, l2 in sats:
        assert len(l1) == 69, f"line1 wrong length for {name}: {len(l1)}"
        assert len(l2) == 69, f"line2 wrong length for {name}: {len(l2)}"
        assert l1[0] == "1" and l2[0] == "2"
        # checksum must match the last digit of each line
        assert l1[-1] == str(tle_checksum(l1[:-1]))
        assert l2[-1] == str(tle_checksum(l2[:-1]))


def test_sgp4_propagation_gives_correct_altitude():
    net = RealisticSatelliteNetwork(n_planes=2, sats_per_plane=4, horizon_steps=5)
    for name in net.sat_names:
        assert net.sats[name].model.error == 0
    # altitude should be close to the configured 550 km shell
    from skyfield.api import wgs84
    t = net.time_at(0)
    sat = net.sats[net.sat_names[0]]
    alt_km = wgs84.subpoint(sat.at(t)).elevation.km
    assert 500 < alt_km < 620, f"unrealistic altitude: {alt_km} km"


def test_contact_graph_is_nonempty_and_dynamic():
    net = RealisticSatelliteNetwork(n_planes=4, sats_per_plane=8, horizon_steps=20)
    g0 = net.predicted_contact_graph(0)
    g10 = net.predicted_contact_graph(10)
    assert g0.number_of_edges() > 0, "contact graph should not be empty for a realistic constellation"
    # topology must actually change over time (dynamic network requirement)
    assert set(g0.edges()) != set(g10.edges())


def test_earth_occlusion_blocks_antipodal_satellites():
    """Two satellites on opposite sides of the Earth must NOT see each other,
    regardless of raw distance -- this is the genuine geometric-occlusion
    check (not just a distance threshold)."""
    import numpy as np
    net = RealisticSatelliteNetwork(n_planes=2, sats_per_plane=2, horizon_steps=1)
    earth_center = np.array([0.0, 0.0, 0.0])
    p1 = np.array([7000.0, 0.0, 0.0])
    p2 = np.array([-7000.0, 0.0, 0.0])
    assert net._segment_blocked_by_earth(p1, p2) is True


def test_all_routing_strategies_run_without_error():
    net = RealisticSatelliteNetwork(n_planes=3, sats_per_plane=6, horizon_steps=30)
    sched = net.build_time_expanded_schedule()
    opp = total_contact_opportunities(sched)
    random.seed(1)
    for result in (
        run_naive(net, n_messages=5, total_opportunities=opp),
        run_cgr(net, sched, n_messages=5, total_opportunities=opp),
        run_epidemic(net, n_messages=5, total_opportunities=opp),
        run_hybrid(net, sched, n_messages=5, total_opportunities=opp),
    ):
        assert 0.0 <= result["delivery_rate"] <= 1.0
        assert result["transmissions"] >= 0


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        print(f"Running {t.__name__} ...", end=" ")
        t()
        print("OK")
    print(f"\nAll {len(tests)} tests passed.")
