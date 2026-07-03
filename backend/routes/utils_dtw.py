# backend/utils_dtw.py
from __future__ import annotations

import json
from uuid import uuid4
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
from tslearn.metrics import dtw_path
from storage_paths import DTW_RUNS_DIR, TEMPLATES_DIR

# ================== BASE PATHS ==================
TEMPLATES_ROOT = TEMPLATES_DIR
DTW_BASE = DTW_RUNS_DIR
TEMPLATES_ROOT.mkdir(parents=True, exist_ok=True)
DTW_BASE.mkdir(parents=True, exist_ok=True)

print(f"[DTW] TEMPLATES_ROOT = {TEMPLATES_ROOT}")
print(f"[DTW] DTW_BASE       = {DTW_BASE}")

# ================== NORMALIZATION / GUARDS ==================
ALLOWED_TESTS = {"stand-and-sit", "finger-tapping", "fist-open-close"}

_TEST_NORMALIZATION_ALIASES = {
    "stand-and-sit": "stand-and-sit",
    "stand-sit": "stand-and-sit",
    "stand_to_sit": "stand-and-sit",
    "stand-and-sit-assessment": "stand-and-sit",
    "stand-and-sit-test": "stand-and-sit",
    "stand-&-sit": "stand-and-sit",
    "stand-&-sit-assessment": "stand-and-sit",
    "stand-and-sit-evaluation": "stand-and-sit",
    "finger-tapping": "finger-tapping",
    "finger_tapping": "finger-tapping",
    "finger-taping": "finger-tapping",
    "finger-tapping-test": "finger-tapping",
    "finger-tapping-assessment": "finger-tapping",
    "finger-tap": "finger-tapping",
    "fist-open-close": "fist-open-close",
    "fist_open_close": "fist-open-close",
    "fist-open-close-test": "fist-open-close",
    "fist-open-close-assessment": "fist-open-close",
}

def normalize_test_name(t: str | None) -> str:
    t = (t or "").strip().lower()
    if not t:
        return ""
    t = t.replace(" ", "-").replace("_", "-")
    t = t.replace("&", "and")
    while "--" in t:
        t = t.replace("--", "-")
    return _TEST_NORMALIZATION_ALIASES.get(t, t)

def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def generate_session_id() -> str:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    sid = uuid4().hex[:8]
    return f"{ts}_{sid}"

# ================== TEMPLATES ==================
class TemplateLibrary:
    @staticmethod
    def load(test_name: str, model: str) -> np.ndarray:
        """Load reference template X (T_ref, D) from backend/data/templates/<test>/<model>.npz."""
        test_key = normalize_test_name(test_name)

        primary = TEMPLATES_ROOT / test_key / f"{model}.npz"

        if primary.exists():
            X = np.load(str(primary))["X"].astype(np.float32)
            if X.ndim != 2:
                raise ValueError(f"Template array must be 2D (T,D). Got {X.shape} at {primary}")
            print(f"[DTW] Using template: {primary}")
            return X

        raise FileNotFoundError(
            "Missing template file.\n"
            f"  looked for: {primary}\n"
            "Place template at backend/data/templates/<test>/<model>.npz with array 'X'."
        )

# ================== FEATURE EXTRACTION ==================
#Should either be positional scaled or statistically scaled
def _hands_features(kp: Dict) -> Optional[np.ndarray]:
    """
    Use ALL Mediapipe hand landmarks (21).
    - Origin: wrist (id 0)
    - Scale: distance wrist->middle MCP (id 9)
    - Output: flattened 42D vector (21*2)
    """
    hands = kp.get("hands", [])
    if not hands:
        return None
    lm = hands[0].get("landmarks", [])
    if len(lm) < 21:
        return None

    pts = np.array([[p["x"], p["y"]] for p in lm], dtype=np.float32)  # (21,2)
    ref = pts[0]                                  # wrist
    rel = pts - ref                               # translation-invariant
    scale = np.linalg.norm(pts[9] - ref) + 1e-6   # wrist->middle MCP
    return (rel / scale).reshape(-1)              # (42,)

def _pose_features(kp: Dict, use_z: bool = False) -> Optional[np.ndarray]:
    pose = kp.get("pose", [])
    if not pose or len(pose) < 33:
        return None
    if use_z:
        pts = np.array([[p["x"], p["y"], p.get("z", 0.0)] for p in pose], dtype=np.float32)  # (33,3)
        mid_hips = (pts[23] + pts[24]) / 2.0
        rel = pts - mid_hips
        shoulder_w = np.linalg.norm(pts[11] - pts[12]) + 1e-6
        return (rel / shoulder_w).reshape(-1)  # (99,)
    else:
        pts = np.array([[p["x"], p["y"]] for p in pose], dtype=np.float32)  # (33,2)
        mid_hips = (pts[23] + pts[24]) / 2.0
        rel = pts - mid_hips
        shoulder_w = np.linalg.norm(pts[11] - pts[12]) + 1e-6
        return (rel / shoulder_w).reshape(-1)  # (66,)

def _select_finger_features(kp_array: np.ndarray) -> np.ndarray:
    """Select only finger-related features from hand keypoints array."""
    # Hand landmarks indices for fingers (excluding wrist)
    finger_indices = [
       3, 4,    # Thumb
         7, 8,    # Index
    ]
    selected = []
    for idx in finger_indices:
        selected.extend([kp_array[idx * 2], kp_array[idx * 2 + 1]])  # x and y
    return np.array(selected, dtype=np.float32)

def extract_features(model: str, kp: Dict, use_z: bool = False) -> Optional[np.ndarray]:
    if model == "hands":
        return _hands_features(kp)
    if model == "pose":
        return _pose_features(kp, use_z=use_z)
    if model == "finger":
        kp = _hands_features(kp)
        kp = _select_finger_features(kp)
        return kp
    return None

#================== AMPLITUDE AND SPEED CALCULATION ==================
def calculate_amplitude(X: np.ndarray) -> np.ndarray:
    """Calculate amplitude (magnitude) of each feature vector in X."""
    return np.linalg.norm(X, axis=1)

def calculate_speed(X: np.ndarray) -> np.ndarray:
    """Calculate speed (first derivative) of feature vectors in X."""
    diffs = np.diff(X, axis=0, prepend=X[0:1, :])
    return np.linalg.norm(diffs, axis=1)


def _dtw_with_optional_sakoe(a, b, sakoe_radius: Optional[int]):
    if sakoe_radius is not None:
        path, total = dtw_path(
            a, b,
            global_constraint="sakoe_chiba",
            sakoe_chiba_radius=int(sakoe_radius),
        )
    else:
        path, total = dtw_path(a, b)
    return path, float(total)

def normalize_dtw(dtw: float, L_avg: float, R_data: float, eps: float = 1e-6) -> float:
    norm_scale = max(L_avg * max(R_data, eps), eps)

    return float(1.0 / (1.0 + dtw / norm_scale))
# ================== SAVE ARTIFACTS ==================
def save_dtw_npz(
    save_root: str | None,
    test_name: str,
    session_id: str,
    model: str,
    X_live: np.ndarray,
    Y_ref: np.ndarray,
    AX_live: np.ndarray,
    AY_ref: np.ndarray,
    SX_live: np.ndarray,
    SY_ref: np.ndarray,
    pos_path_pairs: List[Tuple[int, int]],
    pos_local_costs: np.ndarray,
    pos_aligned_ref_by_live: np.ndarray,
    amp_path_pairs: List[Tuple[int, int]],
    amp_local_costs: np.ndarray,
    amp_aligned_ref_by_live: np.ndarray,
    spd_path_pairs: List[Tuple[int, int]],
    spd_local_costs: np.ndarray,
    spd_aligned_ref_by_live: np.ndarray,
    meta: Dict,
) -> Dict:
    canonical = normalize_test_name(test_name)
    if canonical not in ALLOWED_TESTS:
        canonical = "stand-and-sit" if "sit" in (test_name or "") else \
                    "finger-tapping" if "finger" in (test_name or "") else "fist-open-close"

    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    folder = (DTW_BASE / canonical / session_id)
    _ensure_dir(folder)

    np.savez_compressed(
        folder / "dtw_artifacts.npz",
        X_live=X_live,
        Y_ref=Y_ref,
        AX_live=AX_live,
        AY_ref=AY_ref,
        SX_live=SX_live,
        SY_ref=SY_ref,
        pos_path=np.asarray(pos_path_pairs, dtype=np.int32),
        pos_local_costs=pos_local_costs.astype(np.float32),
        pos_aligned_ref_by_live=pos_aligned_ref_by_live.astype(np.int32),
        amp_path=np.asarray(amp_path_pairs, dtype=np.int32),
        amp_local_costs=amp_local_costs.astype(np.float32),
        amp_aligned_ref_by_live=amp_aligned_ref_by_live.astype(np.int32),
        spd_path=np.asarray(spd_path_pairs, dtype=np.int32),
        spd_local_costs=spd_local_costs.astype(np.float32),
        spd_aligned_ref_by_live=spd_aligned_ref_by_live.astype(np.int32),
    )

    meta_out = {
        "testName": canonical,
        "model": model,
        "created_utc": ts,
        "session_id": session_id,
        "live_len": int(len(X_live)),
        "ref_len": int(len(Y_ref)),
        "dim": int(X_live.shape[1]),
        **meta,
    }
    (folder / "meta.json").write_text(json.dumps(meta_out, indent=2))

    print(f"[DTW] saved -> {folder}")

    return {
        "dir": str(folder),
        "npz": str(folder / "dtw_artifacts.npz"),
        "json": str(folder / "meta.json"),
        "test_name": canonical,
        "session_id": session_id,
        "created_utc": ts,
    }

# ================== END-ONLY DTW ==================
class EndOnlyDTW:
    def __init__(self, test_name: str, model: str,  session_id: Optional[str] = None, use_z: bool = False,
                 sakoe_radius: Union[int, str, None] = None):
        self.test_name = normalize_test_name(test_name)
        self.model = model
        self.use_z = use_z
        self.buf: List[np.ndarray] = []
        self._pushed_frames = 0
        self._pushed_feats = 0
        self._pushed_drops = 0
        self.session_id = session_id or generate_session_id()
        try:
            self.X_ref = TemplateLibrary.load(self.test_name, model)  # (T_ref, D)
            self.init_error = None
        except Exception as e:
            self.X_ref = None
            self.init_error = f"Template load failed: {e}"
        if sakoe_radius == "auto":
            self.sakoe_radius: Optional[int] = max(1, int(0.10 * (len(self.X_ref) if self.X_ref is not None else 1)))
        elif isinstance(sakoe_radius, int):
            self.sakoe_radius = max(1, sakoe_radius)
        else:
            self.sakoe_radius = None

    def push(self, kp: Dict):
        self._pushed_frames += 1
        feat = extract_features(self.model, kp, use_z=self.use_z)
        if feat is not None:
            self.buf.append(feat)
            self._pushed_feats += 1
        else:
            self._pushed_drops += 1

    #Changing this to return save speed dtw, amplitude, and positional dtw
    def finalize_and_save(self, meta_sidecar: Dict) -> Dict:
        if self.init_error:
            return {"ok": False, "where": "init", "message": self.init_error}

        if not self.buf or self.X_ref is None:
            return {
                "ok": False,
                "where": "finalize",
                "message": "No features or template missing",
                "frames_seen": self._pushed_frames,
                "features_built": len(self.buf),
                "feature_drops": self._pushed_drops,
            }

        X = np.stack(self.buf, axis=0).astype(np.float32)   # (T_live, D)
        Y = self.X_ref.astype(np.float32)                   # (T_ref, D)

        if X.shape[1] != Y.shape[1]:
            return {
                "ok": False,
                "where": "finalize",
                "message": f"Dim mismatch: live D={X.shape[1]} vs ref D={Y.shape[1]}",
            }

        # ---------- AMPLITUDE ----------
        AX = calculate_amplitude(X)  # (T_live,)
        AY = calculate_amplitude(Y)  # (T_ref,)

        amp_path, amp_total = _dtw_with_optional_sakoe(AX, AY, self.sakoe_radius)
        R_amp = float(AY.max() - AY.min())
        L_amp = 0.5 * (len(AX) + len(AY))

        S_amp = amp_total

        amp_local_costs = np.fromiter(
            (abs(AX[i] - AY[j]) for (i, j) in amp_path),
            dtype=np.float32,
            count=len(amp_path),
        )
        amp_aligned_ref_by_live = np.full(len(AX), -1, dtype=int)
        for i, j in amp_path:
            amp_aligned_ref_by_live[i] = j

        # ---------- SPEED ----------
        SX = calculate_speed(X)  # (T_live-1,)
        SY = calculate_speed(Y)  # (T_ref-1,)

        if len(SX) > 0 and len(SY) > 0:
            s_path, s_total = _dtw_with_optional_sakoe(SX, SY, self.sakoe_radius)
            R_spd = float(SY.max() - SY.min())
            L_spd = 0.5 * (len(SX) + len(SY))
            S_spd = s_total

            spd_local_costs = np.fromiter(
                (abs(SX[i] - SY[j]) for (i, j) in s_path),
                dtype=np.float32,
                count=len(s_path),
            )
            spd_aligned_ref_by_live = np.full(len(SX), -1, dtype=int)
            for i, j in s_path:
                spd_aligned_ref_by_live[i] = j
        else:
            s_path, s_total = [], 0.0
            R_spd, L_spd, S_spd = 0.0, max(len(SX), len(SY), 1), 1.0
            spd_local_costs = np.zeros(0, dtype=np.float32)
            spd_aligned_ref_by_live = np.full(len(SX), -1, dtype=int)

        # ---------- POSITION ----------
        pos_path, pos_total = _dtw_with_optional_sakoe(X, Y, self.sakoe_radius)

        pos_local_costs = np.fromiter(
            (np.linalg.norm(X[i] - Y[j]) for (i, j) in pos_path),
            dtype=np.float32,
            count=len(pos_path),
        )
        pos_aligned_ref_by_live = np.full(len(X), -1, dtype=int)
        for i, j in pos_path:
            pos_aligned_ref_by_live[i] = j

        R_pos = float((Y.max(axis=0) - Y.min(axis=0)).max())
        L_pos = 0.5 * (len(X) + len(Y))

        S_pos = pos_total

        # ---------- COMBINED SCORE ----------
        S_overall = (S_pos + S_amp + S_spd) / 3.0
        avg_step_pos = float(pos_total / max(1, len(pos_path)))

        save_result = save_dtw_npz(
            save_root=None,
            test_name=self.test_name,
            session_id=self.session_id,
            model=self.model,
            X_live=X,
            Y_ref=Y,
            AX_live=AX,
            AY_ref=AY,
            SX_live=SX,
            SY_ref=SY,
            pos_path_pairs=pos_path,
            pos_local_costs=pos_local_costs,
            pos_aligned_ref_by_live=pos_aligned_ref_by_live,
            amp_path_pairs=amp_path,
            amp_local_costs=amp_local_costs,
            amp_aligned_ref_by_live=amp_aligned_ref_by_live,
            spd_path_pairs=s_path,
            spd_local_costs=spd_local_costs,
            spd_aligned_ref_by_live=spd_aligned_ref_by_live,
            meta={
                "pos_dtw": pos_total,
                "amp_dtw": amp_total,
                "spd_dtw": s_total,
                "R_pos": R_pos,
                "R_amp": R_amp,
                "R_spd": R_spd,
                "L_pos": L_pos,
                "L_amp": L_amp,
                "L_spd": L_spd,
                "similarity_pos": S_pos,
                "similarity_amp": S_amp,
                "similarity_spd": S_spd,
                "similarity_overall": S_overall,
                "avg_step_pos": avg_step_pos,
                **meta_sidecar,
            },
        )

        print(
            f"[DTW] ok save | test={self.test_name} model={self.model} "
            f"frames={self._pushed_frames} feats={self._pushed_feats} "
            f"path_len={len(pos_path)} S_overall={S_overall:.4f}"
        )

        return {
            "ok": True,
            "session_id": self.session_id,
            "artifacts": save_result,
            "similarity_overall": S_overall,
            "similarity_pos": S_pos,
            "similarity_amp": S_amp,
            "similarity_spd": S_spd,
            "distance": pos_total,
            "avg_step_cost": avg_step_pos,
        }
