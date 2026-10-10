"""Per-frame foot track for D5/#32 and ball track for the shot, from manual key frames + camera motion."""
import json, sys, numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import gaussian_filter1d
W = sys.argv[1]; N = 1291
A = [np.vstack([np.array(a), [0, 0, 1]]) for a in json.load(open(f"{W}/camera2.json"))["A"]]
G = [np.eye(3)]                      # G[i]: frame-i pixel -> frame-0 pixel (stabilised floor/scene coords)
for i in range(N - 1):
    G.append(G[-1] @ np.linalg.inv(A[i]))
def apply(M, p):
    v = M @ np.array([p[0], p[1], 1.0]); return v[:2] / v[2]
KEYS = {6: (1720, 724), 36: (1740, 730), 66: (1760, 744), 96: (1770, 742), 126: (1745, 750), 156: (1750, 755),
        186: (1745, 750), 216: (1730, 748), 246: (1710, 750), 276: (1690, 748), 306: (1685, 742), 336: (1705, 714),
        366: (1710, 662), 396: (1735, 650), 426: (1675, 572), 456: (1662, 572), 486: (1695, 590), 515: (1745, 598),
        545: (1772, 630), 575: (1685, 585), 605: (1445, 555), 635: (1290, 562), 665: (1175, 562), 695: (1170, 540),
        725: (1238, 522), 755: (1242, 560), 785: (1333, 545), 815: (1450, 542), 845: (1495, 538), 875: (1498, 528),
        905: (1360, 502), 935: (1175, 512), 947: (1120, 518), 959: (1055, 546), 971: (1005, 600), 983: (965, 600),
        995: (950, 605)}
fr = np.array(sorted(KEYS)); q = np.array([apply(G[f], KEYS[f]) for f in fr])
frames = np.arange(fr[0], fr[-1] + 1)
qs = np.stack([PchipInterpolator(fr, q[:, k])(frames) for k in (0, 1)], 1)
qs = np.stack([gaussian_filter1d(qs[:, k], 5, mode="nearest") for k in (0, 1)], 1)
foot = {}
for f, p in zip(frames, qs):
    x, y = apply(np.linalg.inv(G[f]), p)
    foot[int(f)] = [round(float(x), 1), round(float(y), 1), round(175 + 0.19 * (float(y) - 530), 1)]
# keep a take-off anchor through the release so the ring can fade in place
for f in range(fr[-1] + 1, 1020):
    foot[f] = list(foot[fr[-1]])
BALL = {1001: (867, 258), 1007: (840, 238), 1013: (817, 221), 1019: (787, 221), 1025: (757, 234), 1031: (730, 258),
        1037: (740, 261), 1043: (750, 281), 1049: (743, 308), 1055: (767, 361), 1061: (780, 424)}
bf = np.array(sorted(BALL)); bp = np.array([BALL[f] for f in bf], float)
bfr = np.arange(bf[0], bf[-1] + 1)
ball = {int(f): [round(float(PchipInterpolator(bf, bp[:, 0])(f)), 1), round(float(PchipInterpolator(bf, bp[:, 1])(f)), 1)] for f in bfr}
stab = {int(f): [round(float(p[0]), 1), round(float(p[1]), 1)] for f, p in zip(frames, qs)}
json.dump({"foot": foot, "stab": stab, "ball": ball, "rim": [735, 268],
           "G": {str(i): G[i].tolist() for i in range(N)}}, open(f"{W}/track.json", "w"))
err = [np.hypot(*(np.array(foot[int(f)][:2]) - KEYS[f])) for f in fr]
print("frames", len(foot), "max key error after smoothing px", round(max(err), 1), "mean", round(float(np.mean(err)), 1))
