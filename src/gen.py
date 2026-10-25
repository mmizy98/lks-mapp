"""Builds vector map data and the routing graph from the scans + floors.py.

Geometry comes from the scans themselves (src/scans/f*.jpg):
  * walls   – dark strokes of the plan, minus text, dots and the grid, vectorised;
  * rooms   – the real enclosed region around each room label (flood fill between walls);
  * halls   – free space inside the corridor zones from floors.py;
  * routes  – along the skeleton (centre line) of the halls.
floors.py only says *what* is where (room numbers, kinds, rough boxes); the shapes are traced.
Outputs vec.json and seed.json next to this file.
"""
import json, os, cv2, numpy as np
from skimage.morphology import skeletonize
from floors import F
from boxgen import build as build_box, CO as BCO, UP as BUP, LO as BLO, X0 as BX0, X1 as BX1, CORE_TOP as BCORE_TOP
BOXF = {'5', '6', '7', '8', '9', '10', '11'}
from wallvec import straight_walls, straight_poly_path, clean_walls, room_shape, snap_poly

HERE = os.path.dirname(os.path.abspath(__file__))
ORDER = ['1a', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11']
THR, MINLEN, MINAREA = 130, 45, 60


def path_from_mask(mask, eps=1.2, min_area=30):
    """Mask -> SVG path (evenodd), holes included."""
    cs, hier = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cs:
        if abs(cv2.contourArea(c)) < min_area:
            continue
        a = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
        if len(a) < 3:
            continue
        out.append('M' + 'L'.join(f'{x} {y}' for x, y in a) + 'Z')
    return ''.join(out)


def poly_mask(shape, d):
    """Rasterise floors.py outline paths (M/L/Q/H/V/Z subset) to a mask."""
    m = np.zeros(shape, np.uint8)
    import re
    for p in d['out']:
        toks = re.findall(r'[MLQHVZ]|-?\d+(?:\.\d+)?', p)
        pts, i, cmd, cur = [], 0, None, (0, 0)
        polys = []
        while i < len(toks):
            t = toks[i]
            if t in 'MLQHVZ':
                cmd = t; i += 1
                if t == 'Z':
                    polys.append(pts); pts = []
                continue
            if cmd in 'ML':
                cur = (float(toks[i]), float(toks[i + 1])); pts.append(cur); i += 2
            elif cmd == 'H':
                cur = (float(t), cur[1]); pts.append(cur); i += 1
            elif cmd == 'V':
                cur = (cur[0], float(t)); pts.append(cur); i += 1
            elif cmd == 'Q':
                cx, cy, x, y = map(float, toks[i:i + 4]); x0, y0 = cur
                for s in np.linspace(0, 1, 16)[1:]:
                    pts.append(((1 - s) ** 2 * x0 + 2 * (1 - s) * s * cx + s * s * x, (1 - s) ** 2 * y0 + 2 * (1 - s) * s * cy + s * s * y))
                cur = (x, y); i += 4
        if pts:
            polys.append(pts)
        for q in polys:
            cv2.fillPoly(m, [np.array(q, np.int32)], 1)
    for (x0, y0, x1, y1) in d.get('deco', []):
        cv2.rectangle(m, (x0, y0), (x1, y1), 1, -1)
    return m


def walls_of(im, region, erase=()):
    dark = (im < THR).astype(np.uint8)
    for (x0, y0, x1, y1) in erase:
        dark[y0:y1, x0:x1] = 0
    n, lab, st, _ = cv2.connectedComponentsWithStats(dark, 8)
    keep = np.zeros(n, bool)
    near = cv2.dilate(region, np.ones((41, 41), np.uint8))
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if max(w, h) >= MINLEN and a >= MINAREA and near[y:y + h, x:x + w].any():
            keep[i] = True
    return keep[lab].astype(np.uint8)


def comp_at(free, x, y, r=18):
    H, W = free.shape
    x, y = int(round(x)), int(round(y))
    best = None
    for dy in range(-r, r + 1, 2):
        for dx in range(-r, r + 1, 2):
            xx, yy = x + dx, y + dy
            if 0 <= xx < W and 0 <= yy < H and free[yy, xx]:
                dd = dx * dx + dy * dy
                if best is None or dd < best[0]:
                    best = (dd, xx, yy)
    return None if best is None else (best[1], best[2])


def flood(free, x, y):
    p = comp_at(free, x, y)
    if p is None:
        return None
    m = np.zeros((free.shape[0] + 2, free.shape[1] + 2), np.uint8)
    img = free.copy()
    cv2.floodFill(img, m, p, 2, flags=8)
    return img == 2


def label_spot(mask):
    dt = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    y, x = np.unravel_index(np.argmax(dt), dt.shape)
    return int(x), int(y), float(dt[y, x])


def skeleton_graph(hall):
    """Hall mask -> list of (points, edges) along its centre line (on a 2x downsampled grid)."""
    small = cv2.resize(hall.astype(np.uint8), (hall.shape[1] // 2, hall.shape[0] // 2), interpolation=cv2.INTER_NEAREST)
    small = cv2.morphologyEx(small, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    sk = skeletonize(small > 0)
    ys, xs = np.nonzero(sk)
    pix = set(zip(xs.tolist(), ys.tolist()))
    nb = lambda p: [(p[0] + dx, p[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx or dy) and (p[0] + dx, p[1] + dy) in pix]
    deg = {p: len(nb(p)) for p in pix}
    nodes = {p for p in pix if deg[p] != 2}
    seen = set(); edges = []
    def walk(a, b):
        path = [a, b]; prev, cur = a, b
        while cur not in nodes:
            nxt = [q for q in nb(cur) if q != prev and (cur, q) not in seen]
            if not nxt:
                break
            seen.add((cur, nxt[0])); seen.add((nxt[0], cur))
            prev, cur = cur, nxt[0]; path.append(cur)
        return path
    for a in list(nodes):
        for b in nb(a):
            if (a, b) in seen:
                continue
            seen.add((a, b)); seen.add((b, a))
            edges.append(walk(a, b))
    left = [p for p in pix if p not in nodes and not any((p, q) in seen for q in nb(p))]
    for p in left:  # closed loops without junctions
        if any((p, q) in seen for q in nb(p)):
            continue
        nodes.add(p)
        for b in nb(p):
            if (p, b) not in seen:
                seen.add((p, b)); seen.add((b, p)); edges.append(walk(p, b))
    # simplify each edge polyline, scale back x2
    out_pts = {}; out_edges = []
    def key(p):
        k = (p[0] * 2, p[1] * 2)
        out_pts.setdefault(k, len(out_pts)); return out_pts[k]
    for e in edges:
        if len(e) < 2:
            continue
        arr = np.array(e, np.int32).reshape(-1, 1, 2)
        s = cv2.approxPolyDP(arr, 1.5, False).reshape(-1, 2)
        ks = [key(tuple(p)) for p in s]
        for a, b in zip(ks, ks[1:]):
            if a != b:
                out_edges.append((a, b))
    pts = [None] * len(out_pts)
    for k, i in out_pts.items():
        pts[i] = k
    return pts, out_edges


def rect_door(r, corr):
    """Door estimate from the old box model: middle of the side that faces the nearest corridor box."""
    l, x0, x1, y0, y1 = r[:5]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    def dist(c):
        a, b, c2, d = c; dx = max(a - cx, 0, cx - c2); dy = max(b - cy, 0, cy - d); return dx * dx + dy * dy
    c = min(corr, key=dist)
    if y1 <= c[1] + 4: return cx, y1
    if y0 >= c[3] - 4: return cx, y0
    if x1 <= c[0] + 4: return x1, cy
    if x0 >= c[2] - 4: return x0, cy
    return cx, cy


vec, seed = {}, {}
for f in ORDER:
    d = F[f]
    if f in BOXF:
        B = build_box(f); OFF = 200; H, W = 520, 2600
        sh = lambda y: y + OFF
        hall = np.zeros((H, W), np.uint8)
        for (a0, b0, a1, b1) in B['corr']:
            cv2.rectangle(hall, (int(a0), int(sh(b0))), (int(a1) - 1, int(sh(b1)) - 1), 1, -1)
        labelled, room_masks = [], []
        for r in B['rooms']:
            x0, x1, y0, y1 = int(r['x']), int(r['x'] + r['w']), int(sh(r['y'])), int(sh(r['y'] + r['h']))
            labelled.append((r['l'], x0, x1, y0, y1, r['k'], tuple(r.get('al', ()))))
            m = np.zeros((H, W), np.uint8); cv2.rectangle(m, (x0, y0), (x1 - 1, y1 - 1), 1, -1); room_masks.append(m)
        cmid = sh((BCO[0] + BCO[1]) / 2)
        d = dict(d, corr=[(int(a0), int(sh(b0)), int(a1), int(sh(b1))) for a0, b0, a1, b1 in B['corr']],
                 st=[(l, hx, cmid) for l, hx in B['halls']], paths=[], ent=[])
        rooms_out = []
        for r in B['rooms']:
            x, y, w, h = r['x'], sh(r['y']), r['w'], r['h']
            o = {'l': r['l'], 'k': r['k'], 'x': x, 'y': y, 'w': w, 'h': h, 'p': f'M{x} {y}h{w}v{h}h{-w}Z',
                 'lx': x + w / 2, 'ly': y + h / 2, 'r': min(w, h) / 2, 'bw': w, 'bh': h}
            if r.get('al'):
                o['al'] = r['al']
            rooms_out.append(o)
        vec[f] = {'box': 1, 'off': OFF, 'band': [BX0, sh(BUP[0]), BX1, sh(BLO[1])],
                  'bb': [BX0 - 10, sh(BCORE_TOP) - 10, BX1 + 10, sh(BLO[1]) + 10],
                  'corr': [[a0, sh(b0), a1 - a0, b1 - b0] for a0, b0, a1, b1 in B['corr']],
                  'stubs': [[s['x'], sh(s['y']), s['w'], s['h']] for s in B['stubs']],
                  'cores': [dict(c, y=sh(c['y']), lifts=[[lx, sh(ly), lw] for lx, ly, lw in c.get('lifts', [])]) for c in B['cores']],
                  'rooms': rooms_out, 'labels': [], 'ent': [], 'paths': []}
    else:
        im = cv2.imread(os.path.join(HERE, 'scans', f'f{f}.jpg'), 0)
        H, W = im.shape
        region = poly_mask(im.shape, d)
        walls = walls_of(im, region, d.get('erase', ()))
        wallsC = cv2.morphologyEx(walls, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

        # building interior: everything the outer walls enclose (seal small gaps first)
        sealed = cv2.morphologyEx(walls, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
        ext = (1 - sealed).astype(np.uint8)
        ff = np.zeros((H + 2, W + 2), np.uint8)
        for sx, sy in ((1, 1), (W - 2, 1), (1, H - 2), (W - 2, H - 2)):
            if ext[sy, sx] == 1:
                cv2.floodFill(ext, ff, (sx, sy), 2)
        inside = (((ext != 2) | (cv2.erode(region, np.ones((15, 15), np.uint8)) > 0)) & (walls == 0)).astype(np.uint8)
        inside &= cv2.dilate(region, np.ones((41, 41), np.uint8))

        # rooms: flood the real region around every labelled room, closing door gaps progressively
        labelled = [r for r in d['rooms'] if r[0] and r[5] in ('room', 'place', 'wc', 'area')]
        seeds = [((r[1] + r[2]) / 2, (r[3] + r[4]) / 2) for r in labelled]
        room_masks = []
        for idx, r in enumerate(labelled):
            l, x0, x1, y0, y1, k, al = r
            E = (x1 - x0) * (y1 - y0); sx, sy = seeds[idx]; got = None
            for kk in (1, 5, 9, 13, 17, 23):
                wk = walls if kk == 1 else cv2.morphologyEx(walls, cv2.MORPH_CLOSE, np.ones((kk, kk), np.uint8))
                free = (inside & (wk == 0)).astype(np.uint8)
                m = flood(free, sx, sy)
                if m is None:
                    continue
                A = int(m.sum())
                others = sum(1 for j, s in enumerate(seeds) if j != idx and m[int(s[1]), int(s[0])] if 0 <= int(s[1]) < H and 0 <= int(s[0]) < W)
                if A <= 2.3 * E and A >= 0.55 * E and others == 0:
                    got = cv2.dilate(m.astype(np.uint8), np.ones((kk // 2 * 2 + 1,) * 2, np.uint8)) & (walls == 0)
                    break
                if A < 0.55 * E:
                    continue
            if got is None:  # merged with neighbours or open plan: real space inside the box
                box = np.zeros_like(walls); cv2.rectangle(box, (x0, y0), (x1, y1), 1, -1)
                got = box & (walls == 0) & inside if (box & inside).sum() > 0.3 * E else box
            room_masks.append(got.astype(np.uint8))

        rooms_all = np.zeros_like(walls)
        for m in room_masks:
            rooms_all |= m

        # halls: free space within the corridor zones
        zone = np.zeros_like(walls)
        for (x0, y0, x1, y1) in d['corr']:
            cv2.rectangle(zone, (x0 - 14, y0 - 14), (x1 + 14, y1 + 14), 1, -1)
        hall = (inside & (wallsC == 0) & (rooms_all == 0) & zone).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(hall, 4)
        for i in range(1, n):
            if st[i][4] < 400:
                hall[lab == i] = 0

        # ---- vector output ----
        # schematic: every room is a clean rectangle at its real place, no walls
        boxes = []
        for r, m in zip(labelled, room_masks):
            l, x0, x1, y0, y1, k, al = r
            ys, xs = np.nonzero(m)
            if len(xs) > 20:
                bx0, bx1 = np.percentile(xs, [2, 98]); by0, by1 = np.percentile(ys, [2, 98])
            else:
                bx0, bx1, by0, by1 = x0, x1, y0, y1
            boxes.append([float(bx0), float(by0), float(bx1) + 1, float(by1) + 1])
        for _ in range(3):  # split overlaps between neighbours at the middle
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    a_, b_ = boxes[i], boxes[j]
                    ox = min(a_[2], b_[2]) - max(a_[0], b_[0]); oy = min(a_[3], b_[3]) - max(a_[1], b_[1])
                    if ox <= 0 or oy <= 0:
                        continue
                    if ox <= oy:
                        if (a_[0] + a_[2]) < (b_[0] + b_[2]):
                            m_ = (max(a_[0], b_[0]) + min(a_[2], b_[2])) / 2; a_[2] = min(a_[2], m_); b_[0] = max(b_[0], m_)
                        else:
                            m_ = (max(a_[0], b_[0]) + min(a_[2], b_[2])) / 2; b_[2] = min(b_[2], m_); a_[0] = max(a_[0], m_)
                    else:
                        if (a_[1] + a_[3]) < (b_[1] + b_[3]):
                            m_ = (max(a_[1], b_[1]) + min(a_[3], b_[3])) / 2; a_[3] = min(a_[3], m_); b_[1] = max(b_[1], m_)
                        else:
                            m_ = (max(a_[1], b_[1]) + min(a_[3], b_[3])) / 2; b_[3] = min(b_[3], m_); a_[1] = max(a_[1], m_)
        # tidy rows/columns: box edges that are close get one shared coordinate
        from wallvec import _cluster
        for idxs in ((1, 3), (0, 2)):
            vals = [(b[i], 1.0) for b in boxes for i in idxs]
            if vals:
                m_ = _cluster(vals, 12); k_ = 0
                for b in boxes:
                    for i in idxs:
                        b[i] = m_[k_]; k_ += 1
        rooms_out = []
        for r, b in zip(labelled, boxes):
            l, x0, x1, y0, y1, k, al = r
            g = 3  # gap between neighbouring boxes
            X0, Y0, X1, Y1 = [int(round(v)) for v in (b[0] + g, b[1] + g, b[2] - g, b[3] - g)]
            if X1 - X0 < 6 or Y1 - Y0 < 6:
                X0, Y0, X1, Y1 = x0 + g, y0 + g, x1 - g, y1 - g
            o = {'l': l, 'k': k, 'p': f'M{X0} {Y0}H{X1}V{Y1}H{X0}Z', 'x': X0, 'y': Y0, 'w': X1 - X0, 'h': Y1 - Y0,
                 'lx': (X0 + X1) // 2, 'ly': (Y0 + Y1) // 2, 'r': min(X1 - X0, Y1 - Y0) / 2, 'bw': X1 - X0, 'bh': Y1 - Y0}
            if al:
                o['al'] = list(al)
            rooms_out.append(o)
        # stair / lift cores: keep their real outline, replace the scanned hatching with clean symbols
        halls_x = [x for _, x, _ in d['st']]
        vwalls = walls.copy(); cores = []
        for (x0, y0, x1, y1) in d['deco']:
            X0, Y0, X1, Y1 = max(x0 - 6, 0), max(y0 - 6, 0), min(x1 + 6, W), min(y1 + 6, H)
            ys_, xs_ = np.nonzero(walls[Y0:Y1, X0:X1])
            if len(xs_) < 30:
                continue
            hull = cv2.convexHull(np.stack([xs_ + X0, ys_ + Y0], 1).astype(np.int32)).reshape(-1, 2)
            hm = np.zeros_like(walls); cv2.fillPoly(hm, [hull], 1)
            inner = cv2.erode(hm, np.ones((15, 15), np.uint8))
            vwalls[inner > 0] = 0
            main = any(abs(hx - (x0 + x1) / 2) < 110 for hx in halls_x)
            top, bot = int(hull[:, 1].min()), int(hull[:, 1].max())
            split = int(top + (bot - top) * 0.62) if main else top
            boxes = []
            if main:
                y = top + 10
                while True:
                    row = np.nonzero(inner[y])[0] if y < H else []
                    if len(row) < 12:
                        y += 4
                        if y > split - 12:
                            break
                        continue
                    cx = (row[0] + row[-1]) / 2; s = min(row[-1] - row[0] - 4, 30)
                    if y + s > split:
                        break
                    boxes.append([round(float(cx - s / 2), 1), int(y), int(s)]); y += s + 5
            hx0, hy0, hx1, hy1 = int(hull[:, 0].min()), int(hull[:, 1].min()), int(hull[:, 0].max()), int(hull[:, 1].max())
            cores.append({'pts': [[hx0, hy0], [hx1, hy0], [hx1, hy1], [hx0, hy1]], 'split': split, 'main': bool(main), 'boxes': boxes,
                          'bb': [int(hull[:, 0].min()), top, int(hull[:, 0].max()), bot]})
        # interiors whose inner lines (seating, furniture, scan junk) are dropped: rooms + their boxes
        clutter = cv2.erode(rooms_all, np.ones((11, 11), np.uint8))
        for r in labelled:
            l, x0, x1, y0, y1 = r[:5]
            if x1 - x0 > 30 and y1 - y0 > 30:
                cv2.rectangle(clutter, (x0 + 9, y0 + 9), (x1 - 9, y1 - 9), 1, -1)
        for r in d['rooms']:
            if r[5] == 'svc' and r[2] - r[1] > 30 and r[4] - r[3] > 30:
                cv2.rectangle(clutter, (r[1] + 9, r[3] + 9), (r[2] - 9, r[4] - 9), 1, -1)
        clutter = ((clutter & (hall == 0)) | cv2.erode(hall, np.ones((9, 9), np.uint8))).astype(np.uint8)
        wy, wx = np.nonzero(walls)
        vec[f] = {
            'bb': [int(wx.min()), int(wy.min()), int(wx.max()), int(wy.max())],
            'wl': [],
            'cores': cores,
            'inside': straight_poly_path(cv2.morphologyEx(inside | walls, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8)) & cv2.dilate(region, np.ones((41, 41), np.uint8)), eps=10, min_area=4000),
            'hall': straight_poly_path(cv2.morphologyEx(hall, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8)), eps=8, min_area=600),
            'rooms': rooms_out,
            'deco': [{'x': a, 'y': b, 'w': c - a, 'h': e - b} for a, b, c, e in d['deco']],
            'ent': [{'l': l, 'x': x, 'y': y} for l, x, y in d['ent']],
            'paths': [{'a': A, 'b': B, 'w': w} for A, B, w in d.get('paths', [])],
            'labels': [{'t': t, 'x': x, 'y': y} for t, x, y in d['lab']],
        }

    # ---- routing graph along the hall centre lines ----
    pts, sk_edges = skeleton_graph(hall)
    nodes, edges = [], []
    for i, (x, y) in enumerate(pts):
        nodes.append({'id': f'k{f}_{i}', 't': 'c', 'x': int(x), 'y': int(y)})
    for a, b in sk_edges:
        edges.append([f'k{f}_{a}', f'k{f}_{b}'])
    P = np.array(pts, float) if pts else np.zeros((0, 2))
    hy, hx = np.nonzero(hall)
    HP = np.stack([hx, hy], 1).astype(float) if len(hx) else np.zeros((0, 2))
    nid = [0]

    def add(t, x, y, l=None, pre='n'):
        nid[0] += 1
        o = {'id': f'{pre}{f}_{nid[0]}', 't': t, 'x': int(round(x)), 'y': int(round(y))}
        if l:
            o['l'] = l
        nodes.append(o); return o

    def to_skel(n):
        if not len(P):
            return
        dd = ((P[:, 0] - n['x']) ** 2 + (P[:, 1] - n['y']) ** 2)
        j = int(np.argmin(dd)); edges.append([n['id'], f'k{f}_{j}'])

    def hall_point_near(x, y, mask=None):
        if not len(HP):
            return x, y
        cand = HP
        if mask is not None:
            ring = cv2.dilate(mask, np.ones((41, 41), np.uint8))
            sel = ring[HP[:, 1].astype(int), HP[:, 0].astype(int)] > 0
            if sel.any():
                cand = HP[sel]
        dd = (cand[:, 0] - x) ** 2 + (cand[:, 1] - y) ** 2
        j = int(np.argmin(dd)); return cand[j]

    for r, m in zip(labelled, room_masks):
        l, x0, x1, y0, y1, k, al = r
        if k not in ('room', 'place'):
            continue
        labs = [l] + list(al) if k == 'room' else list(al) + [l]
        for i, lab in enumerate(labs):
            tx, ty = rect_door(r, d['corr'])
            if len(labs) > 1:
                tx = x0 + (x1 - x0) * (i + 1) / (len(labs) + 1)
            hx_, hy_ = hall_point_near(tx, ty, m)
            to_skel(add('r', hx_, hy_, lab, 'r'))
    for (l, x, y) in d['st']:
        hx_, hy_ = hall_point_near(x, y)
        n = add('s', hx_, hy_, l, 's'); to_skel(n)
    pstarts = []
    for (A, B, w) in d.get('paths', []):
        a = add('c', *A, pre='c'); b = add('c', *B, pre='c'); edges.append([a['id'], b['id']]); to_skel(b); pstarts.append(a)
    for (l, x, y) in d['ent']:
        e = add('e', x, y, l, 'e')
        near = [p for p in pstarts if ((p['x'] - x) ** 2 + (p['y'] - y) ** 2) ** .5 < 60]
        if near:
            edges.append([e['id'], near[0]['id']])
        else:
            hx_, hy_ = hall_point_near(x, y); c = add('c', hx_, hy_, pre='c'); edges.append([e['id'], c['id']]); to_skel(c)

    # shortcuts: straight edges wherever two graph points see each other through the hall,
    # so routes run straight down corridors instead of following skeleton wiggles
    walk = cv2.dilate(hall, np.ones((5, 5), np.uint8))
    for n in list(nodes):  # special nodes may sit just outside the hall (doors, halls, entrances)
        cv2.circle(walk, (n['x'], n['y']), 10, 1, -1)
    XY = np.array([[n['x'], n['y']] for n in nodes], float)
    existing = {tuple(sorted(e)) for e in edges}
    for i in range(len(nodes)):
        dd = np.hypot(XY[:, 0] - XY[i, 0], XY[:, 1] - XY[i, 1])
        for j in np.nonzero((dd > 1) & (dd < 320))[0]:
            if j <= i:
                continue
            k = max(2, int(dd[j] / 4))
            xs = np.linspace(XY[i, 0], XY[j, 0], k).round().astype(int); ys = np.linspace(XY[i, 1], XY[j, 1], k).round().astype(int)
            if f in BOXF and abs(XY[j, 0] - XY[i, 0]) > 3 and abs(XY[j, 1] - XY[i, 1]) > 3:
                continue  # schematic floors: only straight corridor runs
            if walk[ys, xs].all():
                key2 = tuple(sorted((nodes[i]['id'], nodes[j]['id'])))
                if key2 not in existing:
                    existing.add(key2); edges.append(list(key2))

    # prune edges that are (almost) straight continuations of two shorter kept edges
    pos = {n['id']: (n['x'], n['y']) for n in nodes}
    L = lambda a, b: ((pos[a][0] - pos[b][0]) ** 2 + (pos[a][1] - pos[b][1]) ** 2) ** .5
    adj = {}
    for a_, b_ in edges:
        adj.setdefault(a_, set()).add(b_); adj.setdefault(b_, set()).add(a_)
    for a_, b_ in sorted({tuple(sorted(e)) for e in edges}, key=lambda e: -L(*e)):
        ln = L(a_, b_)
        if any(L(a_, k) + L(k, b_) <= ln * 1.03 + 1 for k in adj[a_] & adj[b_]):
            adj[a_].discard(b_); adj[b_].discard(a_)
    edges = sorted({tuple(sorted((a_, b_))) for a_ in adj for b_ in adj[a_]})
    edges = [list(e) for e in edges]
    used = {x for e in edges for x in e}
    nodes = [n for n in nodes if n['id'] in used or n['t'] != 'c']

    # bridge disconnected skeleton pieces (doors drawn as walls, scan noise)
    ids = {n['id']: i for i, n in enumerate(nodes)}
    parent = list(range(len(nodes)))
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for a, b in edges:
        parent[find(ids[a])] = find(ids[b])
    while True:
        groups = {}
        for i in range(len(nodes)):
            groups.setdefault(find(i), []).append(i)
        if len(groups) <= 1:
            break
        main = max(groups.values(), key=len)
        mainP = np.array([[nodes[i]['x'], nodes[i]['y']] for i in main], float)
        best = None
        for g in groups.values():
            if g is main:
                continue
            for i in g:
                dd = (mainP[:, 0] - nodes[i]['x']) ** 2 + (mainP[:, 1] - nodes[i]['y']) ** 2
                j = int(np.argmin(dd))
                if best is None or dd[j] < best[0]:
                    best = (dd[j], i, main[j])
        if best is None or best[0] > 400 ** 2:
            break
        edges.append([nodes[best[1]]['id'], nodes[best[2]]['id']]); parent[find(best[1])] = find(best[2])
    seed[f] = {'nodes': nodes, 'edges': edges}
    print(f, 'rooms', len(rooms_out), 'nodes', len(nodes), 'pieces', len({find(i) for i in range(len(nodes))}),
          'kb', round(sum(len(json.dumps(v, ensure_ascii=False)) for v in vec[f].values()) / 1024))

json.dump(vec, open(os.path.join(HERE, 'vec.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
json.dump(seed, open(os.path.join(HERE, 'seed.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
