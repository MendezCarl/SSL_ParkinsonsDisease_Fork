# backend/utils_dtw.py
from __future__ import annotations

import json
from uuid import uuid4
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
from tslearn.metrics import dtw_path

# ================== BASE PATHS (match your repo layout) ==================
PROJECT_BACKEND = Path(__file__).resolve().parent               # .../project/backend
TEMPLATES_ROOT  = (PROJECT_BACKEND / "templates").resolve()     # .../backend/templates
DTW_BASE        = (PROJECT_BACKEND / "dtw_runs").resolve()      # .../backend/dtw_runs
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

# ================== TEMPLATES ==================
class TemplateLibrary:
    @staticmethod
    def load(test_name: str, model: str) -> np.ndarray:
        """Load reference template X (T_ref, D) from backend/templates/<test>/<model>.npz."""
        test_key = normalize_test_name(test_name)

        primary  = TEMPLATES_ROOT / test_key / f"{model}.npz"
        fallback = Path.cwd() / "backend" / "templates" / test_key / f"{model}.npz"  # extra dev convenience

        for p in (primary, fallback):
            if p.exists():
                X = np.load(str(p))["X"].astype(np.float32)
                if X.ndim != 2:
                    raise ValueError(f"Template array must be 2D (T,D). Got {X.shape} at {p}")
                print(f"[DTW] Using template: {p}")
                return X

        raise FileNotFoundError(
            "Missing template file.\n"
            f"  looked for: {primary}\n"
            f"  and also : {fallback}\n"
            "Place template at backend/templates/<test>/<model>.npz with array 'X'."
        )

# ================== FEATURE EXTRACTION ==================
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

def extract_features(model: str, kp: Dict, use_z: bool = False) -> Optional[np.ndarray]:
    if model == "hands":
        return _hands_features(kp)
    if model == "pose":
        return _pose_features(kp, use_z=use_z)
    return None

# ================== SAVE ARTIFACTS ==================
def save_dtw_npz(
    save_root: str | None,
    test_name: str,
    test_id: str,
    model: str,
    X_live: np.ndarray,
    Y_ref: np.ndarray,
    path_pairs: List[Tuple[int, int]],
    local_costs: np.ndarray,
    aligned_ref_by_live: np.ndarray,
    meta: Dict
) -> Dict:
    canonical = normalize_test_name(test_name)
    if canonical not in ALLOWED_TESTS:
        canonical = "stand-and-sit" if "sit" in (test_name or "") else \
                    "finger-tapping" if "finger" in (test_name or "") else "fist-open-close"

    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    sid = uuid4().hex[:8]
    session_id = f"{ts}_{sid}"
    folder = (DTW_BASE / canonical / test_id)
    _ensure_dir(folder)

    np.savez_compressed(
        folder / "dtw_artifacts.npz",
        X_live=X_live,
        Y_ref=Y_ref,
        path=np.asarray(path_pairs, dtype=np.int32),
        local_costs=local_costs.astype(np.float32),
        aligned_ref_by_live=aligned_ref_by_live.astype(np.int32),
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
    def __init__(self, test_name: str, model: str,  test_id: Optional[str] = None, use_z: bool = False,
                 sakoe_radius: Union[int, str, None] = None):
        self.test_name = normalize_test_name(test_name)
        self.model = model
        self.use_z = use_z
        self.buf: List[np.ndarray] = []
        self._pushed_frames = 0
        self._pushed_feats = 0
        self._pushed_drops = 0
        self.test_id = test_id
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
            return {"ok": False, "where": "finalize",
                    "message": f"Dim mismatch: live D={X.shape[1]} vs ref D={Y.shape[1]}"}

        if self.sakoe_radius is None:
            path, total = dtw_path(X, Y)
        else:
            path, total = dtw_path(X, Y, global_constraint="sakoe_chiba",
                                   sakoe_chiba_radius=int(self.sakoe_radius))

        local_costs = np.fromiter((np.linalg.norm(X[i] - Y[j]) for (i, j) in path),
                                  dtype=np.float32, count=len(path))
        aligned_ref_by_live = np.full(len(X), -1, dtype=int)
        for i, j in path:
            aligned_ref_by_live[i] = j

        avg_step = float(total / max(1, len(path)))
        similarity = float(np.exp(-avg_step))

        artifacts = save_dtw_npz(
            save_root=None,
            test_name=self.test_name,
            test_id = self.test_id,
            model=self.model,
            X_live=X, Y_ref=Y,
            path_pairs=path,
            local_costs=local_costs,
            aligned_ref_by_live=aligned_ref_by_live,
            meta={"distance": float(total), "avg_step_cost": avg_step,
                  "similarity": similarity, **meta_sidecar}
        )

        print(f"[DTW] ok save | test={self.test_name} model={self.model} "
              f"frames={self._pushed_frames} feats={self._pushed_feats} path_len={len(path)}")

        return {
            "ok": True,
            "distance": float(total),
            "avg_step_cost": avg_step,
            "similarity": similarity,
            "live_len": int(len(X)),
            "ref_len": int(len(Y)),
            "frames_seen": self._pushed_frames,
            "features_built": len(self.buf),
            "artifacts": artifacts,
            "test_name": artifacts["test_name"],
            "session_id": artifacts["session_id"],
        }
