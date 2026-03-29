# -*- coding: utf-8 -*-
"""
Iron Dome Missile Tracker — Day/Night Edition v3
=================================================
Day mode  → YOLOv8 shape detection (missile silhouette)
Night mode → DUAL engine:
               1. YOLOv8 (low-conf fallback for shape)
               2. NightFlameDetector (bright moving dot / flame / propellant glow)
                  Uses: Background subtraction + bright-spot thresholding + optical flow

At night, missiles are only visible as a moving dot of light or propellant flame.
Real Iron Dome and Patriot radar systems detect missile exhaust/IR signature.
This tracker simulates that with pure-OpenCV visible-light techniques.

Controls:
    Q  — Quit
    P  — Pause / Resume
    N  — Toggle Night/Day mode
    S  — Screenshot
"""

import cv2
import argparse
import time
import sys
import os
import io
import math
import collections
import numpy as np
from scipy.optimize import linear_sum_assignment
import threading
import json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

GLOBAL_GPS = "ACQUIRING..."

def acquire_gps():
    global GLOBAL_GPS
    try:
        from urllib.request import urlopen
        resp = urlopen("https://ipinfo.io/json", timeout=3).read()
        data = json.loads(resp)
        loc = data.get("loc", "0,0")
        lat, lon = loc.split(',')
        GLOBAL_GPS = f"{float(lat):.4f} N, {float(lon):.4f} E"
    except Exception:
        GLOBAL_GPS = "GPS SIGNAL LOST"

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_WEIGHTS = os.path.join(BASE_DIR, "models", "yolo26n_custom.pt")
FALLBACK_WEIGHTS = os.path.join(BASE_DIR, "models", "missile.pt")

AUTO_NIGHT_THRESHOLD = 60   # mean brightness → night mode
TRAIL_LENGTH         = 30   # frames of motion trail kept

MISSILE_CLASS_KEYWORDS = {
    "missile", "rocket", "agm", "aim", "sky-rocket",
    "ten-lua", "m-wta1", "projectile", "warhead"
}

# ── Colours ───────────────────────────────────────────────────────────────────
DAY_COLOUR_MISSILE   = (0, 0, 255)
DAY_COLOUR_OTHER     = (0, 200, 100)
DAY_COLOUR_HUD       = (0, 255, 255)

NIGHT_COLOUR_MISSILE = (0, 50, 255)   # bright red — YOLO hit
NIGHT_COLOUR_FLAME   = (0, 140, 255)  # orange — flame/hot-dot hit
NIGHT_COLOUR_OTHER   = (200, 200, 200)   # white/grey
NIGHT_COLOUR_HUD     = (255, 255, 255)   # white HUD
NIGHT_TRAIL_COLOUR   = (150, 150, 150)   # grey trail

THREAT_CLEAR   = (0, 220, 60)
THREAT_CAUTION = (0, 180, 255)
THREAT_ALERT   = (0, 0, 255)


# ─────────────────────────────────────────────────────────────────────────────
# Night Flame / Hot-Dot Detector
# ─────────────────────────────────────────────────────────────────────────────

class NightFlameDetector:
    """
    Detects missiles at night as bright MOVING objects — propellant flame / exhaust dot.

    Signals combined (AND):
      1. Bright-spot mask  — high intensity pixels = flame glow
      2. Motion mask (MOG2) — only objects that MOVE against the background

    Additional shape filters:
      • Aspect-ratio reject  — wide flat blobs = text bars / banners (not missiles)
      • Max area cap        — huge blobs = explosions / full-screen flare
      • Frame-edge exclusion — channel logos and tickers live at the edges
    """

    def __init__(self, bright_thresh: int = 200, min_area_px: int = 20,
                 max_area_px: int = 150000,
                 edge_margin_frac: float = 0.06,
                 max_aspect_ratio: float = 6.0):
        self.bright_thresh      = bright_thresh
        self.min_area           = min_area_px
        self.max_area           = max_area_px
        self.edge_margin_frac   = edge_margin_frac   # fraction of frame to ignore at borders
        self.max_aspect_ratio   = max_aspect_ratio   # blobs wider/taller than this = text/bars
        self.bg_subtractor      = cv2.createBackgroundSubtractorMOG2(history=150, varThreshold=35, detectShadows=False)

    def detect(self, frame) -> list[dict]:
        h_fr, w_fr = frame.shape[:2]

        # Exclusion margins (top, bottom, left, right) in pixels
        mg = int(self.edge_margin_frac * min(h_fr, w_fr))

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # ── Signal 1: Bright-spot mask ────────────────────────────────────
        _, bright_mask = cv2.threshold(gray, self.bright_thresh, 255, cv2.THRESH_BINARY)
        # ── Signal 2: MOG2 Motion Flow mask ───────────────────────────────
        motion_mask = self.bg_subtractor.apply(frame)
        _, motion_mask = cv2.threshold(motion_mask, 127, 255, cv2.THRESH_BINARY)

        # Intersect bright spots with active motion flow
        flow_mask = cv2.bitwise_and(bright_mask, motion_mask)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        flow_mask = cv2.dilate(flow_mask, kernel, iterations=1)
        flow_mask = cv2.morphologyEx(flow_mask, cv2.MORPH_CLOSE, kernel)

        num_labels, _, stats, centroids = cv2.connectedComponentsWithStats(
            flow_mask, connectivity=8
        )

        detections = []
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < self.min_area or area > self.max_area:
                continue

            bx = stats[i, cv2.CC_STAT_LEFT]
            by = stats[i, cv2.CC_STAT_TOP]
            bw = stats[i, cv2.CC_STAT_WIDTH]
            bh = stats[i, cv2.CC_STAT_HEIGHT]
            cx = int(centroids[i][0])
            cy = int(centroids[i][1])

            # ── Filter 1: Edge & Ground Exclusion ───────────────────────────
            # Skip blobs at the very top/left/right edge of the frame (logos/text)
            # ALSO completely ignore the bottom 30% of the screen (city lights, ground clutter)
            ground_y = int(h_fr * 0.70)
            if cx < mg or cx > w_fr - mg or cy < mg or cy > ground_y:
                continue

            # ── Filter 2: Aspect ratio (reject wide/tall text/scatter) ───────────
            if bh > 0 and bw > 0:
                aspect = max(bw, bh) / min(bw, bh)
                if aspect > self.max_aspect_ratio:
                    continue   # Very elongated strip = text bar / streak, not missile dot

            # Pad box for visibility
            pad = 12
            bx = max(0, bx - pad)
            by = max(0, by - pad)
            bw += pad * 2
            bh += pad * 2

            mean_bright = float(np.mean(gray[
                stats[i, cv2.CC_STAT_TOP]:
                stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT],
                stats[i, cv2.CC_STAT_LEFT]:
                stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH]
            ]))
            confidence = min(0.99, 0.40 + (mean_bright / 255.0) * 0.55 +
                             (area / self.max_area) * 0.05)

            detections.append({
                "label":      "Missile",
                "confidence": confidence,
                "box":        (bx, by, bw, bh),
                "source":     "flame",
            })

        return detections

    def reset(self):
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=150, varThreshold=35, detectShadows=False)

# ───────────────────────────────────────────────────────────────────────────────
# Static Light Filter
# ───────────────────────────────────────────────────────────────────────────────

class StaticLightFilter:
    """
    Suppresses detections that come from STATIC light sources:
    city lights, building windows, video text overlays, channel logos.

    Key insight: MISSILES MOVE. A city light / text stays in the same
    screen region frame after frame.

    Implementation:
      - Divide the frame into a coarse grid of cells (default 40×40 px).
      - Count how many consecutive frames each cell has held a bright blob.
      - If a cell’s count exceeds `static_thresh` → it’s a static light — suppress.
      - If a cell has NO detection for `decay` frames → reset its counter
        (handles camera pans that expose new static lights).

    A real missile travels fast enough to leave any 40-px cell within
    a few frames, so its count stays low and it is NEVER suppressed.
    """

    def __init__(self, grid_size: int = 30,     # Finer grid for precision
                 world_thresh: int = 8,      # Suppresses City Lights after only 8 frames
                 cam_thresh: int = 25,     
                 decay: int = 12):           # Remembers static lights better during panned motion
        self.grid_size = grid_size
        self.world_thresh = world_thresh  # Suppresses City Lights (Static in World)
        self.cam_thresh = cam_thresh      # Suppresses Burned-in Text/Logos (Static in Camera)
        self.decay = decay
        
        self._w_hits, self._w_abs = {}, {}
        self._c_hits, self._c_abs = {}, {}

    def filter(self, detections: list, cam_x: float, cam_y: float) -> list:
        active_w, active_c = set(), set()
        
        # 1. Map Detections to Both Grids
        for d in detections:
            bx, by, bw, bh = d["box"]
            cx = bx + bw // 2
            cy = by + bh // 2
            
            c_cell = (cx // self.grid_size, cy // self.grid_size)
            w_cell = (int(cx + cam_x) // self.grid_size, int(cy + cam_y) // self.grid_size)
            
            active_c.add(c_cell)
            active_w.add(w_cell)

        # 2. Process Camera-Fixed Matrix (Burned in Text)
        for cell in active_c:
            self._c_hits[cell]   = self._c_hits.get(cell, 0) + 1
            self._c_abs[cell]    = 0
        for cell in list(self._c_hits.keys()):
            if cell not in active_c:
                self._c_abs[cell] = self._c_abs.get(cell, 0) + 1
                if self._c_abs[cell] >= self.decay:
                    del self._c_hits[cell]
                    self._c_abs.pop(cell, None)

        # 3. Process World-Fixed Matrix (City Lights / Ground Structures)
        for cell in active_w:
            self._w_hits[cell]   = self._w_hits.get(cell, 0) + 1
            self._w_abs[cell]    = 0
        for cell in list(self._w_hits.keys()):
            if cell not in active_w:
                self._w_abs[cell] = self._w_abs.get(cell, 0) + 1
                if self._w_abs[cell] >= self.decay:
                    del self._w_hits[cell]
                    self._w_abs.pop(cell, None)

        # 4. Filter Detections
        result = []
        for d in detections:
            bx, by, bw, bh = d["box"]
            cx = bx + bw // 2
            cy = by + bh // 2
            
            c_cell = (cx // self.grid_size, cy // self.grid_size)
            w_cell = (int(cx + cam_x) // self.grid_size, int(cy + cam_y) // self.grid_size)
            
            if self._c_hits.get(c_cell, 0) > self.cam_thresh:
                continue  # Screen clutter (Logo/Timestamp)
            if self._w_hits.get(w_cell, 0) > self.world_thresh:
                continue  # World clutter (Streetlamps/Buildings)
                
            result.append(d)
        return result

    def reset(self):
        self._w_hits.clear()
        self._w_abs.clear()
        self._c_hits.clear()
        self._c_abs.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Night-Vision Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def apply_night_vision(frame):
    """
    Real-time NVG/IR simulation:
      1. Gaussian denoise
      2. Bilateral filter (edge-preserving)
      3. CLAHE on L channel (contrast boost)
      4. Gamma correction (γ = 0.5 → brighten shadows)
    """
    denoised = cv2.GaussianBlur(frame, (3, 3), 0)
    denoised = cv2.bilateralFilter(denoised, 5, 50, 50)

    lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(8, 8))
    lab_eq = cv2.merge([clahe.apply(l_ch), a_ch, b_ch])
    enhanced = cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)

    inv_gamma = 1.0 / 0.5
    table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)],
                     dtype=np.uint8)
    return cv2.LUT(enhanced, table)


def apply_thermal_display(frame):
    """Grayscale/Thermal FLIR simulation + light scan-lines + vignette."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    thermal = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    h, w  = frame.shape[:2]
    Y, X  = np.ogrid[:h, :w]
    dist  = np.sqrt((X - w // 2) ** 2 + (Y - h // 2) ** 2)
    max_d = math.sqrt((w // 2) ** 2 + (h // 2) ** 2)
    vig   = np.clip(1.0 - (dist / max_d) * 0.50, 0.50, 1.0)
    for c in range(3):
        thermal[:, :, c] = (thermal[:, :, c] * vig).astype(np.uint8)

    # Slight scan-line texture
    thermal[::4, :] = (thermal[::4, :] * 0.85).astype(np.uint8)
    return thermal


def apply_nvg_display(frame):
    """Green phosphor NVG display rendering + scan-lines + vignette."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    nvg  = np.zeros_like(frame)
    nvg[:, :, 1] = gray
    nvg[:, :, 0] = (gray * 0.10).astype(np.uint8)
    nvg[:, :, 2] = (gray * 0.05).astype(np.uint8)

    h, w  = frame.shape[:2]
    Y, X  = np.ogrid[:h, :w]
    dist  = np.sqrt((X - w // 2) ** 2 + (Y - h // 2) ** 2)
    max_d = math.sqrt((w // 2) ** 2 + (h // 2) ** 2)
    vig   = np.clip(1.0 - (dist / max_d) * 0.65, 0.35, 1.0)
    for c in range(3):
        nvg[:, :, c] = (nvg[:, :, c] * vig).astype(np.uint8)

    nvg[::4, :] = (nvg[::4, :] * 0.4).astype(np.uint8)
    return nvg


# ─────────────────────────────────────────────────────────────────────────────
# Missile Trail Tracker
# ─────────────────────────────────────────────────────────────────────────────

class MissileTrail:
    def __init__(self, maxlen=TRAIL_LENGTH):
        self._trails: dict[int, collections.deque] = {}
        self._missed: dict[int, int] = {}
        self._hits: dict[int, int] = {}
        self._last_hit: dict[int, dict] = {}
        self._box_history: dict[int, collections.deque] = {}
        self._velocities: dict[int, tuple[float, float]] = {}  # (dx, dy)
        self._maxlen  = maxlen
        self._next_id = 1 
        self._confirm_frames = 3
        self._max_dist = 80  # Reduced for precision

    def update(self, hits: list[dict]) -> list[dict]:
        """Returns the assigned and confirmed target hits using stable Hungarian matching."""
        tids = list(self._trails.keys())
        num_targets = len(tids)
        num_hits = len(hits)
        matched_hits = set()
        matched_tids = set()

        # 1. Build cost matrix (Target x Hit)
        if num_targets > 0 and num_hits > 0:
            cost_matrix = np.zeros((num_targets, num_hits))
            for i, tid in enumerate(tids):
                dq = self._trails[tid]
                lx, ly = dq[-1]
                # Try to predict next spot using velocity
                dx, dy = self._velocities.get(tid, (0.0, 0.0))
                px, py = lx + dx, ly + dy
                
                for j, hit in enumerate(hits):
                    bx, by, bw, bh = hit["box"]
                    cx, cy = bx + bw // 2, by + bh // 2
                    # Cost is distance from predicted position
                    cost_matrix[i, j] = math.hypot(cx - px, cy - py)

            # 2. Hungarian Matching
            t_indices, h_indices = linear_sum_assignment(cost_matrix)
            
            # 3. Process matches
            for t_idx, h_idx in zip(t_indices, h_indices):
                dist = cost_matrix[t_idx, h_idx]
                if dist < self._max_dist:
                    tid = tids[t_idx]
                    hit = hits[h_idx]
                    matched_hits.add(h_idx)
                    matched_tids.add(tid)
                    
                    # Update target
                    bx, by, bw, bh = hit["box"]
                    cx, cy = bx + bw // 2, by + bh // 2
                    
                    # Calculate velocity for next frame (smoothed)
                    lx, ly = self._trails[tid][-1]
                    new_dx, new_dy = cx - lx, cy - ly
                    prev_dx, prev_dy = self._velocities.get(tid, (new_dx, new_dy))
                    self._velocities[tid] = (0.7*new_dx + 0.3*prev_dx, 0.7*new_dy + 0.3*prev_dy)

                    # Update history
                    self._trails[tid].append((cx, cy))
                    self._box_history[tid].append(hit["box"])
                    self._missed[tid] = 0
                    self._hits[tid] += 1
                    self._last_hit[tid] = hit
                    hit["tid"] = tid

        # 4. Handle unmatched hits (New Targets)
        for j, hit in enumerate(hits):
            if num_targets == 0 or j not in matched_hits:
                tid = self._next_id
                self._next_id += 1
                bx, by, bw, bh = hit["box"]
                cx, cy = bx + bw // 2, by + bh // 2
                
                self._trails[tid] = collections.deque(maxlen=self._maxlen)
                self._trails[tid].append((cx, cy))
                self._missed[tid] = 0
                self._hits[tid] = 1
                self._box_history[tid] = collections.deque(maxlen=5)
                self._box_history[tid].append(hit["box"])
                self._velocities[tid] = (0.0, 0.0)
                self._last_hit[tid] = hit
                hit["tid"] = tid
                matched_tids.add(tid)

        # 5. Handle unmatched targets (Missed Frames)
        active_tracked = []
        for tid in list(self._trails.keys()):
            is_confirmed = (self._hits[tid] >= self._confirm_frames)
            
            if tid in matched_tids:
                if is_confirmed:
                    # Smoothing logic (as approved before)
                    hist = self._box_history[tid]
                    avg_box = np.mean(hist, axis=0).astype(int)
                    hit = self._last_hit[tid].copy()
                    hit["box"] = tuple(avg_box.tolist())
                    active_tracked.append(hit)
            else:
                self._missed[tid] += 1
                if self._missed[tid] > 12: 
                    del self._trails[tid]
                    del self._missed[tid]
                    del self._hits[tid]
                    del self._last_hit[tid]
                    del self._box_history[tid]
                    if tid in self._velocities: del self._velocities[tid]
                else:
                    # In missed frames, do not guess position (as approved before)
                    pass

        return active_tracked

    def draw(self, frame, night_mode: bool):
        for dq in self._trails.values():
            pts = list(dq)
            for i in range(1, len(pts)):
                alpha = i / len(pts)
                t     = max(1, int(alpha * 3))
                c     = NIGHT_TRAIL_COLOUR if night_mode else DAY_COLOUR_OTHER
                dim   = tuple(int(x * 0.35) for x in c)
                cv2.line(frame, pts[i-1], pts[i], dim,  t + 4, cv2.LINE_AA)
                cv2.line(frame, pts[i-1], pts[i], c,    t,     cv2.LINE_AA)
        return frame


# ─────────────────────────────────────────────────────────────────────────────
# HUD
# ─────────────────────────────────────────────────────────────────────────────

def draw_detection(frame, x1, y1, x2, y2, label, confidence,
                   is_missile: bool, night_mode: bool, frame_idx: int,
                   tid: int, source: str = "yolo"):
    # ALL threats — whether shape (YOLO) or flame trail — are MISSILE colour
    if is_missile or source == "flame":
        colour = NIGHT_COLOUR_MISSILE if night_mode else DAY_COLOUR_MISSILE
    else:
        colour = NIGHT_COLOUR_OTHER if night_mode else DAY_COLOUR_OTHER

    if source == "flame" and night_mode:
        colour = NIGHT_COLOUR_FLAME

    # Main box
    cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 1)

    # Bracketing (corners)
    cl, lw = 20, 2
    for sx, sy, dx, dy in [(x1,y1,1,1),(x2,y1,-1,1),(x1,y2,1,-1),(x2,y2,-1,-1)]:
        cv2.line(frame, (sx, sy), (sx + dx*cl, sy),        colour, lw)
        cv2.line(frame, (sx, sy), (sx,         sy + dy*cl), colour, lw)

    # Crosshair inside the box
    cx_m = (x1 + x2) // 2
    cy_m = (y1 + y2) // 2
    cv2.drawMarker(frame, (cx_m, cy_m), colour, cv2.MARKER_CROSS, 10, 1, cv2.LINE_AA)

    # Pulsing lock-on ring
    if is_missile or source == "flame":
        radius = max(35, int(math.hypot(x2-x1, y2-y1) * 0.60))
        pulse  = 0.65 + 0.35 * math.sin(frame_idx * 0.35)
        rc     = tuple(int(v * pulse) for v in colour)
        cv2.circle(frame, (cx_m, cy_m), radius,     rc,                              1, cv2.LINE_AA)
        cv2.circle(frame, (cx_m, cy_m), radius + 6, tuple(int(v*0.35) for v in colour), 1, cv2.LINE_AA)

    # Military telemetry block
    tgt_id = f"TGT-{tid:03d}"
    
    # Fake telemetry calculated from position/size
    w_box = x2 - x1
    rng_km = max(0.5, 2000.0 / (w_box + 1e-5))           # small box = far away
    alt_m  = max(100.0, (frame.shape[0] - y2) * 18.5)    # high up = higher altitude
    spd_ms = 450 + (tid * 13) % 200                      # mach ~1.5 - 2.0
    
    dim_c = tuple(int(c * 0.7) for c in colour)
    
    if source == "flame":
        header = f"{tgt_id} [IR-EXHAUST] {confidence:.2f}"
    else:
        header = f"{tgt_id} [{label.upper()}] {confidence:.2f}"
        
    cv2.putText(frame, header, (x1, y1-25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, colour, 1, cv2.LINE_AA)
    
    cv2.putText(frame, f"RNG: {rng_km:.2f} km", (x2 + 10, y1 + 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, dim_c, 1, cv2.LINE_AA)
    cv2.putText(frame, f"ALT: {alt_m:.0f} m", (x2 + 10, y1 + 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, dim_c, 1, cv2.LINE_AA)
    cv2.putText(frame, f"SPD: {spd_ms} m/s", (x2 + 10, y1 + 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, dim_c, 1, cv2.LINE_AA)
        
    return frame


def draw_hud(frame, missile_count: int, fps: float, paused: bool,
             model_name: str, night_mode: bool, display_filter: str,
             frame_idx: int, brightness: float, threat_level: str):
    """Rich military-style telemetry and HUD overlay."""
    h, w  = frame.shape[:2]
    hud_c = NIGHT_COLOUR_HUD if night_mode else DAY_COLOUR_HUD
    dim_c = tuple(int(c * 0.6) for c in hud_c)

    # ── 1. Center Crosshairs + Pitch Ladder ──────────────────────────────────
    cx, cy = w // 2, h // 2
    # Main crosshair
    cv2.line(frame, (cx - 40, cy), (cx - 10, cy), hud_c, 1, cv2.LINE_AA)
    cv2.line(frame, (cx + 10, cy), (cx + 40, cy), hud_c, 1, cv2.LINE_AA)
    cv2.line(frame, (cx, cy - 40), (cx, cy - 10), hud_c, 1, cv2.LINE_AA)
    cv2.line(frame, (cx, cy + 10), (cx, cy + 40), hud_c, 1, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), 2, hud_c, -1)
    
    # Outer radar ring
    cv2.circle(frame, (cx, cy), 150, dim_c, 1, cv2.LINE_AA)
    
    # Artificial Horizon / Pitch Ladder (static for effect)
    for p in [-100, -50, 50, 100]:
        pw = 20 if abs(p) == 50 else 40
        cv2.line(frame, (cx - pw - 60, cy + p), (cx - 60, cy + p), dim_c, 1, cv2.LINE_AA)
        cv2.line(frame, (cx + 60, cy + p), (cx + pw + 60, cy + p), dim_c, 1, cv2.LINE_AA)
        cv2.putText(frame, f"{abs(p)}", (cx + pw + 65, cy + p + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.3, dim_c, 1)

    # ── 2. Top Banner Overlay ────────────────────────────────────────────────
    # Darker block behind text
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 90), (0,0,0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    cv2.line(frame, (0, 90), (w, 90), hud_c, 1)

    # Titles
    cv2.putText(frame, "TACTICAL ENGAGEMENT SYSTEM", (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.70, hud_c, 2, cv2.LINE_AA)
    cv2.putText(frame, "IRON DOME MK-III | AIRSPACE SURVEILLANCE", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.45, dim_c, 1, cv2.LINE_AA)
    
    # System Status (Left)
    cv2.putText(frame, f"SYS OP : NOMINAL", (15, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.40, hud_c, 1, cv2.LINE_AA)
    cv2.putText(frame, f"RADAR  : OMNI-DIRECTIONAL // HIGH RES", (15, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.40, hud_c, 1, cv2.LINE_AA)

    # Center-Right Status
    flt_text = display_filter.upper() if night_mode else "DAYLIGHT"
    cv2.putText(frame, f"FILTER : {flt_text}", (w // 2 - 50, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.40, hud_c, 1, cv2.LINE_AA)
    cv2.putText(frame, f"DATALNK: SECURE UPLINK", (w // 2 - 50, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.40, hud_c, 1, cv2.LINE_AA)
    cv2.putText(frame, f"GPS    : {GLOBAL_GPS}", (w // 2 - 50, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.40, dim_c, 1, cv2.LINE_AA)

    # Right Environment Status
    cv2.putText(frame, f"FPS  : {fps:.1f}", (w - 150, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, hud_c, 1, cv2.LINE_AA)
    cv2.putText(frame, f"LUM  : {brightness:.0f}/255", (w - 150, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.40, dim_c, 1, cv2.LINE_AA)
    time_str = time.strftime("%H:%M:%S", time.localtime())
    cv2.putText(frame, f"TIME : {time_str} LOC", (w - 150, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.40, dim_c, 1, cv2.LINE_AA)

    # ── 3. Bottom Threat Assessment Bar ──────────────────────────────────────
    overlay2 = frame.copy()
    cv2.rectangle(overlay2, (0, h-60), (w, h), (0,0,0), -1)
    cv2.addWeighted(overlay2, 0.7, frame, 0.3, 0, frame)
    cv2.line(frame, (0, h-60), (w, h-60), hud_c, 1)

    # Threat Threat Status Box
    if threat_level == "CLEAR":
        tc = THREAT_CLEAR
    elif threat_level == "CAUTION":
        tc = THREAT_CAUTION if (frame_idx // 15) % 2 == 0 else (0, 100, 180)
    else:
        tc = THREAT_ALERT if (frame_idx // 8) % 2 == 0 else (0, 0, 150)

    cv2.rectangle(frame, (10, h-50), (240, h-10), tc, -1)
    cv2.putText(frame, f"THREAT: {threat_level}", (20, h-25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0,0,0), 2, cv2.LINE_AA)

    # Active Targets tracker
    count_c = (NIGHT_COLOUR_MISSILE if night_mode else DAY_COLOUR_MISSILE) if missile_count > 0 else dim_c
    cv2.putText(frame, f"ACTIVE TARGETS TRACKED: {missile_count:02d}", (260, h-25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, count_c, 2, cv2.LINE_AA)

    # Controls
    cv2.putText(frame, "ENGAGEMENT PROTOCOLS: [Q] ABORT  [P] HALT  [N] OPTICS  [F] FILTER  [S] RECORD",
                (w - 600, h - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.40, dim_c, 1, cv2.LINE_AA)

    if paused:
        cv2.putText(frame, ">> TACTICAL HOLD <<", (cx - 200, cy - 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,200,255), 2, cv2.LINE_AA)

    return frame


# ─────────────────────────────────────────────────────────────────────────────
# Threat / Audio
# ─────────────────────────────────────────────────────────────────────────────

def threat_beep(threat_level: str, prev_level: str):
    try:
        import winsound
        if threat_level == "CAUTION" and prev_level == "CLEAR":
            winsound.Beep(880, 200)
        elif threat_level == "THREAT DETECTED":
            winsound.Beep(1200, 100)
            winsound.Beep(1200, 100)
    except Exception:
        pass


def get_scene_brightness(frame) -> float:
    return float(np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)))


def is_missile_class(label: str) -> bool:
    return any(kw in label.lower() for kw in MISSILE_CLASS_KEYWORDS)


def print_status(frame_idx, fps, total_missiles, night_mode):
    mode = "NIGHT" if night_mode else "DAY  "
    bar  = "|" * total_missiles if total_missiles else "- none -"
    sys.stdout.write(
        f"\r[{mode}][{frame_idx:>6}] {fps:>5.1f}fps | "
        f"[MISSILE] {total_missiles:>3}  {bar}"
    )
    sys.stdout.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────────────

def run(source, weights: str, conf: float, show_window: bool,
        force_night: bool, force_day: bool,
        night_sensitivity: int, save_output: bool,
        bright_thresh: int, min_flame_area: int) -> None:

    try:
        from ultralytics import YOLO
    except ImportError:
        sys.exit("[ERROR] ultralytics not installed.")

    if not os.path.isfile(weights):
        print(f"[WARN] Weights not found: {weights}")
        weights = FALLBACK_WEIGHTS

    print(f"[INFO] Loading YOLO model: {weights} ...", end=" ", flush=True)
    model = YOLO(weights)
    print("OK")

    flame_detector = NightFlameDetector(
        bright_thresh=bright_thresh,
        min_area_px=min_flame_area
    )
    static_filter = StaticLightFilter()

    class_names = model.names

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        sys.exit(f"[ERROR] Cannot open: {source!r}")

    threading.Thread(target=acquire_gps, daemon=True).start()

    src_label = "Webcam" if isinstance(source, int) else os.path.basename(str(source))
    print(f"[INFO] Source         : {src_label}")
    print(f"[INFO] YOLO conf      : {conf}")
    print(f"[INFO] Night thresh   : {night_sensitivity}")
    print(f"[INFO] Flame bright   : {bright_thresh}  | Min flame area: {min_flame_area}px")
    print(f"[INFO] Mode           : {'NIGHT forced' if force_night else 'DAY forced' if force_day else 'AUTO'}")
    print("[INFO] Controls: Q=Quit  P=Pause  N=Toggle Night  F=Cycle Filter  S=Screenshot")
    print("-" * 70)
    print("[LEGEND] YOLO:N = missile shape detections | FLAME:N = propellant flame/exhaust detections")
    print("-" * 70)

    # Video writer
    writer = None
    if save_output:
        fps_src = cap.get(cv2.CAP_PROP_FPS) or 30
        W, H    = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        out_path = os.path.join(BASE_DIR, "output_tracked.mp4")
        writer   = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps_src, (W, H))
        print(f"[INFO] Saving to: {out_path}")

    trail_yolo  = MissileTrail(maxlen=TRAIL_LENGTH + 10)  # unified trail for all missiles

    frame_idx             = 0
    fps                   = 0.0
    paused                = False
    night_mode            = force_night
    manual_night_override = None  # Tracks user 'N' key forced mode
    display_filter        = "thermal"  # 'thermal', 'nvg', 'original'
    prev_time             = time.perf_counter()
    prev_threat           = "CLEAR"
    annotated             = None

    # Optical Ego-Motion State
    prev_gray_small = None
    cam_x, cam_y = 0.0, 0.0

    while True:
        key = cv2.waitKey(1) & 0xFF if show_window else 0xFF

        if key == ord("q"):
            break
        if key == ord("p"):
            paused = not paused
        if key == ord("n"):
            night_mode = not night_mode
            manual_night_override = night_mode
            # Reset flame detector background model on mode switch
            flame_detector.reset()
            static_filter.reset()
            print(f"\n[TOGGLE] {'NIGHT' if night_mode else 'DAY'} mode")
        if key == ord("f"):
            filters = ["thermal", "nvg", "original"]
            idx = filters.index(display_filter)
            display_filter = filters[(idx + 1) % len(filters)]
            print(f"\n[TOGGLE] Visual filter changed to: {display_filter.upper()}")
        if key == ord("s") and annotated is not None:
            p = os.path.join(BASE_DIR, f"screenshot_{int(time.time())}.png")
            cv2.imwrite(p, annotated)
            print(f"\n[SS] {p}")

        if paused:
            if show_window and annotated is not None:
                cv2.imshow("Iron Dome Missile Tracker v3", annotated)
            time.sleep(0.05)
            continue

        ret, frame = cap.read()
        if not ret:
            print("\n[INFO] End of stream.")
            break

        # ── Optical Ego-Motion Tracking (Phase Correlate) ────────────────────
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_small = cv2.resize(gray_frame, (320, 180)) # Fast Phase Correlate Size
        
        if prev_gray_small is not None:
            # dx, dy is the shift from prev to current.
            # If camera pans right, image shifts left.
            shift, response = cv2.phaseCorrelate(np.float32(prev_gray_small), np.float32(gray_small))
            
            # ONLY update camera coordinates if the algorithm is confident 
            # (prevents hallucinating movement in a pitch-black sky)
            if response > 0.03: 
                dx = shift[0] * (frame.shape[1] / 320.0)
                dy = shift[1] * (frame.shape[0] / 180.0)
                cam_x -= dx
                cam_y -= dy
            
        prev_gray_small = gray_small

        frame_idx += 1
        now = time.perf_counter()
        fps = 1.0 / (now - prev_time) if (now - prev_time) > 0 else 0.0
        prev_time = now

        # ── Auto brightness → night mode ──────────────────────────────────────
        brightness = get_scene_brightness(frame)
        if manual_night_override is not None:
            night_mode = manual_night_override
        elif not force_night and not force_day:
            night_mode = brightness < night_sensitivity

        # ── Night-vision preprocessing for inference + display ────────────────
        if night_mode:
            enhanced = apply_night_vision(frame)
        else:
            enhanced = frame

        # ── YOLO inference ────────────────────────────────────────────────────
        # Lower confidence in night mode — shape may be partially visible
        night_conf = max(0.20, conf - 0.10) if night_mode else conf
        results = model(enhanced, conf=night_conf, verbose=False)[0]

        # ── Night Flame detector (only in night mode) ─────────────────────────
        flame_detections = []
        if night_mode:
            # Run ONCE on original frame — dark frames preserve hot pixel info better
            flame_detections = flame_detector.detect(frame)
            # Suppress static bright spots (city lights, text)
            flame_detections = static_filter.filter(flame_detections, cam_x, cam_y)
            # Deduplicate flame-vs-flame (same blob split into two nearby boxes)
            flame_detections = _dedup_detections(flame_detections, iou_thresh=0.30)
            # Remove any flame box that overlaps with a YOLO box (YOLO wins — higher quality)
            flame_detections = _remove_yolo_overlaps(
                flame_detections, results.boxes, class_names, iou_thresh=0.25
            )

        # ── Build display frame ───────────────────────────────────────────────
        if night_mode:
            if display_filter == "thermal":
                display = apply_thermal_display(enhanced)
            elif display_filter == "nvg":
                display = apply_nvg_display(enhanced)
            else:
                display = enhanced.copy()
        else:
            display = frame.copy()

        # ── Collect all hits (YOLO + Flame) ──────────────────────────────────
        hits = []
        for box in results.boxes:
            confidence = float(box.conf[0])
            class_id   = int(box.cls[0])
            label      = class_names.get(class_id, f"cls_{class_id}")
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            if is_missile_class(label):
                hits.append({
                    "box": (x1, y1, x2-x1, y2-y1),
                    "label": label,
                    "confidence": confidence,
                    "source": "yolo"
                })

        for d in flame_detections:
            if d["confidence"] < 0.35:
                continue
            hits.append(d)

        # ── Global NMS Deduplication (Fix overlapping / duplicated boxes) ────
        final_hits = []
        for h in sorted(hits, key=lambda x: -x["confidence"]):
            box = h["box"]
            duplicate = False
            for keep in final_hits:
                k_box = keep["box"]
                
                # Check Intersection over Minimum Area (IOA)
                # Safely suppresses tiny boxes sitting inside huge boxes
                ax1, ay1 = box[0], box[1]
                ax2, ay2 = ax1 + box[2], ay1 + box[3]
                bx1, by1 = k_box[0], k_box[1]
                bx2, by2 = bx1 + k_box[2], by1 + k_box[3]

                ix1, iy1 = max(ax1, bx1), max(ay1, by1)
                ix2, iy2 = min(ax2, bx2), min(ay2, by2)
                inter = max(0, ix2-ix1) * max(0, iy2-iy1)
                
                if inter > 0:
                    area_a = box[2] * box[3]
                    area_b = k_box[2] * k_box[3]
                    ioa = inter / float(min(area_a, area_b) + 1e-6)
                    # If 85% of the smaller box overlaps the larger box = duplicate target
                    if ioa > 0.85:  
                        duplicate = True
                        break
                
                # Check absolute Center Distance for fragmented blobs
                cx_a, cy_a = box[0] + box[2]/2, box[1] + box[3]/2
                cx_b, cy_b = k_box[0] + k_box[2]/2, k_box[1] + k_box[3]/2
                dist = math.hypot(cx_a - cx_b, cy_a - cy_b)
                
                # Use a hard minimum of 12 pixels for separation
                if dist < max(12.0, min(box[2], box[3]) * 0.40):
                    duplicate = True
                    break
                    
            if not duplicate:
                final_hits.append(h)
        hits = final_hits

        # ── Link Targets & Get IDs ───────────────────────────────────────────
        active_hits = trail_yolo.update(hits)
        missile_count = len([h for h in active_hits if h["source"] != "coast"])

        # ── Draw Detections + Trails ─────────────────────────────────────────
        for hit in active_hits:
            bx, by, bw, bh = hit["box"]
            draw_detection(display, bx, by, bx+bw, by+bh,
                           hit["label"], hit["confidence"],
                           True, night_mode, frame_idx, hit["tid"], source=hit["source"])



        trail_yolo.draw(display, night_mode)

        # ── Threat level ──────────────────────────────────────────────────────
        if missile_count == 0:
            threat = "CLEAR"
        elif missile_count <= 2:
            threat = "CAUTION"
        else:
            threat = "THREAT DETECTED"

        if threat != prev_threat:
            threat_beep(threat, prev_threat)
            print(f"\n[THREAT] {prev_threat} → {threat}  ({missile_count} missiles)")
            prev_threat = threat

        # ── Terminal ──────────────────────────────────────────────────────────
        print_status(frame_idx, fps, missile_count, night_mode)

        # ── HUD ───────────────────────────────────────────────────────────────
        if show_window:
            annotated = draw_hud(display, missile_count, fps, paused,
                                 weights, night_mode, display_filter, frame_idx, brightness, threat)
            cv2.imshow("Iron Dome Missile Tracker", annotated)
        else:
            annotated = display

        if writer:
            writer.write(annotated)

    cap.release()
    if writer:
        writer.release()
    if show_window:
        cv2.destroyAllWindows()
    print("\n[INFO] Tracker stopped.")


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────

def _iou(a, b):
    """IoU for (x,y,w,h) boxes."""
    ax1, ay1 = a[0], a[1]
    ax2, ay2 = ax1 + a[2], ay1 + a[3]
    bx1, by1 = b[0], b[1]
    bx2, by2 = bx1 + b[2], by1 + b[3]

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2-ix1) * max(0, iy2-iy1)
    if inter == 0:
        return 0.0
    union = (a[2]*a[3]) + (b[2]*b[3]) - inter
    return inter / union if union > 0 else 0.0


def _centre_dist(a, b):
    """Pixel distance between centres of two (x,y,w,h) boxes."""
    return math.hypot(
        a[0] + a[2]/2 - (b[0] + b[2]/2),
        a[1] + a[3]/2 - (b[1] + b[3]/2)
    )


def _dedup_detections(detections: list, iou_thresh: float = 0.50) -> list:
    """
    Remove duplicate flame detections.
    Two criteria — either overlapping boxes (IoU) OR very close centres
    (handles tiny dot blobs that barely overlap but are the same flame).
    """
    keep = []
    for d in sorted(detections, key=lambda x: -x["confidence"]):
        box = d["box"]
        # Min side of current box — used to set the centre-distance threshold
        min_side = max(8, min(box[2], box[3]))
        duplicate = False
        for k in keep:
            if _iou(box, k["box"]) > iou_thresh:
                duplicate = True
                break
            # Two detections whose centres are within 0.35× the box size = same missile
            if _centre_dist(box, k["box"]) < min_side * 0.35:
                duplicate = True
                break
        if not duplicate:
            keep.append(d)
    return keep


def _remove_yolo_overlaps(flame_dets: list, yolo_boxes,
                          class_names: dict, iou_thresh: float = 0.25) -> list:
    """
    Suppress any flame detection that significantly overlaps a YOLO detection.
    YOLO shape detection is higher quality — it wins.
    """
    if not yolo_boxes or len(yolo_boxes) == 0:
        return flame_dets

    yolo_rects = []
    for box in yolo_boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        yolo_rects.append((x1, y1, x2-x1, y2-y1))

    filtered = []
    for fd in flame_dets:
        overlaps = any(_iou(fd["box"], yr) > iou_thresh for yr in yolo_rects)
        if not overlaps:
            filtered.append(fd)
    return filtered


# ─────────────────────────────────────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Iron Dome Missile Tracker v3 — Day shape + Night flame/exhaust detection"
    )
    src = p.add_mutually_exclusive_group()
    src.add_argument("--video", "-v", metavar="PATH")
    src.add_argument("--cam",   "-c", type=int, default=0)

    p.add_argument("--weights",  "-w", default=DEFAULT_WEIGHTS)
    p.add_argument("--conf",     type=float, default=0.25,
                   help="YOLO confidence threshold (default 0.25)")
    p.add_argument("--no-window", action="store_true")

    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--night", action="store_true", help="Force night mode")
    mode.add_argument("--day",   action="store_true", help="Force day mode")

    p.add_argument("--night-sensitivity", type=int, default=AUTO_NIGHT_THRESHOLD,
                   help=f"Brightness threshold for auto night (default {AUTO_NIGHT_THRESHOLD})")
    p.add_argument("--save", action="store_true", help="Save to output_tracked.mp4")

    # Night flame detector tuning
    p.add_argument("--bright-thresh", type=int, default=170,
                   help="Pixel brightness (0-255) to count as flame/glow (default 170; lower=more sensitive)")
    p.add_argument("--min-flame-area", type=int, default=5,
                   help="Minimum bright blob area in pixels to count as missile flame (default 5)")

    return p.parse_args()


if __name__ == "__main__":
    args   = parse_args()
    source = args.video if args.video else args.cam
    run(
        source            = source,
        weights           = args.weights,
        conf              = args.conf,
        show_window       = not args.no_window,
        force_night       = args.night,
        force_day         = args.day,
        night_sensitivity = args.night_sensitivity,
        save_output       = args.save,
        bright_thresh     = args.bright_thresh,
        min_flame_area    = args.min_flame_area,
    )