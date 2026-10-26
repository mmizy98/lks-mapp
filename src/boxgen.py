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
SMALL_W = 110


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


BAND = {}   # floors whose band is shorter than the typical one
NO_ENDS = {'4'}               # no U-detours at the ends
SQUEEZE = {'4'}               # upper-row rooms run under the cores on the scan: push them out of the core zones
# extra non-walkable areas drawn around the band (scan x, canonical y), straight lines only
AREAS = {}


SIZES = {'S': 52, 'M': 80, 'L': 118, 'XL': 170}   # the only room widths used on the typical floors
TYPICAL = ['5', '6', '7', '8', '9', '10', '11']


def _cls(w):
    return 'S' if w < 62 else 'M' if w < 100 else 'L' if w < 145 else 'XL'


def _key(f, l, cx):
    if l in ('М', 'Ж'):
        return 'wc' + l + ('L' if cx < 1300 else 'R')
    return l[2:] if f in ('10', '11') else l[1:]


_CANON = None
def _canon():
    """One x position and one size per room suffix (…01, …02 …), shared by floors 4–11,
    so that e.g. 518 sits exactly under 618."""
    global _CANON
    if _CANON is None:
        import statistics as st
        acc = {}
        for f in TYPICAL:
            for rk, its in _rows(f)['rows'].items():
                for l, x0, x1, k, al in its:
                    if l and k not in ('area', 'free', 'svc'):
                        acc.setdefault(_key(f, l, (x0 + x1) / 2), []).append(((x0 + x1) / 2, x1 - x0))
        _CANON = {key: (st.mean(c for c, _ in v), SIZES[_cls(st.median(w for _, w in v))]) for key, v in acc.items()}
    return _CANON


XMAP = {'4': [(371, 341), (780, 854), (1720, 1908), (2075, 2414)]}  # stretch floor 4 so cores line up with 5–11


def _xm(f, x):
    pts = XMAP[f]
    if x <= pts[0][0]:
        return pts[0][1] + (x - pts[0][0])
    for (a, xa), (b, xb) in zip(pts, pts[1:]):
        if x <= b:
            return xa + (x - a) * (xb - xa) / (b - a)
    return pts[-1][1] + (x - pts[-1][0])


def _stretched(f):
    d = dict(F[f]); m = lambda x: round(_xm(f, x))
    d['rooms'] = [(l, m(x0), m(x1), y0, y1, k, al) for (l, x0, x1, y0, y1, k, al) in d['rooms']]
    d['deco'] = [(m(a), b, m(c), e) for (a, b, c, e) in d['deco']]
    d['corr'] = [(m(a), b, m(c), e) for (a, b, c, e) in d['corr']]
    d['st'] = [(l, m(x), y) for (l, x, y) in d['st']]
    return d


def _rows(f):
    d = _stretched(f) if f in XMAP else F[f]
    X0, X1 = BAND.get(f, (globals()['X0'], globals()['X1']))
    halls = [(l, x) for (l, x, _) in d['st']]
    core_zones = [(hx - CORE_W - CORE_GAP / 2 - 6, hx + CORE_W + CORE_GAP / 2 + 6) for _, hx in halls]
    smalls = []
    for (cx0, cy0, cx1, cy1) in d['deco']:
        mid = (cx0 + cx1) / 2
        if any(abs(hx - mid) < 110 for _, hx in halls):
            continue
        if 1150 < mid < 1550:  # the small central stair is left out on purpose
            continue
        smalls.append(mid)
    small_zones = [(m - SMALL_W / 2 - 6, m + SMALL_W / 2 + 6) for m in smalls]
    if f in NO_ENDS:
        ends = []
    elif f in ENDS:
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
    return dict(locals())


def build(f):
    if f in YMAP:
        return build_mapped(f)
    S = _rows(f)
    d, X0, X1, halls, core_zones, smalls, small_zones, ends, corr, rows, zitems = (S[k] for k in ('d', 'X0', 'X1', 'halls', 'core_zones', 'smalls', 'small_zones', 'ends', 'corr', 'rows', 'zitems'))
    rooms, stubs = [], []
    def add_room(l, k, al, x0, x1, ya, yb, rk):
        box = {'l': l, 'k': k, 'x': round(x0 + GAP / 2, 1), 'y': ya + GAP / 2, 'w': round(x1 - x0 - GAP, 1), 'h': yb - ya - GAP, 'row': rk}
        if al:
            box['al'] = list(al)
        rooms.append(box)
    def add_stubs(holes, ya, yb):
        for a_, b_ in holes:  # empty space reads as corridor-coloured floor, not as fake rooms
            if b_ - a_ >= 6:
                stubs.append({'x': round(a_, 1), 'y': ya, 'w': round(b_ - a_, 1), 'h': yb - ya})
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
    canon = _canon()
    for rk, items in rows.items():
        ry = UP if rk == 'u' else LO
        cut = (core_zones + small_zones + ends) if rk == 'u' else ends
        segs = holes_of([], X0 + 6, X1 - 6, sorted(cut))
        placed = {i: [] for i in range(len(segs))}
        for l, x0, x1, k, al in items:
            if not l or k in ('area', 'free', 'svc'):
                continue
            key = _key(f, l, (x0 + x1) / 2)
            cx, w = canon.get(key, ((x0 + x1) / 2, SIZES[_cls(x1 - x0)])) if f in TYPICAL else ((x0 + x1) / 2, SIZES[_cls(x1 - x0)])
            ok = [i for i in range(len(segs)) if segs[i][1] - segs[i][0] >= SIZES['S']] or list(range(len(segs)))
            si = min(ok, key=lambda i: 0 if segs[i][0] <= cx <= segs[i][1] else min(abs(cx - segs[i][0]), abs(cx - segs[i][1])))
            placed[si].append([cx - w / 2, w, l, k, al])
        for si, its in placed.items():
            s0, s1 = segs[si]
            its.sort(key=lambda r: r[0])
            need = sum(r[1] for r in its)
            if need > s1 - s0:  # too tight: shrink everything in this stretch evenly
                sc = (s1 - s0) / need
                for r in its:
                    r[1] *= sc
            cur = s0
            for r in its:  # forward: keep order, no overlaps
                r[0] = max(r[0], cur); cur = r[0] + r[1]
            lim = s1
            for r in reversed(its):  # backward: stay inside the stretch
                r[0] = min(r[0], lim - r[1]); lim = r[0]
            for x, w, l, k, al in its:
                add_room(l, k, al, x, x + w, ry[0], ry[1], rk)
        taken = [(r['x'] - GAP / 2, r['x'] + r['w'] + GAP / 2) for r in rooms if r['row'] == rk]
        add_stubs(holes_of(taken, X0 + 6, X1 - 6, cut), ry[0] + GAP / 2, ry[1] - GAP / 2)
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
    for _, hx in halls:  # one block per lift hall: 8 lifts (2×4) on top, stairs either side below
        w = 2 * CORE_W + CORE_GAP
        cores.append({'x': hx - w / 2, 'y': CORE_TOP, 'w': w, 'h': UP[1] - CORE_TOP, 'main': True})
    for m in smalls:
        # small end stairs: a short horizontal flight above the band, two lifts right under it
        cores.append({'x': m - SMALL_W / 2, 'y': SMALL_TOP, 'w': SMALL_W, 'h': -SMALL_TOP + 4, 'main': False,
                      'lifts': [[m - SMALL_W / 2 + 4, 10, 28], [m + SMALL_W / 2 - 32, 10, 28]]})
        corr.append((m - SMALL_W / 2, UP[0], m + SMALL_W / 2, UP[1]))  # free passage from the corridor to the stair, lifts on its sides
    return {'rooms': rooms, 'stubs': stubs, 'cores': cores, 'halls': halls, 'corr': corr, 'band': (X0, X1),
            'areas': [{'l': l, 'pts': pts, 'c': c} for l, pts, c in AREAS.get(f, [])]}


if __name__ == '__main__':
    import json, sys
    print(json.dumps(build(sys.argv[1] if len(sys.argv) > 1 else '6'), ensure_ascii=False)[:600])


# ---------- floors 2–3: big footprint, mapped straight from floors.py ----------
# x is kept from the scan; y is squeezed piecewise so rows get tidy, equal heights.
YMAP = {'3': [(125, 0), (310, 170), (408, 226), (660, 420), (960, 600)],
        '2': [(130, 0), (305, 160), (410, 220), (660, 420), (960, 600)]}
R_ = lambda l, x0, x1, y0, y1, k='room', al=(): (l, x0, x1, y0, y1, k, tuple(al))
CLEAN_ROOMS = {'3': [  # floor 3 tidied: equal-height upper row, everything inside the outline
    R_('302', 305, 440, 125, 308), R_('310', 545, 705, 125, 308, al=['310а', '308']),
    R_('312', 905, 1065, 125, 308, al=['312а']), R_('316', 1090, 1250, 125, 308, al=['316а']), R_('318', 1290, 1450, 125, 308, al=['318а']),
    R_('320', 1475, 1635, 125, 308, al=['320а']), R_('322', 1830, 1990, 125, 308, al=['322а']),
    R_('324', 2080, 2240, 125, 308, al=['324а', '317']), R_('326', 2265, 2425, 125, 308, al=['328', '317а']), R_('330', 2445, 2505, 125, 308),
    R_('301', 305, 385, 408, 480), R_(None, 385, 560, 408, 480, 'svc'), R_('М', 560, 620, 408, 480, 'wc'), R_('Ж', 620, 680, 408, 480, 'wc'), R_('303', 680, 767, 408, 480),
    R_(None, 1092, 1192, 425, 592, 'svc'), R_('Читальный зал', 1192, 1508, 425, 592, 'place', ['305']),
    R_('311', 1508, 1642, 425, 500), R_('307', 1508, 1575, 500, 592), R_('313', 1575, 1642, 500, 592)]}
CLEAN_ROOMS['2'] = [
    R_('202', 300, 370, 130, 300), R_('204', 370, 440, 130, 300), R_('206', 440, 500, 130, 215), R_('208', 440, 500, 215, 300),
    R_('Конференц-зал', 500, 645, 130, 300, 'place', ['210']), R_('М', 650, 715, 130, 300, 'wc'), R_('Ж', 852, 905, 130, 300, 'wc'),
    R_('212', 905, 1060, 130, 300), R_('216', 1060, 1210, 130, 300), R_('218', 1275, 1440, 130, 300), R_('220', 1440, 1605, 130, 300),
    R_('Ж', 1605, 1665, 130, 300, 'wc'), R_('М', 1802, 1845, 130, 300, 'wc'), R_('222', 1845, 1985, 130, 300), R_('246', 1985, 2045, 130, 300),
    R_('224', 2045, 2235, 130, 300), R_('226', 2235, 2320, 130, 300), R_('228', 2320, 2400, 130, 300), R_('230', 2400, 2490, 130, 215), R_('232', 2400, 2490, 215, 300),
    R_('Буфет', 2050, 2140, 345, 425, 'place'), R_('253', 2140, 2215, 345, 425), R_('255', 2215, 2290, 345, 425), R_('257', 2290, 2365, 345, 425),
    R_('259', 2365, 2440, 345, 425), R_('261', 2440, 2515, 345, 425),
    R_('201', 470, 650, 410, 470), R_('203', 683, 850, 410, 530), R_('Фойе', 683, 850, 530, 658, 'area'),
    R_('243', 867, 962, 410, 583), R_('237', 962, 1058, 410, 583), R_('Книгохранилище', 1058, 1367, 410, 550, 'area'), R_('229', 1058, 1167, 550, 583),
    R_('244', 867, 917, 608, 658), R_('241', 917, 967, 608, 658), R_('235', 967, 1017, 608, 658), R_('233', 1017, 1067, 608, 658), R_('231', 1067, 1117, 608, 658),
    R_('Читальный зал', 1167, 1325, 550, 658, 'place', ['225']), R_('Читальный зал', 1325, 1495, 550, 658, 'place', ['221']), R_('217', 1495, 1583, 550, 658),
    R_('205', 1367, 1421, 410, 460), R_('205а', 1421, 1475, 410, 460), R_('205б', 1475, 1529, 410, 460), R_('205в', 1529, 1583, 410, 460),
    R_('Абонемент', 1367, 1583, 460, 550, 'place'), R_('207', 1605, 1690, 410, 550), R_('209', 1690, 1740, 410, 550),
    R_('247', 1740, 1800, 410, 470), R_('247а', 1800, 1855, 410, 470), R_('249', 1855, 1910, 410, 470), R_('251', 1910, 1962, 410, 470)]
CLEAN_CORR = {'3': [(305, 310, 2505, 408)], '2': [(408, 305, 2050, 410), (2050, 305, 2510, 345)]}
OUTLINES = {
    '3': [(300, 125), (2510, 125), (2510, 417), (2133, 417), (1750, 650), (300, 650)],
    '2': [(260, 130), (2492, 130), (2550, 425), (2025, 425), (1733, 658), (683, 658), (600, 800), (342, 958), (260, 958)],
}
EXTRA_STAIRS = {'2': [(402, 200, 480, 300)]}  # left end stair missing from the scan data
EXTRA_CORR = {  # inner passages to rooms that do not open onto the main corridor (scan coords)
    '3': [(1642, 400, 1678, 592)],
    '2': [(850, 400, 867, 608), (850, 583, 1167, 608), (1583, 400, 1605, 550)],
}
MAP_AREAS = {
    '3': [('Атриум', [(767, 408), (2133, 408), (1750, 650), (767, 650)], (950, 600)),
          ('Зрительный зал', [(300, 480), (767, 480), (767, 650), (300, 650)], (535, 580))],
    '2': [('Зрительный зал', [(258, 467), (683, 467), (683, 658), (600, 800), (342, 958), (270, 958)], (470, 700))],
}


def _ym(f, y):
    pts = YMAP[f]
    for (a, ya), (b, yb) in zip(pts, pts[1:]):
        if y <= b:
            return ya + (min(max(y, a), b) - a) * (yb - ya) / (b - a)
    return pts[-1][1]


def _outline(f):
    if f in OUTLINES:
        return [(x, round(_ym(f, y))) for x, y in OUTLINES[f]]
    import re
    toks = re.findall(r'[MLQZ]|-?\d+(?:\.\d+)?', F[f]['out'][0])
    pts, i, cmd = [], 0, None
    while i < len(toks):
        tk = toks[i]
        if tk in 'MLQZ':
            cmd = tk; i += 1; continue
        if cmd == 'Q':
            cx, cy, x, y = map(float, toks[i:i + 4]); x0, y0 = pts[-1]
            for s in (0.33, 0.66, 1.0):  # curve → three straight pieces
                pts.append(((1 - s) ** 2 * x0 + 2 * (1 - s) * s * cx + s * s * x, (1 - s) ** 2 * y0 + 2 * (1 - s) * s * cy + s * s * y))
            i += 4
        else:
            pts.append((float(toks[i]), float(toks[i + 1]))); i += 2
    return [(round(x), round(_ym(f, y))) for x, y in pts]


def build_mapped(f):
    d = F[f]; ym = lambda y: _ym(f, y)
    halls = [(l, x) for (l, x, _) in d['st']]
    rooms, stubs = [], []
    for (l, x0, x1, y0, y1, k, al) in CLEAN_ROOMS.get(f, d['rooms']):
        b = {'x': x0 + GAP / 2, 'y': round(ym(y0) + GAP / 2, 1), 'w': x1 - x0 - GAP, 'h': round(ym(y1) - ym(y0) - GAP, 1)}
        if not l or k == 'svc':
            stubs.append(b); continue
        if b['h'] < 34:
            b['h'] = 34
        b.update({'l': l, 'k': k, 'row': 'm'})
        if f == '3' and l == 'Читальный зал':
            b['hall'] = 1  # drawn like the atrium, with an entrance from the corridor
        if al:
            b['al'] = list(al)
        rooms.append(b)
    # the four standard sizes here too: snap teaching rooms to S/M/L/XL, keep order, no overlaps
    rs = sorted(rooms, key=lambda b: (round(b['y']), round(b['h']), b['x']))
    clusters, cur = [], []
    for b in rs:
        if cur and round(b['y']) == round(cur[-1]['y']) and round(b['h']) == round(cur[-1]['h']) and b['x'] - (cur[-1]['x'] + cur[-1]['w']) < 20:
            cur.append(b)
        else:
            if cur: clusters.append(cur)
            cur = [b]
    if cur: clusters.append(cur)
    for cl in clusters:
        s0, s1 = cl[0]['x'], cl[-1]['x'] + cl[-1]['w']
        for b in cl:
            if b['k'] == 'room':
                c = b['x'] + b['w'] / 2; b['w'] = SIZES[_cls(b['w'] + GAP)] - GAP; b['x'] = c - b['w'] / 2
        need = sum(b['w'] + GAP for b in cl) - GAP
        if need > s1 - s0:
            sc = (s1 - s0 - GAP * (len(cl) - 1)) / sum(b['w'] for b in cl)
            for b in cl: b['w'] *= sc
        x = s0
        for b in cl:
            b['x'] = max(b['x'], x); x = b['x'] + b['w'] + GAP
        lim = s1
        for b in reversed(cl):
            b['x'] = min(b['x'], lim - b['w']); lim = b['x'] - GAP
        for b in cl:
            b['x'] = round(b['x'], 1); b['w'] = round(b['w'], 1)
    # rows of small neighbours share their width evenly, so none gets too thin to tap
    rs = sorted(rooms, key=lambda b: (round(b['y']), round(b['h']), b['x']))
    runs, cur = [], []
    for b in rs:
        if cur and round(b['y']) == round(cur[-1]['y']) and round(b['h']) == round(cur[-1]['h']) and b['x'] - (cur[-1]['x'] + cur[-1]['w']) < 10:
            cur.append(b)
        else:
            if cur: runs.append(cur)
            cur = [b]
    if cur: runs.append(cur)
    for run in runs:
        if len(run) > 1 and min(b['w'] for b in run) < 44:
            s, e = run[0]['x'], run[-1]['x'] + run[-1]['w']; w = (e - s - GAP * (len(run) - 1)) / len(run)
            for i, b in enumerate(run):
                b['x'] = round(s + i * (w + GAP), 1); b['w'] = round(w, 1)
    for b in rooms:
        if b['w'] < 40:
            b['x'] -= (40 - b['w']) / 2; b['w'] = 40
    corr = [(x0, min(round(ym(y0)), round(ym(y1)) - 26), x1, round(ym(y1))) for (x0, y0, x1, y1) in CLEAN_CORR.get(f, d['corr'])]
    corr += [(x0, round(ym(y0)), x1, round(ym(y1))) for (x0, y0, x1, y1) in EXTRA_CORR.get(f, [])]
    top = ym(min(r[3] for r in d['rooms']))
    cores = []
    for (cx0, cy0, cx1, cy1) in d['deco'] + EXTRA_STAIRS.get(f, []):
        mid = (cx0 + cx1) / 2
        if 1150 < mid < 1550:
            continue  # central stair removed, as on the upper floors
        main = any(abs(hx - mid) < 110 for _, hx in halls)
        if main:
            hx = min((h for _, h in halls), key=lambda h: abs(h - mid))
            same = next((c for c in cores if c['main'] and c.get('hx') == hx), None)
            if same:  # merge the two towers of one lift hall into one block
                x0 = min(same['x'], cx0); x1 = max(same['x'] + same['w'], cx1); same['x'], same['w'] = x0, x1 - x0
            else:
                cores.append({'x': cx0, 'y': CORE_TOP + 50, 'w': cx1 - cx0, 'h': round(ym(cy1)) - CORE_TOP - 50, 'main': True, 'hx': hx})
        else:
            # end stair as on the upper floors: a small block above the band, stair on top, two small lifts under it
            w = SMALL_W; x = mid - w / 2; y = -98
            cores.append({'x': x, 'y': y, 'w': w, 'h': -y + 4, 'main': False, 'sh': 40, 'lifts': [[mid - 31, y + 54, 28], [mid + 3, y + 54, 28]]})
    hy = (corr[0][1] + corr[0][3]) / 2
    return {'rooms': rooms, 'stubs': stubs, 'cores': cores, 'halls': halls, 'corr': corr, 'hall_y': hy,
            'band': (min(x for x, _ in _outline(f)), max(x for x, _ in _outline(f))), 'outline': _outline(f),
            'areas': [{'l': l, 'pts': [(x, round(ym(y))) for x, y in pts], 'c': (c[0], round(ym(c[1])))} for l, pts, c in MAP_AREAS.get(f, [])]}
