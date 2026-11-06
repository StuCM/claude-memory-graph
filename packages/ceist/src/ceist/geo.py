"""Distances between GeoJSON geometries in km, for "near X" and "within N km of X"."""

from math import cos, hypot, pi, radians

KM_PER_DEGREE = 6371.0088 * pi / 180


def geometries(value) -> list[dict]:
    """The geometries in a tile value: a FeatureCollection, a Feature or a bare geometry."""
    if not isinstance(value, dict):
        return []
    kind = value.get("type")
    if kind == "FeatureCollection":
        return [g for f in value.get("features") or [] for g in geometries(f)]
    if kind == "Feature":
        return geometries(value.get("geometry"))
    if kind == "GeometryCollection":
        return [g for x in value.get("geometries") or [] for g in geometries(x)]
    return [value] if value.get("coordinates") else []


def _shape(g: dict) -> tuple[list, list]:
    """(chains of vertices, polygons as lists of rings)."""
    kind, c = g.get("type"), g.get("coordinates")
    if kind == "Point":
        return [[c]], []
    if kind == "MultiPoint":
        return [[p] for p in c], []
    if kind == "LineString":
        return [c], []
    if kind == "MultiLineString":
        return c, []
    if kind == "Polygon":
        return c, [c]
    if kind == "MultiPolygon":
        return [r for p in c for r in p], c
    return [], []


def box(geoms: list[dict], km: float) -> dict:
    """The lng/lat box around `geoms`, widened by `km` on every side."""
    points = [p for g in geoms for chain in _shape(g)[0] for p in chain]
    lngs, lats = [p[0] for p in points], [p[1] for p in points]
    dlat = km / KM_PER_DEGREE
    widest = min(max(abs(min(lats)), abs(max(lats))) + dlat, 89.0)
    dlng = km / (KM_PER_DEGREE * cos(radians(widest)))
    return {"min_lng": min(lngs) - dlng, "min_lat": min(lats) - dlat,
            "max_lng": max(lngs) + dlng, "max_lat": max(lats) + dlat}


def _inside(p, polygon) -> bool:
    inside = False
    for ring in polygon:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > p[1]) != (y2 > p[1]) and p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def _to_segment(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy)
                                                / (dx * dx + dy * dy)))
    return hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _projected(geoms: list[dict], lat0: float) -> tuple[list, list]:
    k = cos(radians(lat0))

    def xy(p):
        return (p[0] * KM_PER_DEGREE * k, p[1] * KM_PER_DEGREE)
    chains, polys = [], []
    for g in geoms:
        c, p = _shape(g)
        chains += [[xy(v) for v in chain] for chain in c]
        polys += [[[xy(v) for v in ring] for ring in poly] for poly in p]
    return chains, polys


def distance_km(a: list[dict], b: list[dict]) -> float:
    """The least distance between two sets of geometries (0 where one lies in the other).

    Projected flat around a's latitude: within 0.5% over tens of km."""
    # ponytail: vertex-to-edge only, so two lines that cross with no vertex near the
    # other read as apart; add a segment-intersection test if long lines matter
    lat0 = _shape(a[0])[0][0][0][1]
    (ca, pa), (cb, pb) = _projected(a, lat0), _projected(b, lat0)
    if any(_inside(v, poly) for chain in ca for v in chain for poly in pb) or \
            any(_inside(v, poly) for chain in cb for v in chain for poly in pa):
        return 0.0
    best = float("inf")
    for chains, others in ((ca, cb), (cb, ca)):
        for chain in chains:
            for v in chain:
                for other in others:
                    pairs = zip(other, other[1:]) if len(other) > 1 else [(other[0], other[0])]
                    best = min(best, min(_to_segment(v, s, e) for s, e in pairs))
    return best


def keep_within(vocab, record: str, km: float, ids) -> set[str]:
    """The ids whose geometry lies within `km` of `record`'s, leaving `record` out."""
    # ponytail: every candidate measured in Python, O(candidates × vertices); a Rós Madair
    # distance predicate (ST_DWithin in the substrate) would make this exact at the source
    anchor = vocab.geometry(record)
    return {i for i in ids if i != record and (g := vocab.geometry(i))
            and distance_km(anchor, g) <= km}
