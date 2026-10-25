"""Clean schematic for the typical floors (5–11): boxes on a canonical grid.

Geometry is NOT traced from the scan. Room order and widths come from floors.py
(x positions along the building); everything across the building (row heights,
corridor width, core shapes) is a fixed, tidy layout shared by all typical floors.
"""
from floors import F

# canonical cross-section (y grows downward)
UP = (0, 120)        # upper row of rooms
CO = (120, 176)      # corridor
LO = (176, 296)      # lower row of rooms
CORE_TOP = -170      # big stair+lift cores rise above the band
SMALL_TOP = -54      # small stair cores (short, horizontal)
GAP = 4              # gap between neighbouring boxes
X0, X1 = 335, 2420   # band ends (scan x)


def _row_kind(f, y0, y1):
    """Which canonical row a floors.py box belongs to, from its scan y range."""
    d = F[f]
    cy0, cy1 = d['corr'][0][1], d['corr'][0][3]
    if y1 <= cy0 + 4:
        return 'u'
    if y0 >= cy1 - 4:
        return 'd'
    return 'ud'


MINW = 72           # narrowest clickable room box
CORE_W, CORE_GAP = 78, 34   # each lift/stair tower and the lift hall between a pair
SMALL_W = 78


def _fit_row(items, blocked):
    """items: [label, x0, x1, kind] sorted by x along one row. Widen narrow rooms:
    tiny gaps are absorbed, runs of rooms share their width so none is narrower than MINW,
    and if a run is too short it borrows from neighbouring empty space (never from cores)."""
    it = [list(i) for i in items]
    # absorb slivers of empty space between rooms
    i = 0
    while i < len(it):
        l, x0, x1, k = it[i]
        if l is None and (x1 - x0 < 40 or k == 'free') and not blocked(x0, x1):
            L = it[i - 1] if i > 0 and it[i - 1][0] else None
            R = it[i + 1] if i + 1 < len(it) and it[i + 1][0] else None
            if L and R:
                m = (x0 + x1) / 2; L[2] = m; R[1] = m; it.pop(i); continue
            if L or R:
                (L or R)[2 if L else 1] = x1 if L else x0; it.pop(i); continue
        i += 1
    # runs of teaching rooms
    i = 0
    while i < len(it):
        if not (it[i][0] and it[i][3] == 'room'):
            i += 1; continue
        j = i
        while j + 1 < len(it) and it[j + 1][0] and it[j + 1][3] == 'room':
            j += 1
        run = it[i:j + 1]; n = len(run); s, e = run[0][1], run[-1][2]
        need = n * MINW - (e - s)
        if need > 0:  # borrow from empty neighbours (and a little from big non-teaching areas)
            def avail(k2):
                if not (0 <= k2 < len(it)):
                    return 0
                l2, a2, b2, kd2 = it[k2]
                if l2 is None and not blocked(a2, b2):
                    shared = all(0 <= q < len(it) and it[q][0] and it[q][3] == 'room' for q in (k2 - 1, k2 + 1))
                    return max(0, (b2 - a2 - 12) / (2 if shared else 1))
                if kd2 == 'area':
                    return max(0, (b2 - a2) - max(76, 0.55 * (b2 - a2)))
                return 0
            al_, ar_ = avail(i - 1), avail(j + 1)
            tl = min(al_, need * al_ / (al_ + ar_)) if al_ + ar_ else 0
            tr = min(ar_, need - tl)
            tl = min(al_, need - tr)
            if tl > 0:
                it[i - 1][2] -= tl; s -= tl
            if tr > 0:
                it[j + 1][1] += tr; e += tr
        widths = [r[2] - r[1] for r in run]; total = e - s
        fixed = [w < MINW for w in widths]
        for _ in range(4):  # rooms below MINW get MINW, the rest share what is left proportionally
            rest = total - MINW * sum(fixed); big = sum(w for w, fx in zip(widths, fixed) if not fx)
            new = [MINW if fx else w * rest / big for w, fx in zip(widths, fixed)] if big else [total / n] * n
            more = [nw < MINW - 0.5 for nw in new]
            if not any(m and not fx for m, fx in zip(more, fixed)):
                break
            fixed = [fx or m for fx, m in zip(fixed, more)]
        if min(new) < MINW - 0.5:  # still too short: equal split
            new = [total / n] * n
        x = s
        for r, w in zip(run, new):
            r[1], r[2] = x, x + w; x += w
        i = j + 1
    return it


# Ends of the floor where the corridor turns: [(zone_x0, zone_x1)] in scan x.
# Inside a zone the main corridor is blocked by a tall block (rooms / «второй свет»);
# you walk down a connector, along a passage at the bottom of the building, and up into the end wing.
ENDS = {}  # per-floor override; default = between end stair and big core
CONN = 34       # width of vertical connectors
PASS = (232, 290)
ZLOW = (126, 226)  # lower slot inside a zone block


def build(f):
    d = F[f]
    halls = [(l, x) for (l, x, _) in d['st']]
    core_zones = [(hx - CORE_W - CORE_GAP / 2 - 6, hx + CORE_W + CORE_GAP / 2 + 6) for _, hx in halls]
    smalls = []
    for (cx0, cy0, cx1, cy1) in d['deco']:
        mid = (cx0 + cx1) / 2
        if any(abs(hx - mid) < 110 for _, hx in halls):
            continue
        if 1250 < mid < 1500:  # the small central stair is left out on purpose
            continue
        smalls.append(mid)
    small_zones = [(m - SMALL_W / 2 - 6, m + SMALL_W / 2 + 6) for m in smalls]
    if f in ENDS:
        ends = ENDS[f]
    else:  # between the small end stair and the big core on each side
        cz = sorted(core_zones); sz = sorted(small_zones)
        ends = []
        if sz and cz and sz[0][1] < cz[0][0]:
            ends.append((sz[0][1], cz[0][0]))
        if sz and cz and sz[-1][0] > cz[-1][1]:
            ends.append((cz[-1][1], sz[-1][0]))
    left = [z for z in ends if z[0] < 1300]; right = [z for z in ends if z[0] >= 1300]
    # corridors
    cx_a = left[0][1] if left else X0 + 6
    cx_b = right[0][0] if right else X1 - 6
    corr = [(cx_a, CO[0], cx_b, CO[1])]
    outer = []  # lower-row strips taken by the up-connectors into the wings
    for (zl, zr) in left + right:  # U-shaped detour: down a connector, along the bottom, up again
        corr += [(zl, CO[0], zl + CONN, PASS[1]), (zr - CONN, CO[0], zr, PASS[1]), (zl, PASS[0], zr, PASS[1])]
    for (zl, zr) in left:
        corr.append((X0 + 6, CO[0], zl, CO[1]))
    for (zl, zr) in right:
        corr.append((zr, CO[0], X1 - 6, CO[1]))
    zone_of = lambda a, b: next((z for z in ends if (a + b) / 2 > z[0] - 4 and (a + b) / 2 < z[1] + 25), None)
    blocked_u = lambda a, b: any(a < z1 and b > z0 for z0, z1 in core_zones + small_zones + ends)
    blocked_d = lambda a, b: any(a < z1 and b > z0 for z0, z1 in ends)
    rows = {'u': [], 'd': []}; zitems = {z: [] for z in ends}
    for (l, x0, x1, y0, y1, k, al) in d['rooms']:
        rk = _row_kind(f, y0, y1)
        z = zone_of(x0, x1)
        if z:
            zitems[z].append([l, x0, x1, k, al, rk]); continue
        if l is None and x0 < 1500 and x1 > 1250 and rk in ('u', 'ud'):
            k = 'free'  # landing of the removed central stair: give it to the rooms
        rows['u' if rk in ('u', 'ud') else 'd'].append([l, x0, x1, k, al])
    rooms, stubs = [], []
    def add_room(l, k, al, x0, x1, ya, yb, rk):
        box = {'l': l, 'k': k, 'x': round(x0 + GAP / 2, 1), 'y': ya + GAP / 2, 'w': round(x1 - x0 - GAP, 1), 'h': yb - ya - GAP, 'row': rk}
        if al:
            box['al'] = list(al)
        rooms.append(box)
    def add_stubs(holes, ya, yb):
        for a_, b_ in holes:
            w = b_ - a_
            if w < 30:
                continue
            n = max(1, round(w / 130))
            for i in range(n):
                s0 = a_ + w * i / n
                stubs.append({'x': round(s0 + GAP / 2, 1), 'y': ya + GAP / 2, 'w': round(w / n - GAP, 1), 'h': yb - ya - GAP})
    def holes_of(taken, a0, a1, cut):
        taken = sorted(taken); holes, cur = [], a0
        for a_, b_ in taken:
            if a_ > cur:
                holes.append((cur, a_))
            cur = max(cur, b_)
        if cur < a1:
            holes.append((cur, a1))
        for z0, z1 in cut:
            holes = [p for a_, b_ in holes for p in ((a_, min(b_, z0)), (max(a_, z1), b_)) if p[1] - p[0] > 0]
        return holes
    for rk, items in rows.items():
        items += [['#', z0, z1, 'zone', None] for z0, z1 in ends]  # zones split rows into separate runs
        items.sort(key=lambda r: r[1])
        fitted = _fit_row([r[:4] for r in items], blocked_u if rk == 'u' else blocked_d)
        als = {r[0]: r[4] for r in items if r[0]}
        ry = UP if rk == 'u' else LO
        for l, x0, x1, k in fitted:
            if l and k not in ('area', 'zone'):
                for z0, z1 in (outer if rk == 'd' else []):  # keep clear of the up-connectors
                    if x0 < z1 and x1 > z0:
                        x0, x1 = (z1, x1) if (x0 + x1) / 2 > (z0 + z1) / 2 else (x0, z0)
                add_room(l, k, als.get(l), x0, x1, ry[0], ry[1], rk)
        taken = [(r['x'] - GAP / 2, r['x'] + r['w'] + GAP / 2) for r in rooms if r['row'] == rk]
        cut = (core_zones + small_zones + ends) if rk == 'u' else ends
        add_stubs(holes_of(taken, X0 + 6, X1 - 6, cut), ry[0], ry[1])
    # zone blocks: rooms of the zone as tidy columns between the two connectors
    for (zl, zr), items in zitems.items():
        b0, b1 = zl + CONN, zr - CONN
        cols = []  # [label, kind, al, tall, x0, x1, lower]
        for l, x0, x1, k, al, rk in sorted(items, key=lambda r: r[1]):
            if l and k != 'area' and rk in ('u', 'ud'):
                cols.append([l, k, al, rk == 'ud', x0, x1, None])
        for l, x0, x1, k, al, rk in sorted(items, key=lambda r: r[1]):
            if l and k != 'area' and rk == 'd':
                best = max((c for c in cols if not c[3] and c[6] is None), key=lambda c: min(c[5], x1) - max(c[4], x0), default=None)
                if best is not None and min(best[5], x1) - max(best[4], x0) > 0:
                    best[6] = (l, k, al)
                else:
                    cols.append([None, None, None, False, x0, x1, (l, k, al)])
        cols.sort(key=lambda c: c[4])
        for c in cols:  # a room with nothing under it is a big hall (646, 544, 744…): full height
            if c[0] and c[6] is None:
                c[3] = True
        # column widths follow the real widths (big halls stay big), but nothing narrower than ~45
        wts = [1.5 if (c[3] and c[5] - c[4] > 90) else 1.0 for c in cols]; tw = sum(wts) or 1
        x = b0
        for c, wt in zip(cols, wts):
            cw = (b1 - b0) * wt / tw
            if c[0]:
                add_room(c[0], c[1], c[2], x, x + cw, UP[0], ZLOW[1] if c[3] else UP[1], 'z')
            else:
                add_stubs([(x, x + cw)], UP[0], UP[1])
            if not c[3]:
                if c[6]:
                    add_room(c[6][0], c[6][1], c[6][2], x, x + cw, ZLOW[0], ZLOW[1], 'z')
                else:
                    add_stubs([(x, x + cw)], ZLOW[0], ZLOW[1])
            x += cw
    cores = []
    for _, hx in halls:  # two equal towers, symmetric about the lift hall
        for side in (-1, 1):
            x = hx + side * (CORE_GAP / 2) - (CORE_W if side < 0 else 0)
            cores.append({'x': x, 'y': CORE_TOP, 'w': CORE_W, 'h': UP[1] - CORE_TOP, 'main': True})
    for m in smalls:
        # small end stairs: a short horizontal flight above the band, two lifts right under it
        cores.append({'x': m - SMALL_W / 2, 'y': SMALL_TOP, 'w': SMALL_W, 'h': -SMALL_TOP + 4, 'main': False,
                      'lifts': [[m - 33, 12, 30], [m + 3, 12, 30]]})
    return {'rooms': rooms, 'stubs': stubs, 'cores': cores, 'halls': halls, 'corr': corr}


if __name__ == '__main__':
    import json, sys
    print(json.dumps(build(sys.argv[1] if len(sys.argv) > 1 else '6'), ensure_ascii=False)[:600])
