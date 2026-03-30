# -*- coding: utf-8 -*-
"""
Iron Dome Missile Tracker — Precision Crosshair & Bold Hierarchy Edition
=============================================================================
Controls:
    Q  — Quit
    P  — Pause / Resume
    N  — Toggle Night/Day mode
    F  — Cycle Visual Filter (Thermal, NVG, Original)
    W  — Raise Ground Horizon (Ignore more city lights)
    S  — Lower Ground Horizon
    C  — Take Screenshot
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
from scipy.spatial import KDTree
import threading
import json
if os.name == 'nt':
    import winsound

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

AUTO_NIGHT_THRESHOLD = 60   
TRAIL_LENGTH         = 30   

MISSILE_CLASS_KEYWORDS = {
    "missile", "rocket", "agm", "aim", "sky-rocket",
    "ten-lua", "m-wta1", "projectile", "warhead"
}

DAY_COLOUR_MISSILE   = (0, 0, 255)
DAY_COLOUR_OTHER     = (40, 255, 40) # Bright Hacking Green
DAY_COLOUR_HUD       = (0, 255, 0)   # Tactical Hacking Green

NIGHT_COLOUR_MISSILE = (0, 50, 255)   
NIGHT_COLOUR_FLAME   = (0, 140, 255)  
NIGHT_COLOUR_OTHER   = (200, 200, 200)   
NIGHT_COLOUR_HUD     = (255, 255, 255)   
NIGHT_TRAIL_COLOUR   = (150, 150, 150)   

THREAT_CLEAR    = (0, 220, 60)    # Green
THREAT_CAUTION  = (0, 180, 255)   # Amber-yellow
THREAT_CRITICAL = (0, 100, 255)   # Deep orange
THREAT_ALERT    = (0, 0, 255)     # Red

# Pre-computed gamma LUT for night-vision shadow recovery (gamma = 0.55)
# Built once at import time so apply_night_vision() never recomputes it per frame.
_GAMMA = 0.55
_GAMMA_LUT = np.array(
    [((i / 255.0) ** (1.0 / _GAMMA)) * 255 for i in range(256)], dtype=np.uint8
)


# ─────────────────────────────────────────────────────────────────────────────
# Night Flame Detector
# ─────────────────────────────────────────────────────────────────────────────

class NightFlameDetector:
    def __init__(self, bright_thresh: int = 170, 
                 min_area_px: int = 2,
                 max_area_px: int = 50000,
                 edge_margin_frac: float = 0.06,
                 max_aspect_ratio: float = 5.0,
                 ground_y_frac: float = 0.70,
                 cluster_radius: int = 60,
                 max_cluster_size: int = 4,
                 mog_history: int = 150,
                 mog_var_thresh: int = 25):
        self.bright_thresh      = bright_thresh
        self.min_area           = min_area_px
        self.max_area           = max_area_px
        self.edge_margin_frac   = edge_margin_frac   
        self.max_aspect_ratio   = max_aspect_ratio   
        self.ground_y_frac      = ground_y_frac
        self.cluster_radius     = cluster_radius  
        self.max_cluster_size   = max_cluster_size   
        self.mog_history        = mog_history
        self.mog_var_thresh     = mog_var_thresh
        
        self.bg_subtractor      = cv2.createBackgroundSubtractorMOG2(history=self.mog_history, varThreshold=self.mog_var_thresh, detectShadows=False)

    def detect(self, small_frame, current_ground_frac, proxy_bright_mask=None,
                mog_learning_rate: float = -1) -> list[dict]:
        h_fr, w_fr = small_frame.shape[:2]
        mg = int(self.edge_margin_frac * min(h_fr, w_fr))

        if proxy_bright_mask is not None:
            bright_mask = proxy_bright_mask
        else:
            small_gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
            _, bright_mask = cv2.threshold(small_gray, self.bright_thresh, 255, cv2.THRESH_BINARY)

        # mog_learning_rate=-1 lets MOG2 auto-select; 0.0 freezes the model
        # (used during/after explosion flashes to prevent background poisoning)
        motion_mask = self.bg_subtractor.apply(small_frame, learningRate=mog_learning_rate)
        _, motion_mask = cv2.threshold(motion_mask, 127, 255, cv2.THRESH_BINARY)

        flow_mask = cv2.bitwise_and(bright_mask, motion_mask)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        flow_mask = cv2.dilate(flow_mask, kernel, iterations=1)
        flow_mask = cv2.morphologyEx(flow_mask, cv2.MORPH_CLOSE, kernel)

        num_labels, _, stats, centroids = cv2.connectedComponentsWithStats(flow_mask, connectivity=8)

        raw_detections = []
        # Optimization: also pull the raw brightness mask for intensity weighting
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < self.min_area or area > self.max_area:
                continue

            bx, by, bw, bh = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP], stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
            cx, cy = centroids[i][0], centroids[i][1]

            if cx < mg or cx > w_fr - mg or cy < mg:
                continue

            # 1. Circularity check: prioritize symmetric point sources (missiles)
            # Rejects elongated "light-streaks" or large rectangular building window reflections.
            aspect = max(bw, bh) / (min(bw, bh) + 1e-6)
            if aspect > self.max_aspect_ratio:
                continue
            
            extent = area / (bw * bh + 1e-6)
            if extent < 0.35: # Stricter extent gate for cleaner IR
                continue

            # 2. Intensity Saliency: measure peak brightness normalized to current scene
            # (Provides better SNR than area-based confidence alone)
            roi = bright_mask[by:by+bh, bx:bx+bw]
            peak_val = np.max(roi) if roi.size > 0 else 0
            
            raw_detections.append({
                "cx": cx, "cy": cy,
                "box": (bx, by, bw, bh),
                "area": area,
                "intensity": peak_val,
                "below_ground": (cy > (h_fr * current_ground_frac)),
            })

        if not raw_detections:
            return []

        # 3. Vectorized Cluster Rejection (KDTree)
        # Replaces O(N^2) loop with O(N log N) for high-speed city-light filtering.
        coords = np.array([[d["cx"], d["cy"]] for d in raw_detections])
        tree = KDTree(coords)
        
        filtered_detections = []
        for i, d in enumerate(raw_detections):
            # Query neighbors within cluster radius
            close_indices = tree.query_ball_point([d["cx"], d["cy"]], self.cluster_radius)
            tight_indices = tree.query_ball_point([d["cx"], d["cy"]], self.cluster_radius / 3.0)
            
            # City lights usually appear as high-density grid clusters/strings.
            is_city_light = (len(close_indices) > self.max_cluster_size) and (len(tight_indices) > 2)
            
            if not is_city_light:
                pad = 6
                bx, by, bw, bh = d["box"]
                bx, by = max(0, bx - pad), max(0, by - pad)
                bw, bh = bw + pad * 2, bh + pad * 2

                # 4. Intensity-Weighted Confidence
                # A very bright point source (intensity=255) is heavily prioritized.
                base_conf = 0.25 if d["below_ground"] else 0.40
                int_bonus = (d["intensity"] / 255.0) * 0.15
                area_bonus = (d["area"] / self.max_area) * 0.10
                confidence = min(0.99, base_conf + int_bonus + area_bonus)
                
                filtered_detections.append({
                    "label": "Missile",
                    "confidence": confidence,
                    "box": (bx, by, bw, bh),
                    "source": "flame",
                    "below_ground": d["below_ground"],
                })

        return filtered_detections

    def reset(self):
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=self.mog_history, varThreshold=self.mog_var_thresh, detectShadows=False)


class StaticLightFilter:
    def __init__(self, grid_size: int = 30, world_thresh: int = 8, cam_thresh: int = 25, decay: int = 12):           
        self.grid_size = grid_size
        self.world_thresh = world_thresh  
        self.cam_thresh = cam_thresh      
        self.decay = decay
        self._w_hits, self._w_abs = {}, {}
        self._c_hits, self._c_abs = {}, {}

    def filter(self, detections: list, cam_x: float, cam_y: float) -> list:
        active_w, active_c = set(), set()
        for d in detections:
            bx, by, bw, bh = d["box"]
            cx, cy = bx + bw // 2, by + bh // 2
            c_cell = (int(cx) // self.grid_size, int(cy) // self.grid_size)
            w_cell = (int(cx + cam_x) // self.grid_size, int(cy + cam_y) // self.grid_size)
            active_c.add(c_cell)
            active_w.add(w_cell)

        for cell in active_c:
            self._c_hits[cell]   = self._c_hits.get(cell, 0) + 1
            self._c_abs[cell]    = 0
        for cell in list(self._c_hits.keys()):
            if cell not in active_c:
                self._c_abs[cell] = self._c_abs.get(cell, 0) + 1
                if self._c_abs[cell] >= self.decay:
                    del self._c_hits[cell]
                    self._c_abs.pop(cell, None)

        for cell in active_w:
            self._w_hits[cell]   = self._w_hits.get(cell, 0) + 1
            self._w_abs[cell]    = 0
        for cell in list(self._w_hits.keys()):
            if cell not in active_w:
                self._w_abs[cell] = self._w_abs.get(cell, 0) + 1
                if self._w_abs[cell] >= self.decay:
                    del self._w_hits[cell]
                    self._w_abs.pop(cell, None)

        result = []
        for d in detections:
            bx, by, bw, bh = d["box"]
            cx, cy = bx + bw // 2, by + bh // 2
            c_cell = (int(cx) // self.grid_size, int(cy) // self.grid_size)
            w_cell = (int(cx + cam_x) // self.grid_size, int(cy + cam_y) // self.grid_size)
            if self._c_hits.get(c_cell, 0) > self.cam_thresh: continue 
            if self._w_hits.get(w_cell, 0) > self.world_thresh: continue
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

_VIGNETTE_CACHE = {}

def get_vignette_mask(h, w, intensity=0.50):
    key = (h, w, intensity)
    if key not in _VIGNETTE_CACHE:
        Y, X = np.ogrid[:h, :w]
        dist = np.sqrt((X - w // 2) ** 2 + (Y - h // 2) ** 2)
        max_d = math.sqrt((w // 2) ** 2 + (h // 2) ** 2)
        vig = np.clip(1.0 - (dist / max_d) * intensity, 1.0 - intensity, 1.0)
        _VIGNETTE_CACHE[key] = vig
    return _VIGNETTE_CACHE[key]

def apply_night_vision(frame):
    # 1. Noise reduction (Edge-preserving bilateral)
    denoised = cv2.bilateralFilter(frame, 5, 75, 75)
    
    # 2. Luminance Normalization (CLAHE)
    lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
    lab_eq = cv2.merge([clahe.apply(l_ch), a_ch, b_ch])
    enhanced = cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)
    
    # 3. Gamma Correction (Shadow Recovery - Brightens the darks)
    gamma = 0.55 
    inv_gamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)], dtype=np.uint8)
    return cv2.LUT(enhanced, table)

def apply_thermal_display(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    thermal = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    h, w  = frame.shape[:2]
    vig = get_vignette_mask(h, w, 0.50)
    for c in range(3): thermal[:, :, c] = (thermal[:, :, c] * vig).astype(np.uint8)
    step = max(2, int(h / 360))
    thermal[::step, :] = (thermal[::step, :] * 0.85).astype(np.uint8)
    return thermal

def apply_nvg_display(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    nvg  = np.zeros_like(frame)
    nvg[:, :, 1] = gray
    nvg[:, :, 0] = (gray * 0.10).astype(np.uint8)
    nvg[:, :, 2] = (gray * 0.05).astype(np.uint8)
    h, w  = frame.shape[:2]
    vig = get_vignette_mask(h, w, 0.65)
    for c in range(3): nvg[:, :, c] = (nvg[:, :, c] * vig).astype(np.uint8)
    step = max(2, int(h / 360))
    nvg[::step, :] = (nvg[::step, :] * 0.4).astype(np.uint8)
    return nvg


# ─────────────────────────────────────────────────────────────────────────────
# Tracker
# ─────────────────────────────────────────────────────────────────────────────

class MissileTrail:
    def __init__(self, maxlen=TRAIL_LENGTH, confirm_frames=3, max_dist=80, max_missed=12,
                 max_coast=6, vel_gate_mult=1.5, dir_penalty_mult=0.4,
                 vel_alpha=0.5, coast_drift=0.3, box_smooth_alpha=0.4,
                 trail_jump_mult=2.5):
        self._trails: dict[int, collections.deque] = {}
        self._missed: dict[int, int] = {}
        self._hits: dict[int, int] = {}
        self._last_hit: dict[int, dict] = {}
        self._box_history: dict[int, collections.deque] = {}
        self._velocities: dict[int, tuple[float, float]] = {}
        self._smooth_box: dict[int, list] = {}   # EMA-smoothed box for jitter-free display
        self._maxlen  = maxlen
        self._next_id = 1
        self._confirm_frames = confirm_frames
        self._max_dist = max_dist
        self._max_missed = max_missed
        self._max_coast       = max_coast        # frames to dead-reckon before hiding the box
        self._vel_gate_mult   = vel_gate_mult    # speed multiplier for assignment gate
        self._dir_penalty_mult = dir_penalty_mult # direction-penalty strength
        self._vel_alpha       = vel_alpha        # EMA weight for velocity update (new vs old)
        self._coast_drift     = coast_drift      # fraction of velocity applied during coast
        self._box_smooth_alpha = box_smooth_alpha # EMA alpha for displayed box smoothing
        # Max gap between consecutive trail points before the segment is skipped.
        # Prevents 'wire' lines when two nearby sources briefly swap IDs.
        self._trail_jump_limit = self._max_dist * trail_jump_mult

    def update(self, hits: list[dict]) -> list[dict]:
        tids = list(self._trails.keys())
        num_targets = len(tids)
        num_hits = len(hits)
        matched_hits = set()
        matched_tids = set()

        if num_targets > 0 and num_hits > 0:
            cost_matrix = np.full((num_targets, num_hits), 1e9)
            for i, tid in enumerate(tids):
                lx, ly, _ = self._trails[tid][-1]
                dx, dy = self._velocities.get(tid, (0.0, 0.0))
                px, py = lx + dx, ly + dy
                speed = math.hypot(dx, dy)
                gate = max(self._max_dist, speed * self._vel_gate_mult)
                for j, hit in enumerate(hits):
                    bx, by, bw, bh = hit["box"]
                    cx, cy = bx + bw // 2, by + bh // 2
                    raw_dist = math.hypot(cx - px, cy - py)
                    if speed > 2.0:
                        jx, jy = cx - lx, cy - ly
                        dot = (jx * dx + jy * dy) / (speed * (math.hypot(jx, jy) + 1e-6))
                        direction_penalty = max(0.0, -dot) * speed * self._dir_penalty_mult
                    else:
                        direction_penalty = 0.0
                    cost_matrix[i, j] = raw_dist + direction_penalty

            t_indices, h_indices = linear_sum_assignment(cost_matrix)
            for t_idx, h_idx in zip(t_indices, h_indices):
                tid = tids[t_idx]
                dist = cost_matrix[t_idx, h_idx]
                dx, dy = self._velocities.get(tid, (0.0, 0.0))
                speed = math.hypot(dx, dy)
                gate = max(self._max_dist, speed * self._vel_gate_mult)
                if dist < gate:
                    hit = hits[h_idx]
                    matched_hits.add(h_idx)
                    matched_tids.add(tid)
                    bx, by, bw, bh = hit["box"]
                    cx, cy = bx + bw // 2, by + bh // 2
                    lx, ly, _ = self._trails[tid][-1]
                    new_dx, new_dy = cx - lx, cy - ly
                    prev_dx, prev_dy = self._velocities.get(tid, (new_dx, new_dy))
                    self._velocities[tid] = (
                        self._vel_alpha * new_dx + (1.0 - self._vel_alpha) * prev_dx,
                        self._vel_alpha * new_dy + (1.0 - self._vel_alpha) * prev_dy,
                    )

                    src_size = (bw + bh) / 2.0
                    self._trails[tid].append((cx, cy, src_size))
                    self._box_history[tid].append(hit["box"])
                    self._missed[tid] = 0
                    self._hits[tid] += 1
                    self._last_hit[tid] = hit
                    hit["tid"] = tid

                    # EMA smooth the displayed box (alpha=0.4 → responsive but stable)
                    raw_box = list(hit["box"])
                    if tid in self._smooth_box:
                        sb = self._smooth_box[tid]
                        a = self._box_smooth_alpha
                        self._smooth_box[tid] = [
                            int(a * raw_box[k] + (1.0 - a) * sb[k]) for k in range(4)
                        ]
                    else:
                        self._smooth_box[tid] = raw_box[:]

        for j, hit in enumerate(hits):
            if j not in matched_hits:
                tid = self._next_id
                self._next_id += 1
                bx, by, bw, bh = hit["box"]
                cx, cy = bx + bw // 2, by + bh // 2
                src_size = (bw + bh) / 2.0
                self._trails[tid] = collections.deque(maxlen=self._maxlen)
                self._trails[tid].append((cx, cy, src_size))
                self._missed[tid] = 0
                self._hits[tid] = 1
                self._box_history[tid] = collections.deque(maxlen=5)
                self._box_history[tid].append(hit["box"])
                self._velocities[tid] = (0.0, 0.0)
                self._smooth_box[tid] = list(hit["box"])
                self._last_hit[tid] = hit
                hit["tid"] = tid
                matched_tids.add(tid)

        active_tracked = []
        for tid in list(self._trails.keys()):
            if tid in matched_tids:
                # Confirmed, live detection — use EMA-smoothed box
                if self._hits[tid] >= self._confirm_frames:
                    hit = self._last_hit[tid].copy()
                    sb = self._smooth_box.get(tid, list(self._box_history[tid][-1]))
                    hit["box"] = tuple(sb)
                    hit["dx"], hit["dy"] = self._velocities.get(tid, (0.0, 0.0))
                    hit["coasting"] = False
                    active_tracked.append(hit)
            else:
                self._missed[tid] += 1
                if self._missed[tid] > self._max_missed:
                    # Fully expired — purge track
                    del self._trails[tid]
                    del self._missed[tid]
                    del self._hits[tid]
                    del self._last_hit[tid]
                    del self._box_history[tid]
                    self._smooth_box.pop(tid, None)
                    if tid in self._velocities: del self._velocities[tid]
                elif (self._hits[tid] >= self._confirm_frames and
                      self._missed[tid] <= self._max_coast):
                    # COAST: dead-reckon position using last velocity so the box
                    # stays on-screen during brief MOG2 gaps (no blinking).
                    dx, dy = self._velocities.get(tid, (0.0, 0.0))
                    m = self._missed[tid]
                    sb = self._smooth_box.get(tid, list(self._box_history[tid][-1]))
                    coast_box = (
                        int(sb[0] + dx * m * self._coast_drift),
                        int(sb[1] + dy * m * self._coast_drift),
                        sb[2], sb[3]
                    )
                    hit = self._last_hit[tid].copy()
                    hit["box"] = coast_box
                    hit["dx"], hit["dy"] = dx, dy
                    hit["coasting"] = True
                    active_tracked.append(hit)
        return active_tracked

    def draw(self, frame, night_mode: bool, ui_scale: float):
        for tid, dq in self._trails.items():
            # If the bounding box is not active (missed a frame, or not confirmed yet),
            # instantly hide the tail so they are perfectly synced.
            if self._missed.get(tid, 0) > 0:
                continue
            if self._hits.get(tid, 0) < self._confirm_frames:
                continue

            pts = list(dq)
            if len(pts) < 2: continue

            trail_len = len(pts)
            for i in range(1, trail_len):
                x1, y1, s1 = pts[i-1]
                x2, y2, s2 = pts[i]

                # ── Discontinuity guard ──────────────────────────────────────
                # If two consecutive trail points are farther apart than the
                # allowed jump limit, it means the track ID was briefly stolen
                # by a nearby source. Skip this segment so no 'wire' line is
                # drawn across the gap.
                if math.hypot(x2 - x1, y2 - y1) > self._trail_jump_limit:
                    continue
                # ─────────────────────────────────────────────────────────────

                # alpha: 0.0 (oldest) -> 1.0 (newest)
                alpha = i / (trail_len - 1)

                # Dynamic thickness (Strictly capped to 5 for clarity)
                thick = min(int(2 * ui_scale), int(s2 * (0.15 + 0.65 * alpha)))
                thick = max(1, thick)

                # Color fading (dimming towards background/black)
                base_c = NIGHT_TRAIL_COLOUR if night_mode else DAY_COLOUR_OTHER

                # Add exhaust glow for the last few segments
                if i > trail_len - 6:
                    glow_c = (0, 165, 255) if night_mode else (0, 100, 255)
                    glow_weight = (i - (trail_len - 6)) / 6
                    c = tuple(int(base_c[j]*(1-glow_weight) + glow_c[j]*glow_weight) for j in range(3))
                else:
                    c = base_c

                # Apply alpha fading (dimming)
                draw_c = tuple(int(ch * (0.2 + 0.8 * alpha)) for ch in c)

                cv2.line(frame, (int(x1), int(y1)), (int(x2), int(y2)), draw_c, thick, cv2.LINE_AA)


# ─────────────────────────────────────────────────────────────────────────────
# HUD & Targeting Display 
# ─────────────────────────────────────────────────────────────────────────────

def draw_detection(frame, x1, y1, x2, y2, label, confidence,
                   is_missile: bool, night_mode: bool, frame_idx: int,
                   tid: int, ui_scale: float, dx: float = 0.0, dy: float = 0.0,
                   source: str = "yolo", in_ring: bool = False):
    
    # Establish Typography & Line Hierarchy (Thick Corners, Thin Data)
    lw_fine = 1            # Crisp thin lines for telemetry/data
    lw_bold = max(2, int(2 * ui_scale)) # Thick bold corners for target brackets
    font_th = 1            # Standard thin text
    font_th_bold = 1       # Priority bold text

    if is_missile or source == "flame":
        colour = NIGHT_COLOUR_MISSILE if night_mode else DAY_COLOUR_MISSILE
    else:
        colour = NIGHT_COLOUR_OTHER if night_mode else DAY_COLOUR_OTHER

    if source == "flame" and night_mode: colour = NIGHT_COLOUR_FLAME

    dim_c = tuple(int(c * 0.6) for c in colour)

    # 1. Bounding Box  ─────────────────────────────────────────────────────────
    bw, bh = x2 - x1, y2 - y1

    if in_ring:
        # ── IN-RING: Diamond targeting frame with bold corner L-brackets ────────
        cx_b, cy_b = (x1 + x2) // 2, (y1 + y2) // 2
        half = max(bw, bh) // 2 + int(8 * ui_scale)

        # Diamond vertices
        top    = (cx_b,        cy_b - half)
        right  = (cx_b + half, cy_b)
        bottom = (cx_b,        cy_b + half)
        left   = (cx_b - half, cy_b)
        pts = np.array([top, right, bottom, left], dtype=np.int32)

        # 1. Pulsing semi-transparent fill
        pulse      = abs(math.sin(frame_idx * 0.15))
        fill_alpha = 0.06 + 0.08 * pulse
        overlay = frame.copy()
        cv2.fillPoly(overlay, [pts], colour)
        cv2.addWeighted(overlay, fill_alpha, frame, 1.0 - fill_alpha, 0, frame)

        # 2. Thin diamond outline (dim)
        cv2.polylines(frame, [pts], isClosed=True, color=dim_c, thickness=lw_fine, lineType=cv2.LINE_AA)

        # 3. Bold L-brackets at each of the 4 diamond corners.
        #    Each L is two short lines running along the two adjacent diamond edges.
        #    Edge direction along the diamond is always +/-45° so step_xy = corner_len / sqrt(2).
        cl  = max(int(14 * ui_scale), int(half * 0.30))   # bracket arm length along the edge
        step = int(cl / math.sqrt(2))
        # (corner_point, dir_toward_edge1, dir_toward_edge2)  — each dir is (dx, dy)
        corners = [
            (top,    (+1, +1), (-1, +1)),   # Top    → toward Right and Left
            (right,  (-1, -1), (-1, +1)),   # Right  → toward Top  and Bottom
            (bottom, (+1, -1), (-1, -1)),   # Bottom → toward Right and Left
            (left,   (+1, -1), (+1, +1)),   # Left   → toward Top  and Bottom
        ]
        for (cpx, cpy), (d1x, d1y), (d2x, d2y) in corners:
            cv2.line(frame, (cpx, cpy),
                     (int(cpx + d1x * step), int(cpy + d1y * step)),
                     colour, lw_bold, cv2.LINE_AA)
            cv2.line(frame, (cpx, cpy),
                     (int(cpx + d2x * step), int(cpy + d2y * step)),
                     colour, lw_bold, cv2.LINE_AA)

        # 4. Outer precision ring + inner dot
        cv2.circle(frame, (cx_b, cy_b), half + int(5 * ui_scale), dim_c,  lw_fine, cv2.LINE_AA)
        cv2.circle(frame, (cx_b, cy_b), int(3 * ui_scale),        colour, -1,      cv2.LINE_AA)
    else:
        # ── STANDARD: Fighter-jet corner bracket box ───────────────────────────
        # Thin side edges
        cv2.rectangle(frame, (x1, y1), (x2, y2), dim_c, lw_fine, cv2.LINE_AA)

        # Differentiate minimum corner size based on detection source
        if is_missile and source == "yolo":
            corner_len = max(int(16 * ui_scale), int(min(bw, bh) * 0.35))
        elif source == "flame":
            corner_len = max(int(10 * ui_scale), int(min(bw, bh) * 0.25))
        else:
            corner_len = max(int(8 * ui_scale), int(min(bw, bh) * 0.20))

        # Corner brackets
        for px, py, sx, sy in [(x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)]:
            cv2.line(frame, (px, py), (px + sx * corner_len, py), colour, lw_bold, cv2.LINE_AA)
            cv2.line(frame, (px, py), (px, py + sy * corner_len), colour, lw_bold, cv2.LINE_AA)

    cx_m, cy_m = (x1 + x2) // 2, (y1 + y2) // 2

    # Center targeting dot
    if not in_ring:
        cv2.circle(frame, (cx_m, cy_m), int(3 * ui_scale), colour, -1, cv2.LINE_AA)

    # 3. Predictive Lead Indicator
    if abs(dx) > 0.5 or abs(dy) > 0.5:
        lead_frames = 15  
        lead_x = int(cx_m + dx * lead_frames)
        lead_y = int(cy_m + dy * lead_frames)
        
        cv2.line(frame, (cx_m, cy_m), (lead_x, lead_y), dim_c, lw_fine, cv2.LINE_AA)
        cv2.drawMarker(frame, (lead_x, lead_y), colour, cv2.MARKER_DIAMOND, int(10*ui_scale), lw_fine, cv2.LINE_AA)

    # 3. Lock-on Reticle (Double-Circle Design)  ──────────────────────────────
    if not in_ring and (is_missile or source == "flame"):
        radius = max(int(35*ui_scale), int(math.hypot(x2-x1, y2-y1) * 0.60))
        # Primary Outer Circle
        cv2.circle(frame, (cx_m, cy_m), radius, dim_c, lw_fine, cv2.LINE_AA)
        # Secondary Inner Circle (Overlapping)
        cv2.circle(frame, (cx_m, cy_m), radius - int(3 * ui_scale), colour, lw_fine, cv2.LINE_AA)
        
        tl = int(6 * ui_scale)
        cv2.line(frame, (cx_m, cy_m - radius), (cx_m, cy_m - radius + tl), colour, lw_fine, cv2.LINE_AA)
        cv2.line(frame, (cx_m, cy_m + radius), (cx_m, cy_m + radius - tl), colour, lw_fine, cv2.LINE_AA)
        cv2.line(frame, (cx_m - radius, cy_m), (cx_m - radius + tl, cy_m), colour, lw_fine, cv2.LINE_AA)
        cv2.line(frame, (cx_m + radius, cy_m), (cx_m + radius - tl, cy_m), colour, lw_fine, cv2.LINE_AA)

    # 4. Military Telemetry Block  ─────────────────────────────────────────────
    tgt_id = f"TGT-{tid:03d} [LOCKED]" if in_ring else f"TARGET-{tid:03d}"
    w_box = x2 - x1
    rng_km = max(0.5, 2000.0 / (w_box + 1e-5))           
    alt_m  = max(100.0, (frame.shape[0] - y2) * 18.5)    
    spd_ms = 450 + (tid * 13) % 200                      
    
    f_sc = 0.35 * ui_scale
    
    lbl_x = x2 + int(15 * ui_scale)
    lbl_y = y1 - int(15 * ui_scale)
    cv2.line(frame, (x2, y1), (lbl_x, lbl_y), dim_c, lw_fine, cv2.LINE_AA)
    cv2.line(frame, (lbl_x, lbl_y), (lbl_x + int(60 * ui_scale), lbl_y), dim_c, lw_fine, cv2.LINE_AA)

    txt_x = lbl_x + int(5 * ui_scale)
    y_step = int(14 * ui_scale)
    
    header = f"{tgt_id} [IR]" if source == "flame" else f"{tgt_id} [{label.upper()}]"
    
    # Priority Text (Header) gets BOLD thickness and slightly larger scale
    cv2.putText(frame, header, (txt_x, lbl_y - int(5*ui_scale)), cv2.FONT_HERSHEY_SIMPLEX, f_sc + 0.12, colour, font_th_bold, cv2.LINE_AA)
    
    # Routine data gets standard thin thickness
    cv2.putText(frame, f"RANGE: {rng_km:05.1f}KM", (txt_x, lbl_y + y_step), cv2.FONT_HERSHEY_SIMPLEX, f_sc, dim_c, font_th, cv2.LINE_AA)
    cv2.putText(frame, f"ALTITUDE: {alt_m:05.0f}M", (txt_x, lbl_y + y_step * 2), cv2.FONT_HERSHEY_SIMPLEX, f_sc, dim_c, font_th, cv2.LINE_AA)
    cv2.putText(frame, f"SPEED: {spd_ms:04d}M/S", (txt_x, lbl_y + y_step * 3), cv2.FONT_HERSHEY_SIMPLEX, f_sc, dim_c, font_th, cv2.LINE_AA)
    
    return frame

def draw_hud(frame, active_hits: list, fps: float, paused: bool,
             night_mode: bool, sensor_state: str, display_filter: str,
             frame_idx: int, brightness: float, threat_level: str, 
             ui_scale: float, ground_frac: float, is_auto_ground: bool):
    
    h, w  = frame.shape[:2]
    hud_c = NIGHT_COLOUR_HUD if night_mode else DAY_COLOUR_HUD
    dim_c = tuple(int(c * 0.5) for c in hud_c) 
    
    # Typography Hierarchy
    lw_fine = 1
    font_th = 1         # Standard data
    font_th_bold = 2    # Priority alerts

    # 1. Horizon Exclusion Line
    horizon_y = int(h * ground_frac)
    for x in range(0, w, int(30 * ui_scale)):
        cv2.line(frame, (x, horizon_y), (x + int(15 * ui_scale), horizon_y), (0, 0, 150), lw_fine)
    
    ground_status = "[AUTO]" if is_auto_ground else "[MAN]"
    cv2.putText(frame, f"GROUND EXCLUSION {ground_status} [{ground_frac:.2f}]", 
                (10, horizon_y - int(8*ui_scale)), cv2.FONT_HERSHEY_SIMPLEX, 0.3*ui_scale, (0, 0, 150), font_th, cv2.LINE_AA)

    # 2. CIRCULAR TARGETING HUD
    cx, cy = w // 2, h // 2
    ring_radius = int(220 * ui_scale)

    cv2.circle(frame, (cx, cy), ring_radius, dim_c, lw_fine, cv2.LINE_AA)
    
    tick_len = int(15 * ui_scale)
    cv2.line(frame, (cx, cy - ring_radius), (cx, cy - ring_radius + tick_len), hud_c, lw_fine, cv2.LINE_AA)
    cv2.line(frame, (cx, cy + ring_radius), (cx, cy + ring_radius - tick_len), hud_c, lw_fine, cv2.LINE_AA)
    cv2.line(frame, (cx - ring_radius, cy), (cx - ring_radius + tick_len, cy), hud_c, lw_fine, cv2.LINE_AA)
    cv2.line(frame, (cx + ring_radius, cy), (cx + ring_radius - tick_len, cy), hud_c, lw_fine, cv2.LINE_AA)

    # SHRINK THE CENTER BORESIGHT (Velocity Vector) FOR PRECISION
    r = int(1 * ui_scale)        # Reduced radius
    wing = int(3 * ui_scale)     # Reduced wings
    fin = int(2 * ui_scale)      # Reduced fin
    cv2.circle(frame, (cx, cy), r, hud_c, lw_fine, cv2.LINE_AA) 
    cv2.line(frame, (cx - r, cy), (cx - r - wing, cy), hud_c, lw_fine, cv2.LINE_AA) 
    cv2.line(frame, (cx + r, cy), (cx + r + wing, cy), hud_c, lw_fine, cv2.LINE_AA) 
    cv2.line(frame, (cx, cy - r), (cx, cy - r - fin), hud_c, lw_fine, cv2.LINE_AA)  

    # Pitch Ladder
    gap = int(35 * ui_scale)  
    pw = int(65 * ui_scale)   
    ladder_angles = [10, 5, -5, -10]
    
    for angle in ladder_angles:
        offset_y = int(-angle * 12 * ui_scale) 
        t_len = int(8 * ui_scale)
        t_dir = t_len if angle > 0 else -t_len 
        
        lx_start, lx_end = cx - gap - pw, cx - gap
        rx_start, rx_end = cx + gap, cx + gap + pw
        ly = cy + offset_y

        if angle > 0:
            cv2.line(frame, (lx_start, ly), (lx_end, ly), hud_c, lw_fine, cv2.LINE_AA)
            cv2.line(frame, (lx_start, ly), (lx_start, ly + t_dir), hud_c, lw_fine, cv2.LINE_AA)
            cv2.line(frame, (rx_start, ly), (rx_end, ly), hud_c, lw_fine, cv2.LINE_AA)
            cv2.line(frame, (rx_end, ly), (rx_end, ly + t_dir), hud_c, lw_fine, cv2.LINE_AA)
        else:
            dash_len = pw // 4
            for i in range(0, 4, 2):
                cv2.line(frame, (lx_start + i*dash_len, ly), (lx_start + (i+1)*dash_len, ly), dim_c, lw_fine, cv2.LINE_AA)
                cv2.line(frame, (rx_start + i*dash_len, ly), (rx_start + (i+1)*dash_len, ly), dim_c, lw_fine, cv2.LINE_AA)
            cv2.line(frame, (lx_start, ly), (lx_start, ly + t_dir), dim_c, lw_fine, cv2.LINE_AA)
            cv2.line(frame, (rx_end, ly), (rx_end, ly + t_dir), dim_c, lw_fine, cv2.LINE_AA)

        font_sc = 0.35 * ui_scale
        text_str = f"{abs(angle):02d}"
        cv2.putText(frame, text_str, (lx_start - int(24*ui_scale), ly + int(4*ui_scale)), cv2.FONT_HERSHEY_SIMPLEX, font_sc, hud_c, font_th, cv2.LINE_AA)
        cv2.putText(frame, text_str, (rx_end + int(8*ui_scale), ly + int(4*ui_scale)), cv2.FONT_HERSHEY_SIMPLEX, font_sc, hud_c, font_th, cv2.LINE_AA)

    h_ext = ring_radius - gap - int(20 * ui_scale)
    cv2.line(frame, (cx - gap - h_ext, cy), (cx - gap, cy), dim_c, lw_fine, cv2.LINE_AA)
    cv2.line(frame, (cx + gap, cy), (cx + gap + h_ext, cy), dim_c, lw_fine, cv2.LINE_AA)

    # 3. Top Banner (System Data)
    t_height = int(90 * ui_scale)
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, t_height), (0,0,0), -1)
    cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame) 
    cv2.line(frame, (0, t_height), (w, t_height), dim_c, lw_fine)

    f1, f2, f3 = 0.60 * ui_scale, 0.50 * ui_scale, 0.40 * ui_scale
    y1, y2, y3, y4 = int(25*ui_scale), int(45*ui_scale), int(65*ui_scale), int(85*ui_scale)
    
    x_mid, x_r = w // 2 - int(80*ui_scale), w - int(210*ui_scale)

    # Priority text gets font_th_bold
    cv2.putText(frame, "TACTICAL ENGAGEMENT SYSTEM", (20, y1), cv2.FONT_HERSHEY_SIMPLEX, f1, hud_c, font_th_bold, cv2.LINE_AA)
    cv2.putText(frame, "IRON DOME MK-III | AIRSPACE SURVEILLANCE", (15, y2), cv2.FONT_HERSHEY_SIMPLEX, f2, dim_c, font_th, cv2.LINE_AA)
    if sensor_state == "auto":
        mode_text = "AUTO (NIGHT)" if night_mode else "AUTO (DAY)"
    else:
        mode_text = "FORCE NIGHT" if sensor_state == "force_night" else "FORCE DAY"
    cv2.putText(frame, f"SENSOR MODE: {mode_text}", (15, y3), cv2.FONT_HERSHEY_SIMPLEX, f3, hud_c, font_th, cv2.LINE_AA)
    cv2.putText(frame, f"RADAR: OMNI-DIRECTIONAL // HIGH RES", (15, y4), cv2.FONT_HERSHEY_SIMPLEX, f3, hud_c, font_th, cv2.LINE_AA)


    flt_text = display_filter.upper() if display_filter in ["thermal", "nvg"] else "VISUAL"
    cv2.putText(frame, f"FILTER: {flt_text}", (x_mid, y1), cv2.FONT_HERSHEY_SIMPLEX, f2, hud_c, font_th, cv2.LINE_AA)
    cv2.putText(frame, f"DATALINK: SECURE", (x_mid, y2), cv2.FONT_HERSHEY_SIMPLEX, f2, hud_c, font_th, cv2.LINE_AA)
    cv2.putText(frame, f"GPS: {GLOBAL_GPS}", (x_mid, y3), cv2.FONT_HERSHEY_SIMPLEX, f2, dim_c, font_th, cv2.LINE_AA)

    cv2.putText(frame, f"FPS: {fps:.1f}", (x_r, y1), cv2.FONT_HERSHEY_SIMPLEX, f2, hud_c, font_th, cv2.LINE_AA)
    cv2.putText(frame, f"LUMINANCE: {brightness:.0f}/255", (x_r, y2), cv2.FONT_HERSHEY_SIMPLEX, f2, dim_c, font_th, cv2.LINE_AA)
    time_str = time.strftime("%H:%M:%S", time.localtime())
    cv2.putText(frame, f"TIME: {time_str}Z", (x_r, y3), cv2.FONT_HERSHEY_SIMPLEX, f2, dim_c, font_th, cv2.LINE_AA)

    # 4. Bottom Bar (Threats - HIGH PRIORITY)
    b_height = int(60 * ui_scale)
    overlay2 = frame.copy()
    cv2.rectangle(overlay2, (0, h-b_height), (w, h), (0,0,0), -1)
    cv2.addWeighted(overlay2, 0.5, frame, 0.5, 0, frame)
    cv2.line(frame, (0, h-b_height), (w, h-b_height), dim_c, lw_fine)

    if threat_level == "CLEAR":
        tc = THREAT_CLEAR
    elif threat_level == "CAUTION":
        tc = THREAT_CAUTION if (frame_idx // 15) % 2 == 0 else (0, 120, 180)
    elif threat_level == "CRITICAL":
        tc = THREAT_CRITICAL if (frame_idx // 10) % 2 == 0 else (0, 60, 180)
    else:  # THREAT DETECTED
        tc = THREAT_ALERT if (frame_idx // 8) % 2 == 0 else (0, 0, 150)

    # Increased box size and text scale for critical alerts
    threat_f = 0.55 * ui_scale
    cv2.rectangle(frame, (10, h-b_height+10), (int(250*ui_scale), h-10), tc, -1)
    cv2.putText(frame, f"THREAT: {threat_level}", (20, h-int(20*ui_scale)), cv2.FONT_HERSHEY_SIMPLEX, threat_f, (0,0,0), font_th_bold, cv2.LINE_AA)

    missile_count = len(active_hits)
    count_c = (NIGHT_COLOUR_MISSILE if night_mode else DAY_COLOUR_MISSILE) if missile_count > 0 else dim_c
    cv2.putText(frame, f"ACTIVE MISSILE TRACKED: {missile_count:02d}", (int(270*ui_scale), h-int(20*ui_scale)), cv2.FONT_HERSHEY_SIMPLEX, threat_f, count_c, font_th_bold, cv2.LINE_AA)

    shortcuts = "[Q] ABORT  [P] HALT  [N] OPTICS  [F] FILTER  [G] AUTO-G  [W/S] HORIZON  [C] CAPTURE"
    font_scale = 0.40 * ui_scale
    (text_width, _), _ = cv2.getTextSize(shortcuts, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_th)
    cv2.putText(frame, shortcuts, (w - text_width - int(20 * ui_scale), h - int(25 * ui_scale)), 
                cv2.FONT_HERSHEY_SIMPLEX, font_scale, dim_c, font_th, cv2.LINE_AA)

    if paused:
        cv2.putText(frame, ">> TACTICAL HOLD <<", (cx - int(150*ui_scale), cy - int(100*ui_scale)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8*ui_scale, (0,200,255), font_th_bold, cv2.LINE_AA)

    # 5. PPI Radar
    radar_r = int(50 * ui_scale)
    radar_cx, radar_cy = w - int(80*ui_scale), h - int(130*ui_scale)
    
    cv2.circle(frame, (radar_cx, radar_cy), radar_r, dim_c, lw_fine, cv2.LINE_AA)
    cv2.circle(frame, (radar_cx, radar_cy), radar_r // 2, dim_c, lw_fine, cv2.LINE_AA)
    cv2.line(frame, (radar_cx, radar_cy - radar_r), (radar_cx, radar_cy + radar_r), dim_c, lw_fine, cv2.LINE_AA)
    cv2.line(frame, (radar_cx - radar_r, radar_cy), (radar_cx + radar_r, radar_cy), dim_c, lw_fine, cv2.LINE_AA)
    
    sweep_angle = (frame_idx * 5) % 360
    sx = int(radar_cx + radar_r * math.cos(math.radians(sweep_angle)))
    sy = int(radar_cy + radar_r * math.sin(math.radians(sweep_angle)))
    cv2.line(frame, (radar_cx, radar_cy), (sx, sy), hud_c, lw_fine, cv2.LINE_AA)

    for hit in active_hits:
        hx, hy, hw, hh = hit["box"]
        rel_x = ((hx + hw/2) - w/2) / (w/2)
        rel_y = ((hy + hh/2) - h/2) / (h/2)
        plot_x = int(radar_cx + (rel_x * radar_r))
        plot_y = int(radar_cy + (rel_y * radar_r))
        
        if math.hypot(plot_x - radar_cx, plot_y - radar_cy) <= radar_r:
            hit_color = NIGHT_COLOUR_MISSILE if night_mode else DAY_COLOUR_MISSILE
            if hit.get("source") == "flame" and night_mode: hit_color = NIGHT_COLOUR_FLAME
            cv2.circle(frame, (plot_x, plot_y), max(2, int(2*ui_scale)), hit_color, -1, cv2.LINE_AA)

    return frame

def get_scene_brightness(frame) -> float:
    return float(np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)))

def is_missile_class(label: str) -> bool:
    return any(kw in label.lower() for kw in MISSILE_CLASS_KEYWORDS)

def compute_auto_horizon(small_frame):
    """
    Detects the topmost edge of the bright ground clutter band.
    Returns raw detected fraction (0.0–1.0) WITHOUT EMA smoothing.
    The caller is responsible for applying EMA and clamping.
    """
    ana_h, ana_w = 240, 320
    mini = cv2.resize(small_frame, (ana_w, ana_h))
    gray = cv2.cvtColor(mini, cv2.COLOR_BGR2GRAY)

    # 90th-percentile row profile — robust against single bright pixels/flares
    row_profile = np.percentile(gray, 90, axis=1).astype(np.uint8)

    # 7-pixel vertical median smoothing — removes salt-and-pepper spikes
    row_profile_smoothed = cv2.medianBlur(row_profile.reshape(-1, 1), 7).flatten()

    # Intensity threshold for "ground-level brightness"
    ground_thresh = 45

    # Only search the bottom 60 % of the frame (rows scan_limit … ana_h-1)
    # This hard-caps the horizon so the top 40 % is always available for sky/missiles
    scan_limit = int(ana_h * 0.40)

    # Find the TOPMOST row inside the scan window that starts (or belongs to)
    # a continuous bright band.  Strategy: scan top-to-bottom inside the scan
    # window; record the first bright row, then walk down while rows stay bright.
    # The topmost bright row is our raw horizon estimate.
    detected_y = ana_h - 1   # default = very bottom (exclude nothing)
    in_bright_band = False
    top_of_band = ana_h - 1

    for y in range(scan_limit, ana_h):
        if row_profile_smoothed[y] > ground_thresh:
            if not in_bright_band:
                top_of_band = y      # first row of this bright band
                in_bright_band = True
            detected_y = min(detected_y, top_of_band)
        else:
            in_bright_band = False

    # Safety bias: push the line significantly upward for confidence margin against tall structures
    # A 6% bias ensures unlit vertical obstacles (cranes, skyscraper tips) are pushed under the line
    safety_bias = int(ana_h * 0.06)
    detected_y = max(scan_limit, detected_y - safety_bias)

    return detected_y / float(ana_h)

# ─────────────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────────────

def run(source, weights: str, conf: float, show_window: bool,
        force_night: bool, force_day: bool, night_sensitivity: int, save_output: bool,
        bright_thresh: int, min_flame_area: int, max_flame_area: int, edge_margin: float,
        max_aspect_ratio: float, ground_fraction: float, static_grid: int, static_world_thresh: int,
        static_cam_thresh: int, static_decay: int, trail_length: int, track_max_dist: int,
        track_confirm: int, track_missed: int, default_filter: str,
        cluster_radius: int, cluster_max_size: int,
        mog_history: int, mog_var_thresh: int,
        auto_ground_alpha: float, night_conf_offset: float,
        cam_motion_thresh: float, flame_min_conf: float, device: str,
        track_coast: int, track_vel_gate: float, track_dir_penalty: float,
        track_vel_alpha: float, track_coast_drift: float, track_box_smooth: float,
        trail_jump_mult: float,
        flash_thresh: float, flash_cooldown_frames: int, max_horizon_rise: float,
        below_ground_conf: float, yolo_below_ground_conf: float) -> None:

    try: from ultralytics import YOLO
    except ImportError: sys.exit("[ERROR] ultralytics not installed.")

    print(f"[INFO] Loading YOLO model: {weights} ...", end=" ", flush=True)
    model = YOLO(weights)
    if device:
        print(f"(device: {device}) ...", end=" ")
        torch_device = f"cuda:{device}" if str(device).isdigit() else device
        
        # Friendly Fallback: Prevent crash if friend's PC lacks an NVIDIA GPU
        import torch
        if "cuda" in torch_device and not torch.cuda.is_available():
            print("\n[WARNING] Hardware GPU requested but not found. Falling back to CPU...", end=" ")
            torch_device = "cpu"
            
        model.to(torch_device)
    print("OK")

    flame_detector = NightFlameDetector(
        bright_thresh, min_flame_area, max_flame_area, edge_margin, max_aspect_ratio, ground_fraction,
        cluster_radius, cluster_max_size, mog_history, mog_var_thresh
    )
    static_filter = StaticLightFilter(static_grid, static_world_thresh, static_cam_thresh, static_decay)
    class_names = model.names

    if isinstance(source, int) or str(source).isdigit():
        if os.name == 'nt': cap = cv2.VideoCapture(int(source), cv2.CAP_DSHOW)
        else: cap = cv2.VideoCapture(int(source))
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        cap.set(cv2.CAP_PROP_FPS, 30)
    else:
        cap = cv2.VideoCapture(source)

    threading.Thread(target=acquire_gps, daemon=True).start()

    ret, test_frame = cap.read()
    if not ret: sys.exit("[ERROR] Cannot read video.")
    native_h, native_w = test_frame.shape[:2]
    
    global ui_sc
    ui_sc = native_h / 720.0

    w_orig = native_w   # safe default so end-of-stream display never raises NameError
    current_ground_frac = ground_fraction
    is_auto_ground = True
    # EMA state is kept here, NOT inside compute_auto_horizon, so the
    # smoothing history persists across frames without double-application.
    auto_ground_ema   = ground_fraction
    AUTO_GROUND_ALPHA = auto_ground_alpha

    print(f"[INFO] Active Source     : {source}")
    print(f"[INFO] Native Resolution : {native_w}x{native_h}")
    
    writer = None
    if save_output:
        fps_src = cap.get(cv2.CAP_PROP_FPS) or 30
        out_path = os.path.join(BASE_DIR, "output_tracked.mp4")
        writer   = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps_src, (native_w, native_h))

    trail_yolo = MissileTrail(
        maxlen=trail_length, confirm_frames=track_confirm,
        max_dist=track_max_dist, max_missed=track_missed,
        max_coast=track_coast, vel_gate_mult=track_vel_gate,
        dir_penalty_mult=track_dir_penalty, vel_alpha=track_vel_alpha,
        coast_drift=track_coast_drift, box_smooth_alpha=track_box_smooth,
        trail_jump_mult=trail_jump_mult,
    )

    frame_idx, fps = 0, 0.0
    paused = False
    if force_night:
        sensor_state = "force_night"
    elif force_day:
        sensor_state = "force_day"
    else:
        sensor_state = "auto"
    night_mode = force_night
    display_filter = default_filter
    filter_manual_override = False
    prev_time = time.perf_counter()
    prev_gray_small = None
    cam_x, cam_y = 0.0, 0.0
    announced_tids = set()

    # ── Explosion / flash immunity state ─────────────────────────────────────
    # rolling_brightness tracks the slow-moving "normal" scene brightness.
    # When a frame is much brighter than normal (explosion flash), we:
    #  (a) freeze the auto-horizon so it can't snap upward to the flash,
    #  (b) stop the MOG2 background subtractor from learning the bright frame,
    #  (c) hold a cooldown after the flash so ground lights can't flood as hits.
    rolling_brightness   = None          # slow EMA of scene brightness
    brightness_ema_alpha = 0.05          # very slow tracker of "normal" brightness
    flash_active         = False
    flash_cooldown_ctr   = 0
    # ─────────────────────────────────────────────────────────────────────────

    if not (isinstance(source, int) or str(source).isdigit()):
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    annotated = None
    try:
        while True:
            key = cv2.waitKey(1) & 0xFF if show_window else 0xFF
            if key == ord("q"):
                if os.name == 'nt': winsound.Beep(800, 200) # Abort: Low descending tone
                break
            if key == ord("p"):
                paused = not paused
                if os.name == 'nt': winsound.Beep(1400 if paused else 1600, 80) # Pause/Resume
            manual_toggle_triggered = False
            if key == ord("n"):
                if sensor_state == "auto":
                    sensor_state = "force_night"
                    if os.name == 'nt': winsound.Beep(1000, 100)
                elif sensor_state == "force_night":
                    sensor_state = "force_day"
                    if os.name == 'nt': winsound.Beep(1200, 100)
                else:
                    sensor_state = "auto"
                    if os.name == 'nt': winsound.Beep(1400, 100)
                manual_toggle_triggered = True
                
            if key == ord("f"):
                if os.name == 'nt': winsound.Beep(2000, 50) # Optics Filter Switch
                filters = ["thermal", "nvg", "original"] if night_mode else ["thermal", "original"]
                idx = (filters.index(display_filter) + 1) % len(filters) if display_filter in filters else 0
                display_filter = filters[idx]
                filter_manual_override = True
                
            if key == ord("w"): 
                current_ground_frac = max(0.1, current_ground_frac - 0.05)
                is_auto_ground = False
                if os.name == 'nt': winsound.Beep(1200, 50) # Manual Override Feedback
            if key == ord("s"): 
                current_ground_frac = min(1.0, current_ground_frac + 0.05)
                is_auto_ground = False
                if os.name == 'nt': winsound.Beep(1200, 50) # Manual Override Feedback
            if key == ord("g"):
                is_auto_ground = not is_auto_ground
                if os.name == 'nt': winsound.Beep(1500, 100) # Toggle Auto/Manual
            if key == ord("c") and annotated is not None:
                p = os.path.join(BASE_DIR, f"screenshot_{int(time.time())}.png")
                cv2.imwrite(p, annotated)
                if os.name == 'nt': # Camera Shutter: 2 quick clicks
                    threading.Thread(target=lambda: [winsound.Beep(2500, 30), winsound.Beep(1800, 30)], daemon=True).start()
                print(f"\n[SS] Captured Target Data: {p}")
    
            if paused: time.sleep(0.05); continue
    
            ret, frame = cap.read()
            if not ret: break
    
            h_orig, w_orig = frame.shape[:2]
            proc_w = 640
            proc_h = int(h_orig * (proc_w / w_orig))
            
            scale_x = w_orig / float(proc_w)
            scale_y = h_orig / float(proc_h)
    
            small_frame = cv2.resize(frame, (proc_w, proc_h))
    
            brightness = get_scene_brightness(small_frame)
            was_night = night_mode
            
            if sensor_state == "force_night":
                night_mode = True
            elif sensor_state == "force_day":
                night_mode = False
            else:
                night_mode = brightness < night_sensitivity

            if manual_toggle_triggered:
                flame_detector.reset()
                static_filter.reset()
                if not night_mode:
                    display_filter = "original"
                else:
                    display_filter = default_filter
                filter_manual_override = False
            elif frame_idx == 0:
                if not night_mode and not filter_manual_override:
                    display_filter = "original"
            else:
                if was_night and not night_mode and not filter_manual_override:
                    display_filter = "original"
                elif not was_night and night_mode and not filter_manual_override:
                    display_filter = default_filter

            # ── Flash / explosion detection ───────────────────────────────────
            if rolling_brightness is None:
                rolling_brightness = brightness
            else:
                # Only update the rolling average when NOT flashing so the
                # reference level never gets permanently elevated by explosions.
                if not flash_active:
                    rolling_brightness = (brightness_ema_alpha * brightness
                                          + (1.0 - brightness_ema_alpha) * rolling_brightness)

            flash_ratio = brightness / (rolling_brightness + 1.0)
            if flash_ratio >= flash_thresh:
                if not flash_active:
                    flash_active = True
                flash_cooldown_ctr = flash_cooldown_frames   # reset cooldown on every flash frame
            else:
                flash_active = False
                if flash_cooldown_ctr > 0:
                    flash_cooldown_ctr -= 1

            suppressing_mog = flash_active or (flash_cooldown_ctr > 0)
            # ─────────────────────────────────────────────────────────────────
    
            if night_mode:
                native_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # Apply Physics-Safe CLAHE contrast to uncover and boost critically faint 
                # distant targets organically without mathematically corrupting the dark night sky
                clahe_physics = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
                native_gray = clahe_physics.apply(native_gray)
                
                _, native_bright = cv2.threshold(native_gray, bright_thresh, 255, cv2.THRESH_BINARY)
                star_kernel = np.ones((7, 7), np.uint8)
                native_bright = cv2.dilate(native_bright, star_kernel, iterations=1)
                proxy_bright_mask = cv2.resize(native_bright, (proc_w, proc_h), interpolation=cv2.INTER_NEAREST)
            else:
                proxy_bright_mask = None
    
            gray_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
            if prev_gray_small is not None:
                shift, response = cv2.phaseCorrelate(np.float32(prev_gray_small), np.float32(gray_small))
                if response > cam_motion_thresh:
                    cam_x -= shift[0]
                    cam_y -= shift[1]
            prev_gray_small = gray_small
    
            frame_idx += 1
            now = time.perf_counter()
            fps = 1.0 / (now - prev_time) if (now - prev_time) > 0 else 0.0
            prev_time = now

            if not night_mode:
                # Day mode: ground exclusion is disabled entirely.
                # YOLO AI vision does not need a horizon line — it detects missile
                # shapes at any position. Force ground_frac to 1.0 so the comparison
                # cy >= ground_y_orig is never true (line sits at the very bottom).
                current_ground_frac = 1.0
            elif is_auto_ground:
                raw_frac = compute_auto_horizon(small_frame)

                if flash_active:
                    # Explosion in the sky: freeze the horizon exactly where it is.
                    pass
                else:
                    # Normal EMA update — asymmetrically rate-limited so the line
                    # cannot spike upward faster than max_horizon_rise per frame.
                    candidate = AUTO_GROUND_ALPHA * raw_frac + (1.0 - AUTO_GROUND_ALPHA) * auto_ground_ema
                    if candidate < auto_ground_ema:
                        candidate = max(candidate, auto_ground_ema - max_horizon_rise)
                    auto_ground_ema = candidate

                # Hard cap: exclusion zone can never exceed bottom 60 % of frame
                current_ground_frac = max(0.40, min(0.95, auto_ground_ema))

            # Keep the flame detector's horizon in sync with the live ground frac
            flame_detector.ground_y_frac = current_ground_frac
    
            if night_mode: 
                small_enhanced = apply_night_vision(small_frame)
            else: 
                small_enhanced = small_frame
    
            night_conf = max(0.20, conf - night_conf_offset) if night_mode else conf
            
            # Use specified device, or let Ultralytics auto-select if empty
            inference_kwargs = {"conf": night_conf, "verbose": False}
            if device: inference_kwargs["device"] = device
            
            results = model(small_enhanced, **inference_kwargs)[0]
    
            flame_detections = []
            if night_mode:
                # During or just after a flash, suppress MOG2 learning so the
                # background model isn't poisoned by the explosion-lit frame.
                # This prevents ground lights from appearing as 'new motion' once
                # the flash fades.
                mog_lr = 0.0 if suppressing_mog else -1
                flame_detections = flame_detector.detect(
                    small_enhanced, current_ground_frac,
                    proxy_bright_mask=None, mog_learning_rate=mog_lr
                )
                flame_detections = static_filter.filter(flame_detections, cam_x, cam_y)
    
            if display_filter == "thermal": 
                display = apply_thermal_display(frame)
            elif display_filter == "nvg" and night_mode: 
                display = apply_nvg_display(frame)
            else: 
                display = frame.copy()
                display_filter = "original" if display_filter == "nvg" else display_filter
    
            # Ground exclusion threshold in original-frame pixel coordinates
            ground_y_orig = int(h_orig * current_ground_frac)

            hits = []
            for box in results.boxes:
                label = class_names.get(int(box.cls[0]), f"cls")
                if is_missile_class(label):
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    # Scale to original frame coordinates
                    ox1 = int(round(x1 * scale_x))
                    oy1 = int(round(y1 * scale_y))
                    ox2 = int(round(x2 * scale_x))
                    oy2 = int(round(y2 * scale_y))
                    det_conf = float(box.conf[0])
                    # Two-zone confidence gate for YOLO (mirrors IR pipeline):
                    #   Above ground line → normal conf threshold (already pre-filtered by YOLO)
                    #   Below ground line → stricter yolo_below_ground_conf gate so
                    #     cars, buildings, and low-confidence shape hits near the ground
                    #     don't flood the tracker, while a genuine high-confidence
                    #     missile shape on the ground still gets through.
                    cy_box = (oy1 + oy2) // 2
                    if cy_box >= ground_y_orig:
                        if det_conf < yolo_below_ground_conf:
                            continue
                    hits.append({
                        "box": (ox1, oy1, ox2 - ox1, oy2 - oy1),
                        "label": label,
                        "confidence": det_conf,
                        "source": "yolo"
                    })
    
            for d in flame_detections:
                bx, by, bw, bh = d["box"]
                d["box"] = (int(round(bx*scale_x)), int(round(by*scale_y)),
                            int(round(bw*scale_x)), int(round(bh*scale_y)))
                # Apply the appropriate confidence gate:
                #   - Above ground exclusion line → normal flame_min_conf
                #   - Below ground exclusion line → stricter below_ground_conf
                #     (high-confidence IR only, e.g. very bright/large near-ground missile)
                min_conf = below_ground_conf if d.get("below_ground") else flame_min_conf
                if d["confidence"] >= min_conf:
                    hits.append(d)
    
            final_hits = []
            for h_det in sorted(hits, key=lambda x: -x["confidence"]):
                box = h_det["box"]
                duplicate = False
                for keep in final_hits:
                    k_box = keep["box"]
                    ix1, iy1 = max(box[0], k_box[0]), max(box[1], k_box[1])
                    ix2, iy2 = min(box[0]+box[2], k_box[0]+k_box[2]), min(box[1]+box[3], k_box[1]+k_box[3])
                    inter = max(0, ix2-ix1) * max(0, iy2-iy1)
                    
                    if inter > 0 and (inter / float(min(box[2]*box[3], k_box[2]*k_box[3]) + 1e-6)) > 0.85: duplicate = True
                    if math.hypot((box[0]+box[2]/2) - (k_box[0]+k_box[2]/2), (box[1]+box[3]/2) - (k_box[1]+k_box[3]/2)) < max(12.0*ui_sc, min(box[2], box[3]) * 0.40): duplicate = True
                
                if not duplicate: final_hits.append(h_det)
    
            active_hits = trail_yolo.update(final_hits)
            missile_count = len(active_hits)

            # Prune announced_tids so reused IDs can trigger a new lock-on sound
            active_tids = {h["tid"] for h in active_hits}
            announced_tids &= active_tids

            # --- TACTICAL AUDIO FEEDBACK SYSTEM ---
            if os.name == 'nt' and missile_count > 0:
                new_locks = [h for h in active_hits if h["tid"] not in announced_tids]
                
                if new_locks:
                    # INITIAL ACQUISITION (Triple-Rise Sequence)
                    for h in new_locks: announced_tids.add(h["tid"])
                    def lock_sound():
                        for freq in [1500, 2000, 2500]:
                            winsound.Beep(freq, 100)
                    threading.Thread(target=lock_sound, daemon=True).start()
                
                elif frame_idx % 15 == 0:
                    # CONTINUOUS TRACKING (Source-Dependent Pulses)
                    is_flame = any(h.get("source") == "flame" for h in active_hits)
                    
                    if is_flame:
                        # IR Detection: Low-pitch Blip (1300Hz)
                        threading.Thread(target=lambda: winsound.Beep(1300, 50), daemon=True).start()
                    else:
                        # YOLO Detection: Tactical Ping (1800Hz)
                        threading.Thread(target=lambda: winsound.Beep(1800, 80), daemon=True).start()
    
            for hit in active_hits:
                bx, by, bw, bh = hit["box"]
                # Determine if this target is inside the central HUD targeting ring
                h_fr, w_fr = display.shape[:2]
                ring_r = int(220 * ui_sc)
                cx_fr, cy_fr = w_fr // 2, h_fr // 2
                hit_cx = bx + bw // 2
                hit_cy = by + bh // 2
                target_in_ring = math.hypot(hit_cx - cx_fr, hit_cy - cy_fr) <= ring_r

                is_missile_hit = is_missile_class(hit.get("label", "")) or hit.get("source") == "flame"
                draw_detection(display, bx, by, bx+bw, by+bh, hit["label"], hit["confidence"],
                               is_missile_hit, night_mode, frame_idx, hit["tid"], ui_sc,
                               dx=hit.get("dx", 0.0), dy=hit.get("dy", 0.0),
                               source=hit["source"], in_ring=target_in_ring)
    
            trail_yolo.draw(display, night_mode, ui_sc)
    
            threat = "CLEAR" if missile_count == 0 else "CAUTION" if missile_count <= 3 else "CRITICAL" if missile_count <= 7 else "THREAT DETECTED"
    
            sys.stdout.write(f"\r[FPS: {fps:>5.1f}] | Target Hits: {missile_count}")
            sys.stdout.flush()
    
            if show_window:
                annotated = draw_hud(display, active_hits, fps, paused, night_mode, sensor_state, display_filter, frame_idx, brightness, threat, ui_sc, current_ground_frac, is_auto_ground)
                cv2.imshow("Iron Dome Missile Tracker v3", cv2.resize(annotated, (1280, 720)) if w_orig > 1920 else annotated)
            else:
                annotated = display
    
            if writer: writer.write(annotated)

    except Exception as e:
        print(f"\n[CRASH] System encountered an error: {e}")
        import traceback
        traceback.print_exc()

    print("\n[INFO] Video stream ended or aborted.")
    if show_window and annotated is not None:
        print("[INFO] Press any key on the video window to close...")
        cv2.putText(annotated, ">> END OF STREAM / PRESS ANY KEY TO EXIT <<", (100, 100), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imshow("Iron Dome Missile Tracker v3", cv2.resize(annotated, (1280, 720)) if w_orig > 1920 else annotated)
        cv2.waitKey(0)

    cap.release()
    if writer: writer.release()
    cv2.destroyAllWindows()


def parse_args():
    p = argparse.ArgumentParser()
    src = p.add_mutually_exclusive_group()
    src.add_argument("--video", "-v", metavar="PATH")
    src.add_argument("--cam",   "-c", type=int, default=0)
    p.add_argument("--weights",  "-w", default=DEFAULT_WEIGHTS)
    p.add_argument("--conf",     type=float, default=0.25)
    p.add_argument("--no-window", action="store_true")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--night", action="store_true")
    mode.add_argument("--day",   action="store_true")
    p.add_argument("--night-sensitivity", type=int, default=AUTO_NIGHT_THRESHOLD)
    p.add_argument("--save", action="store_true")
    p.add_argument("--bright-thresh", type=int, default=170)
    p.add_argument("--min-flame-area", type=int, default=2)
    p.add_argument("--max-flame-area", type=int, default=50000)
    p.add_argument("--edge-margin", type=float, default=0.06)
    p.add_argument("--max-aspect-ratio", type=float, default=5.0)
    p.add_argument("--ground-fraction", type=float, default=0.70)
    p.add_argument("--static-grid", type=int, default=30)
    p.add_argument("--static-world-thresh", type=int, default=8)
    p.add_argument("--static-cam-thresh", type=int, default=25)
    p.add_argument("--static-decay", type=int, default=12)
    p.add_argument("--trail-length", type=int, default=TRAIL_LENGTH)
    p.add_argument("--track-max-dist", type=int, default=80)
    p.add_argument("--track-confirm", type=int, default=3)
    p.add_argument("--track-missed", type=int, default=12)
    p.add_argument("--default-filter", choices=["thermal", "nvg", "original"], default="thermal")
    # IR detector - clustering
    p.add_argument("--cluster-radius",    type=int,   default=60,   help="Pixel radius for city-light cluster rejection")
    p.add_argument("--cluster-max-size",  type=int,   default=4,    help="Max neighbors before blob is rejected as city light")
    # IR detector - background subtractor
    p.add_argument("--mog-history",       type=int,   default=150,  help="MOG2 frame history length")
    p.add_argument("--mog-var-thresh",    type=int,   default=25,   help="MOG2 variance threshold")
    # Auto-horizon EMA
    p.add_argument("--auto-ground-alpha", type=float, default=0.25, help="EMA smoothing speed for auto ground exclusion (0=frozen, 1=instant)")
    # YOLO night confidence offset
    p.add_argument("--night-conf-offset", type=float, default=0.10, help="Confidence offset subtracted from --conf in night mode")
    # Camera motion detector
    p.add_argument("--cam-motion-thresh", type=float, default=0.03, help="Phase-correlation response threshold for camera motion detection")
    # IR flame confidence gate
    p.add_argument("--flame-min-conf",      type=float, default=0.35,  help="Min confidence for IR flame/dim-dot detection to be accepted")
    p.add_argument("--device",              type=str,   default="",    help="Device to run on (e.g., '0' for GPU, 'cpu' for CPU)")
    # --- Multi-target IR tracker stability ---
    p.add_argument("--track-coast",         type=int,   default=6,     help="Frames to dead-reckon (coast) a missed IR track before hiding its box (anti-blink)")
    p.add_argument("--track-vel-gate",      type=float, default=1.5,   help="Speed multiplier for Hungarian assignment gate (lower = tighter matching)")
    p.add_argument("--track-dir-penalty",   type=float, default=0.4,   help="Direction-reversal penalty strength (0=off, higher=stricter direction lock)")
    p.add_argument("--track-vel-alpha",     type=float, default=0.5,   help="Velocity EMA weight for new measurement (0=ignore new, 1=instant update)")
    p.add_argument("--track-coast-drift",   type=float, default=0.3,   help="Fraction of velocity applied per missed frame during coast (0=stay put, 1=full drift)")
    p.add_argument("--track-box-smooth",    type=float, default=0.4,   help="EMA alpha for displayed bounding-box smoothing (0=frozen, 1=raw/jittery)")
    p.add_argument("--trail-jump-mult",     type=float, default=2.5,   help="Trail discontinuity threshold as a multiple of track-max-dist (lower = stricter, prevents wire trails)")
    # --- Explosion / flash immunity ---
    p.add_argument("--flash-thresh",         type=float, default=1.6,   help="Brightness ratio (current / rolling avg) above which a frame is classified as an explosion flash")
    p.add_argument("--flash-cooldown",       type=int,   default=30,    help="Frames to suppress MOG2 learning after a flash ends (prevents ground-light false positives)")
    p.add_argument("--max-horizon-rise",     type=float, default=0.015, help="Max fractional change per frame the horizon can move UPWARD (prevents flash from spiking the exclusion line)")
    # --- Below-ground IR detection ---
    p.add_argument("--below-ground-conf",      type=float, default=0.75, help="Min IR confidence for detections BELOW the ground exclusion line (higher = stricter; 1.0 = disabled)")
    # --- Below-ground YOLO detection ---
    p.add_argument("--yolo-below-ground-conf", type=float, default=0.70, help="Min YOLO confidence for detections BELOW the ground exclusion line (higher = stricter; 1.0 = disabled)")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    run(source           = args.video if args.video else args.cam,
        weights          = args.weights,
        conf             = args.conf,
        show_window      = not args.no_window,
        force_night      = args.night,
        force_day        = args.day,
        night_sensitivity= args.night_sensitivity,
        save_output      = args.save,
        bright_thresh    = args.bright_thresh,
        min_flame_area   = args.min_flame_area,
        max_flame_area   = args.max_flame_area,
        edge_margin      = args.edge_margin,
        max_aspect_ratio = args.max_aspect_ratio,
        ground_fraction  = args.ground_fraction,
        static_grid      = args.static_grid,
        static_world_thresh = args.static_world_thresh,
        static_cam_thresh= args.static_cam_thresh,
        static_decay     = args.static_decay,
        trail_length     = args.trail_length,
        track_max_dist   = args.track_max_dist,
        track_confirm    = args.track_confirm,
        track_missed     = args.track_missed,
        default_filter   = args.default_filter,
        cluster_radius   = args.cluster_radius,
        cluster_max_size = args.cluster_max_size,
        mog_history      = args.mog_history,
        mog_var_thresh   = args.mog_var_thresh,
        auto_ground_alpha= args.auto_ground_alpha,
        night_conf_offset= args.night_conf_offset,
        cam_motion_thresh= args.cam_motion_thresh,
        flame_min_conf   = args.flame_min_conf,
        device           = args.device,
        track_coast      = args.track_coast,
        track_vel_gate   = args.track_vel_gate,
        track_dir_penalty= args.track_dir_penalty,
        track_vel_alpha  = args.track_vel_alpha,
        track_coast_drift= args.track_coast_drift,
        track_box_smooth = args.track_box_smooth,
        trail_jump_mult  = args.trail_jump_mult,
        flash_thresh         = args.flash_thresh,
        flash_cooldown_frames= args.flash_cooldown,
        max_horizon_rise     = args.max_horizon_rise,
        below_ground_conf        = args.below_ground_conf,
        yolo_below_ground_conf   = args.yolo_below_ground_conf,
    )
                
