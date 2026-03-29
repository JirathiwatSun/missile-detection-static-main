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

THREAT_CLEAR   = (0, 220, 60)
THREAT_CAUTION = (0, 180, 255)
THREAT_ALERT   = (0, 0, 255)


# ─────────────────────────────────────────────────────────────────────────────
# Night Flame Detector
# ─────────────────────────────────────────────────────────────────────────────

class NightFlameDetector:
    def __init__(self, bright_thresh: int = 170, 
                 min_area_px: int = 2,
                 max_area_px: int = 50000,
                 edge_margin_frac: float = 0.06,
                 max_aspect_ratio: float = 5.0,
                 ground_y_frac: float = 0.70):
        self.bright_thresh      = bright_thresh
        self.min_area           = min_area_px
        self.max_area           = max_area_px
        self.edge_margin_frac   = edge_margin_frac   
        self.max_aspect_ratio   = max_aspect_ratio   
        self.ground_y_frac      = ground_y_frac
        self.cluster_radius     = 60  
        self.max_cluster_size   = 4   
        
        self.bg_subtractor      = cv2.createBackgroundSubtractorMOG2(history=150, varThreshold=25, detectShadows=False)

    def detect(self, small_frame, current_ground_frac, proxy_bright_mask=None) -> list[dict]:
        h_fr, w_fr = small_frame.shape[:2]
        mg = int(self.edge_margin_frac * min(h_fr, w_fr))
        
        if proxy_bright_mask is not None:
            bright_mask = proxy_bright_mask
        else:
            small_gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
            _, bright_mask = cv2.threshold(small_gray, self.bright_thresh, 255, cv2.THRESH_BINARY)

        motion_mask = self.bg_subtractor.apply(small_frame)
        _, motion_mask = cv2.threshold(motion_mask, 127, 255, cv2.THRESH_BINARY)

        flow_mask = cv2.bitwise_and(bright_mask, motion_mask)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        flow_mask = cv2.dilate(flow_mask, kernel, iterations=1)
        flow_mask = cv2.morphologyEx(flow_mask, cv2.MORPH_CLOSE, kernel)

        num_labels, _, stats, centroids = cv2.connectedComponentsWithStats(flow_mask, connectivity=8)

        raw_detections = []
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < self.min_area or area > self.max_area:
                continue

            bx = stats[i, cv2.CC_STAT_LEFT]
            by = stats[i, cv2.CC_STAT_TOP]
            bw = stats[i, cv2.CC_STAT_WIDTH]
            bh = stats[i, cv2.CC_STAT_HEIGHT]
            cx, cy = centroids[i][0], centroids[i][1]

            ground_y = int(h_fr * current_ground_frac)
            if cx < mg or cx > w_fr - mg or cy < mg or cy > ground_y:
                continue

            if bh > 0 and bw > 0:
                aspect = max(bw, bh) / min(bw, bh)
                if aspect > self.max_aspect_ratio:
                    continue
                extent = area / (bw * bh)
                if extent < 0.25: 
                    continue

            raw_detections.append({
                "cx": cx, "cy": cy,
                "box": (bx, by, bw, bh),
                "area": area
            })

        filtered_detections = []
        for d in raw_detections:
            neighbors = sum(1 for other in raw_detections 
                            if math.hypot(d["cx"] - other["cx"], d["cy"] - other["cy"]) < self.cluster_radius)
            
            if neighbors <= self.max_cluster_size:
                pad = 6
                bx, by, bw, bh = d["box"]
                bx, by = max(0, bx - pad), max(0, by - pad)
                bw, bh = bw + pad * 2, bh + pad * 2
                
                confidence = min(0.99, 0.40 + (d["area"] / self.max_area) * 0.10)
                filtered_detections.append({
                    "label": "Missile",
                    "confidence": confidence,
                    "box": (bx, by, bw, bh),
                    "source": "flame",
                })

        return filtered_detections

    def reset(self):
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=150, varThreshold=25, detectShadows=False)


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
# AI Enhancement & Night-Vision Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def enhance_proxy_for_ai(frame):
    # 1. Bilateral filtering (Preserves edges, removes haze/noise)
    denoised = cv2.bilateralFilter(frame, 5, 60, 60)
    
    # 2. Subtle Laplacian Sharpening
    kernel = np.array([[ 0, -0.5,  0],
                       [-0.5,  3.0, -0.5],
                       [ 0, -0.5,  0]])
    sharpened = cv2.filter2D(denoised, -1, kernel)
    
    # 3. Dynamic Range Optimization (CLAHE)
    lab = cv2.cvtColor(sharpened, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l_eq = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l_eq, a, b)), cv2.COLOR_LAB2BGR)


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
    def __init__(self, maxlen=TRAIL_LENGTH, confirm_frames=3, max_dist=80, max_missed=12):
        self._trails: dict[int, collections.deque] = {}
        self._missed: dict[int, int] = {}
        self._hits: dict[int, int] = {}
        self._last_hit: dict[int, dict] = {}
        self._box_history: dict[int, collections.deque] = {}
        self._velocities: dict[int, tuple[float, float]] = {}  
        self._maxlen  = maxlen
        self._next_id = 1 
        self._confirm_frames = confirm_frames
        self._max_dist = max_dist
        self._max_missed = max_missed

    def update(self, hits: list[dict]) -> list[dict]:
        tids = list(self._trails.keys())
        num_targets = len(tids)
        num_hits = len(hits)
        matched_hits = set()
        matched_tids = set()

        if num_targets > 0 and num_hits > 0:
            cost_matrix = np.zeros((num_targets, num_hits))
            for i, tid in enumerate(tids):
                lx, ly, _ = self._trails[tid][-1]
                dx, dy = self._velocities.get(tid, (0.0, 0.0))
                px, py = lx + dx, ly + dy
                for j, hit in enumerate(hits):
                    bx, by, bw, bh = hit["box"]
                    cx, cy = bx + bw // 2, by + bh // 2
                    cost_matrix[i, j] = math.hypot(cx - px, cy - py)

            t_indices, h_indices = linear_sum_assignment(cost_matrix)
            for t_idx, h_idx in zip(t_indices, h_indices):
                dist = cost_matrix[t_idx, h_idx]
                if dist < self._max_dist:
                    tid, hit = tids[t_idx], hits[h_idx]
                    matched_hits.add(h_idx)
                    matched_tids.add(tid)
                    bx, by, bw, bh = hit["box"]
                    cx, cy = bx + bw // 2, by + bh // 2
                    lx, ly, _ = self._trails[tid][-1]
                    # Calculate velocity for smoothing/prediction
                    new_dx, new_dy = cx - lx, cy - ly
                    prev_dx, prev_dy = self._velocities.get(tid, (new_dx, new_dy))
                    self._velocities[tid] = (0.7*new_dx + 0.3*prev_dx, 0.7*new_dy + 0.3*prev_dy)
                    
                    # Store center and source size (avg of dw, dh)
                    src_size = (bw + bh) / 2.0
                    self._trails[tid].append((cx, cy, src_size))
                    self._box_history[tid].append(hit["box"])
                    self._missed[tid] = 0
                    self._hits[tid] += 1
                    self._last_hit[tid] = hit
                    hit["tid"] = tid

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
                self._last_hit[tid] = hit
                hit["tid"] = tid
                matched_tids.add(tid)

        active_tracked = []
        for tid in list(self._trails.keys()):
            if tid in matched_tids:
                if self._hits[tid] >= self._confirm_frames:
                    hist = self._box_history[tid]
                    current_box = hist[-1]
                    hit = self._last_hit[tid].copy()
                    hit["box"] = tuple(int(round(x)) for x in current_box)
                    hit["dx"], hit["dy"] = self._velocities.get(tid, (0.0, 0.0))
                    active_tracked.append(hit)
            else:
                self._missed[tid] += 1
                if self._missed[tid] > self._max_missed: 
                    del self._trails[tid]
                    del self._missed[tid]
                    del self._hits[tid]
                    del self._last_hit[tid]
                    del self._box_history[tid]
                    if tid in self._velocities: del self._velocities[tid]
        return active_tracked

    def draw(self, frame, night_mode: bool, ui_scale: float):
        for dq in self._trails.values():
            pts = list(dq)
            if len(pts) < 2: continue
            
            trail_len = len(pts)
            for i in range(1, trail_len):
                x1, y1, s1 = pts[i-1]
                x2, y2, s2 = pts[i]
                
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
                    # Blend base color with glow color
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
                   tid: int, ui_scale: float, dx: float = 0.0, dy: float = 0.0, source: str = "yolo"):
    
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

    # 1. Fighter Jet Target Brackets (Adaptive Dynamics)
    bw, bh = x2 - x1, y2 - y1
    
    # Differentiate minimum corner size based on detection source
    if is_missile and source == "yolo":
        # YOLO Missile: Larger minimum corner for daylight optics
        cl = max(int(min(bw, bh) * 0.25), max(18, int(12 * ui_scale)))
    else:
        # IR/Flame: Smaller, more precise minimum corner for exhaust tracking
        cl = max(int(min(bw, bh) * 0.25), max(8, int(6 * ui_scale)))

    for sx, sy, dir_x, dir_y in [(x1,y1,1,1),(x2,y1,-1,1),(x1,y2,1,-1),(x2,y2,-1,-1)]:
        cv2.line(frame, (sx, sy), (sx + dir_x*cl, sy), colour, lw_bold, cv2.LINE_AA)
        cv2.line(frame, (sx, sy), (sx, sy + dir_y*cl), colour, lw_bold, cv2.LINE_AA)

    cx_m, cy_m = (x1 + x2) // 2, (y1 + y2) // 2
    
    # 2. Center Targeting Dot (Increased for visibility)
    cv2.circle(frame, (cx_m, cy_m), int(3 * ui_scale), colour, -1, cv2.LINE_AA)

    # 3. Predictive Lead Indicator
    if abs(dx) > 0.5 or abs(dy) > 0.5:
        lead_frames = 15  
        lead_x = int(cx_m + dx * lead_frames)
        lead_y = int(cy_m + dy * lead_frames)
        
        cv2.line(frame, (cx_m, cy_m), (lead_x, lead_y), dim_c, lw_fine, cv2.LINE_AA)
        cv2.drawMarker(frame, (lead_x, lead_y), colour, cv2.MARKER_DIAMOND, int(10*ui_scale), lw_fine, cv2.LINE_AA)

    # 4. Lock-on Reticle (Double-Circle Design)
    if is_missile or source == "flame":
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

    # 5. Military Telemetry Block
    tgt_id = f"TARGET-{tid:03d}"
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
             night_mode: bool, display_filter: str,
             frame_idx: int, brightness: float, threat_level: str, 
             ui_scale: float, ground_frac: float):
    
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
    cv2.putText(frame, f"GROUND EXCLUSION [{ground_frac:.2f}]", 
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
    mode_text = "NIGHT SCAN" if night_mode else "DAY OPTICS"
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

    if threat_level == "CLEAR": tc = THREAT_CLEAR
    elif threat_level == "CAUTION": tc = THREAT_CAUTION if (frame_idx // 15) % 2 == 0 else (0, 100, 180)
    else: tc = THREAT_ALERT if (frame_idx // 8) % 2 == 0 else (0, 0, 150)

    # Increased box size and text scale for critical alerts
    threat_f = 0.55 * ui_scale
    cv2.rectangle(frame, (10, h-b_height+10), (int(250*ui_scale), h-10), tc, -1)
    cv2.putText(frame, f"THREAT: {threat_level}", (20, h-int(20*ui_scale)), cv2.FONT_HERSHEY_SIMPLEX, threat_f, (0,0,0), font_th_bold, cv2.LINE_AA)

    missile_count = len(active_hits)
    count_c = (NIGHT_COLOUR_MISSILE if night_mode else DAY_COLOUR_MISSILE) if missile_count > 0 else dim_c
    cv2.putText(frame, f"ACTIVE MISSILE TRACKED: {missile_count:02d}", (int(270*ui_scale), h-int(20*ui_scale)), cv2.FONT_HERSHEY_SIMPLEX, threat_f, count_c, font_th_bold, cv2.LINE_AA)

    shortcuts = "[Q] ABORT  [P] HALT  [N] OPTICS  [F] FILTER  [W/S] HORIZON  [C] CAPTURE"
    font_scale = 0.50 * ui_scale
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

# ─────────────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────────────

def run(source, weights: str, conf: float, show_window: bool,
        force_night: bool, force_day: bool, night_sensitivity: int, save_output: bool,
        bright_thresh: int, min_flame_area: int, max_flame_area: int, edge_margin: float,
        max_aspect_ratio: float, ground_fraction: float, static_grid: int, static_world_thresh: int,
        static_cam_thresh: int, static_decay: int, trail_length: int, track_max_dist: int,
        track_confirm: int, track_missed: int, default_filter: str) -> None:

    try: from ultralytics import YOLO
    except ImportError: sys.exit("[ERROR] ultralytics not installed.")

    print(f"[INFO] Loading YOLO model: {weights} ...", end=" ", flush=True)
    model = YOLO(weights)
    print("OK")

    flame_detector = NightFlameDetector(bright_thresh, min_flame_area, max_flame_area, edge_margin, max_aspect_ratio, ground_fraction)
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
    
    current_ground_frac = ground_fraction

    print(f"[INFO] Active Source     : {source}")
    print(f"[INFO] Native Resolution : {native_w}x{native_h}")
    
    writer = None
    if save_output:
        fps_src = cap.get(cv2.CAP_PROP_FPS) or 30
        out_path = os.path.join(BASE_DIR, "output_tracked.mp4")
        writer   = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps_src, (native_w, native_h))

    trail_yolo  = MissileTrail(maxlen=trail_length, confirm_frames=track_confirm, max_dist=track_max_dist, max_missed=track_missed) 

    frame_idx, fps = 0, 0.0
    paused, night_mode, manual_night_override = False, force_night, None
    display_filter = default_filter 
    prev_time = time.perf_counter()
    prev_gray_small = None
    cam_x, cam_y = 0.0, 0.0

    if not (isinstance(source, int) or str(source).isdigit()):
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    try:
        while True:
            key = cv2.waitKey(1) & 0xFF if show_window else 0xFF
            if key == ord("q"): break
            if key == ord("p"): paused = not paused
            if key == ord("n"):
                night_mode = not night_mode
                manual_night_override = night_mode
                flame_detector.reset()
                static_filter.reset()
                if not night_mode and display_filter == "nvg":
                    display_filter = "original"
            if key == ord("f"):
                filters = ["thermal", "nvg", "original"] if night_mode else ["thermal", "original"]
                idx = (filters.index(display_filter) + 1) % len(filters) if display_filter in filters else 0
                display_filter = filters[idx]
                
            if key == ord("w"): current_ground_frac = max(0.1, current_ground_frac - 0.05)
            if key == ord("s"): current_ground_frac = min(1.0, current_ground_frac + 0.05)
            if key == ord("c") and 'annotated' in locals() and annotated is not None:
                p = os.path.join(BASE_DIR, f"screenshot_{int(time.time())}.png")
                cv2.imwrite(p, annotated)
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
            if manual_night_override is not None: night_mode = manual_night_override
            elif not force_night and not force_day: night_mode = brightness < night_sensitivity
    
            if night_mode:
                native_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                _, native_bright = cv2.threshold(native_gray, bright_thresh, 255, cv2.THRESH_BINARY)
                star_kernel = np.ones((7, 7), np.uint8)
                native_bright = cv2.dilate(native_bright, star_kernel, iterations=1)
                proxy_bright_mask = cv2.resize(native_bright, (proc_w, proc_h), interpolation=cv2.INTER_NEAREST)
            else:
                proxy_bright_mask = None
    
            gray_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
            if prev_gray_small is not None:
                shift, response = cv2.phaseCorrelate(np.float32(prev_gray_small), np.float32(gray_small))
                if response > 0.03: 
                    cam_x -= shift[0]
                    cam_y -= shift[1]
            prev_gray_small = gray_small
    
            frame_idx += 1
            now = time.perf_counter()
            fps = 1.0 / (now - prev_time) if (now - prev_time) > 0 else 0.0
            prev_time = now
    
            if night_mode: 
                small_enhanced = apply_night_vision(small_frame)
            else: 
                small_enhanced = enhance_proxy_for_ai(small_frame)
    
            night_conf = max(0.20, conf - 0.10) if night_mode else conf
            results = model(small_enhanced, conf=night_conf, verbose=False)[0]
    
            flame_detections = []
            if night_mode:
                flame_detections = flame_detector.detect(small_frame, current_ground_frac, proxy_bright_mask)
                flame_detections = static_filter.filter(flame_detections, cam_x, cam_y)
    
            if display_filter == "thermal": 
                display = apply_thermal_display(frame)
            elif display_filter == "nvg" and night_mode: 
                display = apply_nvg_display(frame)
            else: 
                display = frame.copy()
                display_filter = "original" if display_filter == "nvg" else display_filter
    
            hits = []
            for box in results.boxes:
                label = class_names.get(int(box.cls[0]), f"cls")
                if is_missile_class(label):
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    hits.append({
                        "box": (int(round(x1*scale_x)), int(round(y1*scale_y)), 
                                int(round((x2-x1)*scale_x)), int(round((y2-y1)*scale_y))),
                        "label": label,
                        "confidence": float(box.conf[0]),
                        "source": "yolo"
                    })
    
            for d in flame_detections:
                if d["confidence"] >= 0.35:
                    bx, by, bw, bh = d["box"]
                    d["box"] = (int(round(bx*scale_x)), int(round(by*scale_y)), 
                                int(round(bw*scale_x)), int(round(bh*scale_y)))
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
    
            for hit in active_hits:
                bx, by, bw, bh = hit["box"]
                draw_detection(display, bx, by, bx+bw, by+bh, hit["label"], hit["confidence"],
                               True, night_mode, frame_idx, hit["tid"], ui_sc, 
                               dx=hit.get("dx", 0.0), dy=hit.get("dy", 0.0), source=hit["source"])
    
            trail_yolo.draw(display, night_mode, ui_sc)
    
            threat = "CLEAR" if missile_count == 0 else "CAUTION" if missile_count <= 2 else "THREAT DETECTED"
    
            sys.stdout.write(f"\r[FPS: {fps:>5.1f}] | Target Hits: {missile_count}")
            sys.stdout.flush()
    
            if show_window:
                annotated = draw_hud(display, active_hits, fps, paused, night_mode, display_filter, frame_idx, brightness, threat, ui_sc, current_ground_frac)
                cv2.imshow("Iron Dome Missile Tracker v3", cv2.resize(annotated, (1280, 720)) if w_orig > 1920 else annotated)
            else:
                annotated = display
    
            if writer: writer.write(annotated)

    except Exception as e:
        print(f"\n[CRASH] System encountered an error: {e}")
        import traceback
        traceback.print_exc()

    print("\n[INFO] Video stream ended or aborted.")
    if show_window:
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
    return p.parse_args()

if __name__ == "__main__":
    args   = parse_args()
    run(source=args.video 
        if args.video 
            else args.cam, 
                weights =   args.weights, 
                conf    =   args.conf,
                show_window = not args.no_window, 
                force_night = args.night, 
                force_day   = args.day,
                night_sensitivity = args.night_sensitivity, 
                save_output = args.save, 
                bright_thresh = args.bright_thresh, 
                min_flame_area = args.min_flame_area, 
                max_flame_area = args.max_flame_area, 
                edge_margin = args.edge_margin,
                max_aspect_ratio = args.max_aspect_ratio, 
                ground_fraction = args.ground_fraction, 
                static_grid     = args.static_grid,
                static_world_thresh = args.static_world_thresh, 
                static_cam_thresh = args.static_cam_thresh,
                static_decay = args.static_decay, 
                trail_length = args.trail_length, 
                track_max_dist = args.track_max_dist,
                track_confirm    = args.track_confirm, 
                track_missed    = args.track_missed, 
                default_filter  = args.default_filter)
                

