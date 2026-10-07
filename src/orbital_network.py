"""
Realistic LEO satellite network model: real SGP4 propagation (via Skyfield)
+ genuine Earth-occlusion geometry for inter-satellite link (ISL) visibility
+ real ground-station elevation-angle visibility for space-to-ground links.

This replaces the simplified circular-orbit / probabilistic-range model used
in the mid-review phase, per the Phase-3 roadmap committed to in the interim
report.
"""
import math
import numpy as np
from datetime import datetime, timedelta, timezone
from skyfield.api import load, EarthSatellite, wgs84

from tle_generator import walker_constellation

R_EARTH_KM = 6378.137
ISL_MAX_RANGE_KM = 6000.0      # next-gen optical ISL terminal range
MIN_ELEVATION_DEG = 15.0       # minimum elevation for a usable ground link
EARTH_BUFFER_KM = 50.0         # atmosphere/margin added to Earth's radius for LOS test


# Real ground-station locations (lat, lon, name)
GROUND_STATIONS = [
    (36.8065, 10.1815, "GCS-Tunis"),
    (48.8566, 2.3522, "GCS-Paris"),
    (1.3521, 103.8198, "GCS-Singapore"),
]


class RealisticSatelliteNetwork:
    def __init__(self, n_planes=3, sats_per_plane=4, altitude_km=550,
                 inclination_deg=53.0, horizon_steps=60, step_seconds=30,
                 base_failure_p=0.05, epoch_dt=None):
        self.ts = load.timescale()
        self.horizon = horizon_steps
        self.step_seconds = step_seconds
        self.base_failure_p = base_failure_p

        if epoch_dt is None:
            epoch_dt = datetime.now(timezone.utc)
        self.epoch_dt = epoch_dt

        tle_set = walker_constellation(n_planes, sats_per_plane, altitude_km, inclination_deg, epoch_dt)
        self.sat_names = [t[0] for t in tle_set]
        self.sats = {name: EarthSatellite(l1, l2, name, self.ts) for name, l1, l2 in tle_set}
        for name, sat in self.sats.items():
            assert sat.model.error == 0, f"SGP4 init error for {name}: {sat.model.error}"

        self.ground_names = [g[2] for g in GROUND_STATIONS]
        self.ground_topos = {g[2]: wgs84.latlon(g[0], g[1]) for g in GROUND_STATIONS}

        self.nodes = self.sat_names + self.ground_names

        self._time_cache = {}      # t_index -> skyfield Time
        self._pos_cache = {}       # (t_index, sat_name) -> geocentric position (km, ECI-like)

    # ---------------- time & geometry helpers ----------------

    def time_at(self, t_index):
        if t_index not in self._time_cache:
            dt = self.epoch_dt + timedelta(seconds=t_index * self.step_seconds)
            self._time_cache[t_index] = self.ts.from_datetime(dt)
        return self._time_cache[t_index]

    def sat_position_km(self, sat_name, t_index):
        key = (t_index, sat_name)
        if key not in self._pos_cache:
            t = self.time_at(t_index)
            pos = self.sats[sat_name].at(t).position.km
            self._pos_cache[key] = np.array(pos)
        return self._pos_cache[key]

    def ground_position_km(self, gnd_name, t_index):
        t = self.time_at(t_index)
        pos = self.ground_topos[gnd_name].at(t).position.km
        return np.array(pos)

    @staticmethod
    def _segment_blocked_by_earth(p1, p2, earth_radius=R_EARTH_KM + EARTH_BUFFER_KM):
        """
        True if the straight line segment between two ECI points p1, p2
        passes through the Earth (genuine geometric occultation test).
        """
        d = p2 - p1
        seg_len2 = np.dot(d, d)
        if seg_len2 == 0:
            return False
        # closest approach of the infinite line to Earth's center (origin)
        t_closest = -np.dot(p1, d) / seg_len2
        t_closest = max(0.0, min(1.0, t_closest))
        closest_point = p1 + t_closest * d
        dist_to_center = np.linalg.norm(closest_point)
        return bool(dist_to_center < earth_radius)

    def isl_visible(self, sat_a, sat_b, t_index):
        pa = self.sat_position_km(sat_a, t_index)
        pb = self.sat_position_km(sat_b, t_index)
        if self._segment_blocked_by_earth(pa, pb):
            return False
        return np.linalg.norm(pa - pb) <= ISL_MAX_RANGE_KM

    def ground_link_visible(self, sat_name, gnd_name, t_index):
        t = self.time_at(t_index)
        topo = self.ground_topos[gnd_name]
        difference = self.sats[sat_name] - topo
        alt, az, dist = difference.at(t).altaz()
        return alt.degrees >= MIN_ELEVATION_DEG

    # ---------------- contact graphs ----------------

    def predicted_contact_graph(self, t_index):
        """Contact graph from pure orbital geometry (what CGR plans against)."""
        import networkx as nx
        G = nx.Graph()
        G.add_nodes_from(self.nodes)
        for i, a in enumerate(self.sat_names):
            for b in self.sat_names[i + 1:]:
                if self.isl_visible(a, b, t_index):
                    G.add_edge(a, b, kind="ISL")
        for s in self.sat_names:
            for g in self.ground_names:
                if self.ground_link_visible(s, g, t_index):
                    G.add_edge(s, g, kind="downlink")
        return G

    def actual_contact_graph(self, t_index, extra_failure_p=0.0, rng=None):
        """Predicted graph minus random unmodeled failures (hardware/atmospheric/interference).
        `extra_failure_p` may be a float (constant) or a callable t_index -> float
        (time-varying disruption schedule)."""
        import random
        rng = rng or random
        G = self.predicted_contact_graph(t_index)
        fp = extra_failure_p(t_index) if callable(extra_failure_p) else extra_failure_p
        p_fail = self.base_failure_p + fp
        for (u, v) in list(G.edges()):
            if rng.random() < p_fail:
                G.remove_edge(u, v)
        return G

    def build_time_expanded_schedule(self):
        return [self.predicted_contact_graph(t) for t in range(self.horizon)]
