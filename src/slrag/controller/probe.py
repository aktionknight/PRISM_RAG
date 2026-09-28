import json
import logging
from pathlib import Path
from typing import Optional, Any
import numpy as np

from slrag.core.schemas import ControllerDecision, ControllerReason
from slrag.core.config import get_controller_config

logger = logging.getLogger(__name__)

_BM25_INSTANCE = None
_CALIBRATION_CACHE = None
_BM25_LOAD_ATTEMPTED = False


def reset_probe_cache() -> None:
    """Clear cached BM25 instance and calibration data."""
    global _BM25_INSTANCE, _CALIBRATION_CACHE, _BM25_LOAD_ATTEMPTED
    _BM25_INSTANCE = None
    _CALIBRATION_CACHE = None
    _BM25_LOAD_ATTEMPTED = False


def _load_bm25_probe():
    global _BM25_INSTANCE, _BM25_LOAD_ATTEMPTED
    if _BM25_LOAD_ATTEMPTED:
        return _BM25_INSTANCE
    _BM25_LOAD_ATTEMPTED = True
    try:
        import bm25s
        bm25_path = Path(".index/bm25")
        if bm25_path.exists():
            _BM25_INSTANCE = bm25s.BM25.load(str(bm25_path))
            logger.info("Loaded BM25 index for Controller Stage 2 probe")
    except Exception as e:
        logger.warning(f"Failed loading BM25 index for probe: {e}")
        _BM25_INSTANCE = None
    return _BM25_INSTANCE


def _load_calibration() -> dict:
    global _CALIBRATION_CACHE
    if _CALIBRATION_CACHE is not None:
        return _CALIBRATION_CACHE
    calib_file = Path(".index/probe_calibration.json")
    if calib_file.exists():
        try:
            with open(calib_file, "r", encoding="utf-8") as f:
                _CALIBRATION_CACHE = json.load(f)
                return _CALIBRATION_CACHE
        except Exception as e:
            logger.debug(f"Failed reading probe calibration file: {e}")
    return {}


def evaluate_probe(prefix: str, t_s: float, index_mock: Any = None) -> Optional[ControllerDecision]:
    """
    Stage 2 — Corpus Discriminativeness Probe.
    
    Queries BM25 index. If results are peaked (discriminative) -> RETRIEVE.
    If results are flat (ambiguous) -> WAIT.
    If in between, pass to Stage 3.
    """
    if not prefix.strip():
        return ControllerDecision(
            t_s=t_s,
            decision="WAIT",
            reason=ControllerReason.corpus_ambiguous.value,
            confidence=0.9,
            stage=2,
            stage_name="Stage 2: BM25 Probe",
            margin=0.0,
            entropy=1.0,
            threshold=0.10,
        )

    calib = _load_calibration()
    config = get_controller_config()
    tau_hi = float(calib.get("tau_hi", config.get("tau_hi", 0.35)))
    tau_lo = float(calib.get("tau_lo", config.get("tau_lo", 0.10)))
    h_lo_thresh = float(calib.get("h_lo", config.get("h_lo", 0.65)))
    top_k = int(config.get("top_k_probe", 10))
    margin_n = int(config.get("margin_top_n", 5))

    scores = None
    if index_mock is not None:
        scores = index_mock.query(prefix, k=top_k)
    else:
        bm25 = _load_bm25_probe()
        if bm25 is not None:
            try:
                import bm25s
                tokens = bm25s.tokenize([prefix], show_progress=False)
                docs, score_matrix = bm25.retrieve(tokens, k=top_k, show_progress=False)
                if len(score_matrix) > 0:
                    scores = score_matrix[0]
            except Exception as e:
                logger.debug(f"BM25 probe query error on '{prefix}': {e}")
                scores = None

    if scores is None or len(scores) == 0:
        return None  # Pass to stage 3 if no index or scores available

    if scores[0] == 0:
        # No matches at all -> flat / ambiguous
        return ControllerDecision(
            t_s=t_s,
            decision="WAIT",
            reason=ControllerReason.corpus_ambiguous.value,
            confidence=0.8,
            stage=2,
            stage_name="Stage 2: BM25 Probe",
            margin=0.0,
            entropy=1.0,
            threshold=round(tau_lo, 4),
        )

    # Calculate margin: (s1 - mean(s2..s5)) / s1
    s1 = float(scores[0])
    s_rest = scores[1:margin_n] if len(scores) > 1 else []
    mean_rest = float(np.mean(s_rest)) if len(s_rest) > 0 else 0.0
    margin = float((s1 - mean_rest) / s1) if s1 > 0 else 0.0

    # Calculate normalised entropy of top-k scores
    total_score = float(np.sum(scores))
    if total_score > 0:
        p = np.array(scores, dtype=float) / total_score
        p = p[p > 0]
        h_raw = -float(np.sum(p * np.log(p)))
        h_norm = float(h_raw / np.log(len(scores))) if len(scores) > 1 else 0.0
    else:
        h_norm = 1.0

    if margin > tau_hi and h_norm < h_lo_thresh:
        return ControllerDecision(
            t_s=t_s,
            decision="RETRIEVE",
            reason=ControllerReason.corpus_discriminative.value,
            confidence=min(0.7 + margin, 1.0),
            stage=2,
            stage_name="Stage 2: BM25 Probe",
            margin=round(margin, 4),
            entropy=round(h_norm, 4),
            threshold=round(tau_hi, 4),
        )
    elif margin < tau_lo:
        return ControllerDecision(
            t_s=t_s,
            decision="WAIT",
            reason=ControllerReason.corpus_ambiguous.value,
            confidence=0.7,
            stage=2,
            stage_name="Stage 2: BM25 Probe",
            margin=round(margin, 4),
            entropy=round(h_norm, 4),
            threshold=round(tau_lo, 4),
        )

    # In between: pass to Stage 3
    return None
