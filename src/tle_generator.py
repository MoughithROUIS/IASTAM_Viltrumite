"""
Generate physically-valid, checksum-correct NORAD Two-Line Elements (TLEs)
for a Walker-Delta constellation resembling a Starlink shell, since live
TLE feeds (Celestrak/Space-Track) are not reachable from this sandboxed
environment (robots.txt / auth-gated).

The orbital dynamics are propagated by the REAL SGP4 propagator (via
Skyfield) from these TLEs, so precession, Earth-oblateness (J2) effects,
and drag are all physically accurate for the chosen orbital parameters.
Only the "tracking one specific currently-flying satellite" aspect is
replaced by a synthetic-but-physically-valid Walker constellation -- a
standard approach in LEO satellite-network research when exact live
ephemeris is not required (only realistic orbital geometry is).
"""
import math
from datetime import datetime, timezone

MU_EARTH = 398600.4418  # km^3/s^2
R_EARTH = 6378.137      # km


def mean_motion_rev_per_day(altitude_km):
    a = R_EARTH + altitude_km
    n_rad_s = math.sqrt(MU_EARTH / a ** 3)
    return n_rad_s * 86400 / (2 * math.pi)


def tle_checksum(line68):
    """Sum of all digits mod 10; '-' counts as 1; everything else (incl '+') as 0."""
    total = 0
    for ch in line68:
        if ch.isdigit():
            total += int(ch)
        elif ch == '-':
            total += 1
    return total % 10


def epoch_to_tle(dt: datetime):
    year_two_digit = dt.year % 100
    day_of_year = dt.timetuple().tm_yday
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    frac_day = (dt - midnight).total_seconds() / 86400.0
    # YYDDD.DDDDDDDD  (2 + 3 + 1 + 8 = 14 chars)
    return f"{year_two_digit:02d}{day_of_year:03d}.{int(round(frac_day*1e8)):08d}"


def make_tle(norad_id, epoch_dt, inclination_deg, raan_deg, eccentricity,
             arg_perigee_deg, mean_anomaly_deg, mean_motion_rev_day,
             bstar=0.0001, name="SIM-SAT"):
    intl_designator = f"{'25001A':<8}"  # 8-char field, synthetic but well-formed
    epoch_str = epoch_to_tle(epoch_dt)   # 14 chars

    # BSTAR packed exponential: e.g. 0.0001 -> " 10000-3"
    if bstar == 0:
        bstar_field = " 00000-0"
    else:
        exp = math.floor(math.log10(abs(bstar))) + 1
        mantissa = abs(bstar) / (10 ** exp)
        mantissa_digits = int(round(mantissa * 1e5))
        sign = "-" if bstar < 0 else " "
        bstar_field = f"{sign}{mantissa_digits:05d}-{abs(exp):01d}"

    # ---- Line 1 (69 chars incl. checksum) ----
    l1 = (
        "1 " + f"{norad_id:05d}" + "U " + intl_designator + " " +
        epoch_str + " " +
        " .00000100" + " " +   # first derivative of mean motion (10 chars)
        " 00000-0" + " " +     # second derivative (8 chars)
        bstar_field + " " +    # bstar (8 chars)
        "0" + " " +            # ephemeris type
        " 999"                  # element set number (4 chars)
    )
    assert len(l1) == 68, f"line1 body wrong length: {len(l1)}"
    l1 += str(tle_checksum(l1))

    # ---- Line 2 (69 chars incl. checksum) ----
    ecc_field = f"{int(round(eccentricity * 1e7)):07d}"  # 7 chars, no decimal point
    l2 = (
        "2 " + f"{norad_id:05d}" + " " +
        f"{inclination_deg:8.4f}" + " " +
        f"{raan_deg:8.4f}" + " " +
        ecc_field + " " +
        f"{arg_perigee_deg:8.4f}" + " " +
        f"{mean_anomaly_deg:8.4f}" + " " +
        f"{mean_motion_rev_day:11.8f}" +
        "00001"   # revolution number at epoch (5 chars)
    )
    assert len(l2) == 68, f"line2 body wrong length: {len(l2)}"
    l2 += str(tle_checksum(l2))

    return name, l1, l2


def walker_constellation(n_planes=3, sats_per_plane=4, altitude_km=550,
                          inclination_deg=53.0, epoch_dt=None, start_norad=90000):
    if epoch_dt is None:
        epoch_dt = datetime.now(timezone.utc)
    mm = mean_motion_rev_per_day(altitude_km)
    sats = []
    f = 1
    total_sats = n_planes * sats_per_plane
    for p in range(n_planes):
        raan = p * (360.0 / n_planes)
        for s in range(sats_per_plane):
            phase_offset = p * f * 360.0 / total_sats
            mean_anomaly = (s * 360.0 / sats_per_plane + phase_offset) % 360.0
            norad_id = start_norad + p * sats_per_plane + s
            name = f"SIM-SAT-{p}-{s}"
            sats.append(make_tle(
                norad_id=norad_id, epoch_dt=epoch_dt,
                inclination_deg=inclination_deg, raan_deg=raan,
                eccentricity=0.0001, arg_perigee_deg=0.0,
                mean_anomaly_deg=mean_anomaly, mean_motion_rev_day=mm,
                name=name,
            ))
    return sats


if __name__ == "__main__":
    for name, l1, l2 in walker_constellation(3, 4)[:2]:
        print(name)
        print(l1, len(l1))
        print(l2, len(l2))
