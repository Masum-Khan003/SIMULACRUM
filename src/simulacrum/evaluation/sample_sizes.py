"""
Documented minimum sample sizes for calibration/training (§11, prevents
Palimpsest bug #16: a threshold calibrated from ~29 samples that was
really just "the largest value observed").

These are hard floors, enforced by refusal to proceed — not
suggestions. Any calibration/training entrypoint must call the
corresponding require_* function before computing a threshold or
training a model.
"""
from __future__ import annotations

# Minimum labeled normal-session samples required before computing any
# statistical threshold (e.g. a detector's calibration percentile).
# Rationale: bug #16 showed a threshold from ~29 samples was just the
# max observed value, not a real percentile. This floor is set well
# above that failure point.
MIN_CALIBRATION_SAMPLES = 200

# Minimum labeled sessions (across all attack classes + normal) required
# before training the trajectory sequence model (§10). Sequence models
# overfit badly on small session counts; this floor is a starting
# placeholder pending real learning-curve analysis in Phase 2, not a
# number derived from data yet — documented as such.
MIN_TRAINING_SESSIONS = 500


class InsufficientSampleSizeError(RuntimeError):
    """Raised when a calibration/training call is attempted below the
    documented minimum sample size."""


def require_calibration_samples(*, sample_count: int) -> None:
    if sample_count < MIN_CALIBRATION_SAMPLES:
        raise InsufficientSampleSizeError(
            f"Calibration requires at least {MIN_CALIBRATION_SAMPLES} "
            f"labeled samples; got {sample_count}. Refusing to compute "
            f"a threshold from an insufficient sample (Palimpsest bug #16)."
        )


def require_training_sessions(*, session_count: int) -> None:
    if session_count < MIN_TRAINING_SESSIONS:
        raise InsufficientSampleSizeError(
            f"Trajectory model training requires at least "
            f"{MIN_TRAINING_SESSIONS} labeled sessions; got "
            f"{session_count}. Refusing to train below the documented "
            f"minimum."
        )
