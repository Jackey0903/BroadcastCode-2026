"""Robust per-frame camera motion (similarity) from frame i to i+1, full-res pixel units, sanitized."""
import cv2, numpy as np, json, sys
W = sys.argv[1]; N = 1291
orb = cv2.ORB_create(3000, fastThreshold=10)
mask = np.zeros((540, 960), np.uint8); mask[:int(540 * 0.86), :] = 255
bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
prev = None; A = []; bad = 0
for i in range(N):
    g = cv2.imread(f"{W}/all/f{i:04d}.jpg", cv2.IMREAD_GRAYSCALE)
    kp, des = orb.detectAndCompute(g, mask)
    if prev is not None:
        M = None
        kp0, des0 = prev
        if des is not None and des0 is not None:
            m = bf.match(des0, des)
            if len(m) >= 20:
                a = np.float32([kp0[x.queryIdx].pt for x in m]); b = np.float32([kp[x.trainIdx].pt for x in m])
                M, inl = cv2.estimateAffinePartial2D(a, b, method=cv2.RANSAC, ransacReprojThreshold=1.5, maxIters=4000)
        ok = M is not None
        if ok:
            s = np.hypot(M[0, 0], M[1, 0])
            ok = abs(s - 1) < 0.03 and abs(M[0, 2]) < 40 and abs(M[1, 2]) < 20
        if not ok:
            bad += 1; M = np.array([[1, 0, 0], [0, 1, 0]], float)
        M = M.copy(); M[:, 2] *= 2.0        # 960 -> 1920 scale (similarity is scale-invariant otherwise)
        A.append(M.tolist())
    prev = (kp, des)
json.dump({"units": "full-res px", "A": A}, open(f"{W}/camera2.json", "w"))
print("frames", N, "fallback", bad)
