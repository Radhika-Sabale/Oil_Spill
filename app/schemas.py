"""Pydantic v2 request and response models for the API contract."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import config


class HealthResponse(BaseModel):
    # `model_detail` is about the ML model, not about pydantic's own namespace.
    model_config = ConfigDict(protected_namespaces=())

    ok: bool
    mode: str = "offline"
    cuda: bool
    model_loaded: bool
    detector: str
    ais_rows: int
    ais_vessels: int
    metocean_scenes: int
    scenes: int
    version: str
    warnings: List[str] = Field(default_factory=list)
    model_detail: Dict[str, Any] = Field(default_factory=dict)
    storage: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)


class SceneOut(BaseModel):
    id: str
    title: str
    t_sat: str
    bounds: List[float]
    centroid: List[float]
    crs: str
    ais_mode: str
    source: str = ""
    license: str = ""
    notes: str = ""
    has_truth_mask: bool = False
    thumbnail: Optional[str] = None
    exists: bool = True


class DetectRequest(BaseModel):
    scene_id: Optional[str] = None
    prefer_model: bool = True
    threshold_db: Optional[float] = None
    render_overlays: bool = True


class DriftRequest(BaseModel):
    job_id: Optional[str] = None
    centroid: Optional[List[float]] = Field(
        default=None, description="[lon, lat] used when job_id is absent")
    polygon: Optional[List[List[float]]] = Field(
        default=None, description="optional slick ring as [[lon, lat], ...]")
    t_sat: Optional[str] = None
    hours_back: int = config.HINDCAST_H
    hours_fwd: int = config.FORECAST_H
    ensemble_n: int = config.ENSEMBLE_N
    scene_id: Optional[str] = None


class AttributeRequest(BaseModel):
    job_id: Optional[str] = None
    origin_geojson: Optional[Dict[str, Any]] = None
    origin: Optional[List[float]] = Field(default=None, description="[lon, lat]")
    t_origin: Optional[str] = None
    slick_centroid: Optional[List[float]] = None
    radius_km: float = config.SEARCH_RADIUS_KM
    window_h: float = config.ORIGIN_WINDOW_H
    top_n: int = 10


class RunRequest(BaseModel):
    scene_id: Optional[str] = None
    t_sat: Optional[str] = None
    hindcast_hours: int = config.HINDCAST_H
    forecast_hours: int = config.FORECAST_H
    search_radius_km: float = config.SEARCH_RADIUS_KM
    origin_window_hours: float = config.ORIGIN_WINDOW_H
    ensemble_n: int = config.ENSEMBLE_N
    prefer_model: bool = True
    threshold_db: Optional[float] = None
    top_n: int = 10
    render_overlays: bool = True
    # The caller may name the run so it can poll progress while the synchronous
    # request is still open. Constrained because it becomes a filename.
    job_id: Optional[str] = Field(default=None, pattern=r"^job_[A-Za-z0-9_-]{1,48}$")


class InjectRequest(BaseModel):
    """Optional click-to-drop probe. Not the main path, and labelled as such."""

    lat: float
    lon: float
    t_sat: Optional[str] = None
    radius_km: float = config.SEARCH_RADIUS_KM
    window_h: float = config.ORIGIN_WINDOW_H
    hindcast_hours: int = config.HINDCAST_H
    forecast_hours: int = config.FORECAST_H
    slick_radius_km: float = 1.5
    top_n: int = 10


class JobSummary(BaseModel):
    job_id: str
    scene_id: Optional[str] = None
    created: Optional[str] = None
    oil_polygons: int = 0
    suspects: int = 0
    status: str = "unknown"


# ---------------------------------------------------------------------------
# Stage 4 (M4): kinematic and mass-balance forensics. Contract C in the roadmap.
#
# Additive only: nothing above this line changes. Rules baked into the models:
#   * an unknown value is None, never a guessed number;
#   * a feature that cannot be computed is listed in `unavailable_features`
#     with the reason, instead of being filled in or silently left out;
#   * the score is a prioritisation aid, not a probability of guilt.
# ---------------------------------------------------------------------------
STAGE4_CONCLUSION = "Investigative candidates only; not proof of causation or a finding of guilt"


class Range3(BaseModel):
    """A min / nominal / max estimate. All three None means 'not computed'."""
    min: Optional[float] = None
    nominal: Optional[float] = None
    max: Optional[float] = None

    @model_validator(mode="after")
    def _ordered(self) -> "Range3":
        vals = [v for v in (self.min, self.nominal, self.max) if v is not None]
        if any(v < 0 for v in vals):
            raise ValueError("volume and flow estimates cannot be negative")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min must not exceed max")
        if self.nominal is not None:
            if self.min is not None and self.nominal < self.min:
                raise ValueError("nominal must not be below min")
            if self.max is not None and self.nominal > self.max:
                raise ValueError("nominal must not exceed max")
        return self


class DarkTargetMatch(BaseModel):
    """Radar vs AIS discrepancy. Defaults to 'unavailable': without suitable SAR target
    detection, absence of a detection must never be reported as 'no vessel there'."""
    status: Literal["unavailable", "detected", "not_detected_in_supported_imagery"] = "unavailable"
    reason: Optional[str] = "No SAR vessel-target detection is available for this case"
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class Stage4Candidate(BaseModel):
    mmsi: str
    vessel_name: Optional[str] = None
    time_overlap_minutes: Optional[float] = None
    distance_to_origin_km: Optional[float] = None
    speed_change_knots: Optional[float] = None
    signals: List[str] = Field(default_factory=list)
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    score_explanation: str = "Illustrative ranking only"
    evidence_quality: Literal["low", "medium", "high"] = "low"
    h3_cells: List[str] = Field(default_factory=list)
    dark_target_match: DarkTargetMatch = Field(default_factory=DarkTargetMatch)
    slick_volume_m3: Range3 = Field(default_factory=Range3)
    derived_flow_m3_h: Range3 = Field(default_factory=Range3)
    assumptions: List[str] = Field(default_factory=list)
    unavailable_features: List[str] = Field(default_factory=list)


class Stage4Verdict(BaseModel):
    """attribution_verdict.json (Contract C)."""
    incident_id: str
    case_type: Literal["real_historical", "synthetic_demo", "manual_demo"]
    stage_status: Literal["implemented", "partial", "inherited", "unavailable"] = "partial"
    h3_resolution: Optional[int] = Field(default=None, ge=0, le=15)
    candidates: List[Stage4Candidate] = Field(default_factory=list)
    conclusion: str = STAGE4_CONCLUSION

    @model_validator(mode="after")
    def _fixed_conclusion(self) -> "Stage4Verdict":
        low = self.conclusion.lower()
        if "not proof" not in low and "not a finding of guilt" not in low:
            raise ValueError("conclusion must keep the 'not proof / not a finding of guilt' wording")
        return self

