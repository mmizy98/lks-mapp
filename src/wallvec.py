"""Clean, straight wall lines from a noisy scanned wall mask.

mask -> skeleton -> polylines between junctions -> Douglas–Peucker ->
near-horizontal / near-vertical segments snapped to exact axes, and
collinear wall runs aligned to one shared coordinate across the floor.
Each segment keeps the real wall thickness (from the distance transform).
"""
import cv2, numpy as np
from skimage.morphology import skeletonize

AX_TOL = np.tan(np.radians(6))  # within ~6° of an axis -> snap
ALIGN = 4                       # px: merge parallel runs this close into one line


def _polylines(mask):
    sk = skeletonize(mask > 0)
    ys, xs = np.nonzero(sk)
    pix = set(zip(xs.tolist(), ys.tolist()))
    def nb(p):
        x, y = p
        return [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx or dy) and (x + dx, y + dy) in pix]
    deg = {p: len(nb(p)) for p in pix}
    nodes = {p for p in pix if deg[p] != 2}
    seen = set(); lines = []
    def walk(a, b):
        path = [a, b]; prev, cur = a, b
        while cur not in nodes:
            nxt = [q for q in nb(cur) if q != prev and (cur, q) not in seen]
            if not nxt:
                break
            seen.add((cur, nxt[0])); seen.add((nxt[0], cur)); prev, cur = cur, nxt[0]; path.append(cur)
        return path
    for a in list(nodes):
        for b in nb(a):
            if (a, b) not in seen:
                seen.add((a, b)); seen.add((b, a)); lines.append(walk(a, b))
    for p in pix:  # junction-free loops
        if p in nodes or any((p, q) in seen for q in nb(p)):
            continue
        nodes.add(p)
        for b in nb(p):
            if (p, b) not in seen:
                seen.add((p, b)); seen.add((b, p)); lines.append(walk(p, b))
    return lines


def _cluster(vals, tol):
    """1-D clustering: returns mapping value-index -> cluster mean."""
    order = np.argsort([v for v, _ in vals]); out = {}; grp = []
    def flush():
        if grp:
            m = sum(vals[i][0] * vals[i][1] for i in grp) / sum(vals[i][1] for i in grp)
            for i in grp:
                out[i] = m
    last = first = None
    for i in order:
        v = vals[i][0]
        if last is not None and (v - last > tol or v - first > 1.6 * tol):
            flush(); grp = []; first = None
        grp.append(i); last = v
        if first is None:
            first = v
    flush()
    return out


def straight_walls(mask, min_len=14):
    mask = (mask > 0).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    dt = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    lines = _polylines(mask)
    cnt = {}
    for ln in lines:
        for p in (tuple(ln[0]), tuple(ln[-1])):
            cnt[p] = cnt.get(p, 0) + 1
    ends = {p for p, c in cnt.items() if c == 1}
    V = {}  # vertex key -> [x, y]
    def vid(p):
        if p not in V:
            V[p] = [float(p[0]), float(p[1])]
        return p
    segs = []  # (a, b, thickness)
    for ln in lines:
        if len(ln) < 2:
            continue
        arr = np.array(ln, np.int32)
        L = np.abs(np.diff(arr, axis=0)).sum()
        thick = 2 * float(np.median(dt[arr[:, 1], arr[:, 0]]))
        if (L < min_len and thick < 4) or (L < 10 and (tuple(ln[0]) in ends or tuple(ln[-1]) in ends)):
            continue  # specks, leftover text strokes
        end_a, end_b = tuple(ln[0]) in ends, tuple(ln[-1]) in ends
        if (end_a or end_b) and not (end_a and end_b) and L < thick * 1.6 + 6:
            continue  # skeleton spurs at thick-wall corners
        s = cv2.approxPolyDP(arr.reshape(-1, 1, 2), 2.6, False).reshape(-1, 2)
        keys = [vid(tuple(map(int, s[0])))] + [vid(tuple(map(int, q))) for q in s[1:-1]] + [vid(tuple(map(int, s[-1])))]
        for a, b in zip(keys, keys[1:]):
            if a != b:
                segs.append((a, b, thick))
    # axis snapping at vertex level (keeps joints connected)
    ycand, xcand = {}, {}
    kinds = []
    for a, b, t in segs:
        (x0, y0), (x1, y1) = V[a], V[b]; dx, dy = abs(x1 - x0), abs(y1 - y0)
        if dx > 0 and dy <= dx * AX_TOL:
            kinds.append('h'); w = dx
            ycand.setdefault(a, []).append(((y0 + y1) / 2, w)); ycand.setdefault(b, []).append(((y0 + y1) / 2, w))
        elif dy > 0 and dx <= dy * AX_TOL:
            kinds.append('v'); w = dy
            xcand.setdefault(a, []).append(((x0 + x1) / 2, w)); xcand.setdefault(b, []).append(((x0 + x1) / 2, w))
        else:
            kinds.append('d')
    for k, c in ycand.items():
        V[k][1] = sum(v * w for v, w in c) / sum(w for _, w in c)
    for k, c in xcand.items():
        V[k][0] = sum(v * w for v, w in c) / sum(w for _, w in c)
    # align collinear runs across the floor (walls broken by doors share one line)
    for axis, cand in ((1, ycand), (0, xcand)):
        keys = list(cand.keys())
        if not keys:
            continue
        vals = [(V[k][axis], sum(w for _, w in cand[k])) for k in keys]
        m = _cluster(vals, ALIGN)
        # only merge vertices that are also close along the other axis? Long walls: allow whole floor.
        for i, k in enumerate(keys):
            V[k][axis] = round(m[i] * 2) / 2
    # thickness classes
    out = {}
    for (a, b, t), kd in zip(segs, kinds):
        (x0, y0), (x1, y1) = V[a], V[b]
        if abs(x1 - x0) + abs(y1 - y0) < 1:
            continue
        w = 3 if t < 4 else 5 if t < 7 else 8 if t < 11 else 12
        out.setdefault(w, []).append(f'M{x0:g} {y0:g}L{x1:g} {y1:g}')
    return [[w, ''.join(p)] for w, p in sorted(out.items())]


def straight_poly_path(mask, eps=3.0, min_area=30):
    """Region mask -> SVG path with axis-snapped, simplified outlines."""
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cs:
        if abs(cv2.contourArea(c)) < min_area:
            continue
        a = cv2.approxPolyDP(c, eps, True).reshape(-1, 2).astype(float)
        n = len(a)
        if n < 3:
            continue
        for _ in range(2):
            for i in range(n):
                p, q = a[i], a[(i + 1) % n]; dx, dy = abs(q[0] - p[0]), abs(q[1] - p[1])
                if dx > 0 and dy <= dx * AX_TOL:
                    y = (p[1] + q[1]) / 2; p[1] = q[1] = y
                elif dy > 0 and dx <= dy * AX_TOL:
                    x = (p[0] + q[0]) / 2; p[0] = q[0] = x
        out.append('M' + 'L'.join(f'{x:g} {y:g}' for x, y in np.round(a * 2) / 2) + 'Z')
    return ''.join(out)
