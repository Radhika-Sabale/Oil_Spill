"""Pydantic v2 request and response models for the API contract."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


def _validate_iso_timestamp(value: Optional[str]) -> Optional[str]:
    if value is None:
        return value
    try:
        datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("timestamp must be ISO 8601") from exc
    return value


def _validate_lonlat_pair(value: List[float], label: str) -> List[float]:
    if len(value) != 2:
        raise ValueError("%s must contain [longitude, latitude]" % label)
    lon, lat = value
    if not math.isfinite(lon) or not math.isfinite(lat):
        raise ValueError("%s coordinates must be finite" % label)
    if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
        raise ValueError("%s coordinates must be within longitude/latitude bounds" % label)
    return value


class DriftRequest(BaseModel):
    job_id: Optional[str] = None
    centroid: Optional[List[float]] = Field(
        default=None, description="[lon, lat] used when job_id is absent")
    polygon: Optional[List[List[float]]] = Field(
        default=None, description="optional slick ring as [[lon, lat], ...]")
    t_sat: Optional[str] = None
    hours_back: int = Field(default=config.HINDCAST_H, ge=1)
    hours_fwd: int = Field(default=config.FORECAST_H, ge=1)
    ensemble_n: int = Field(default=config.ENSEMBLE_N, ge=1)
    scene_id: Optional[str] = None
    metocean_profile: Literal["default", "norse2019"] = "default"

    @field_validator("centroid")
    @classmethod
    def _valid_centroid(cls, value):
        return None if value is None else _validate_lonlat_pair(value, "centroid")

    @field_validator("polygon")
    @classmethod
    def _valid_polygon(cls, value):
        if value is None:
            return None
        if len(value) < 4:
            raise ValueError("polygon must contain at least four [longitude, latitude] points")
        for point in value:
            _validate_lonlat_pair(point, "polygon")
        return value

    @field_validator("t_sat")
    @classmethod
    def _valid_timestamp(cls, value):
        return _validate_iso_timestamp(value)


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
    hindcast_hours: int = Field(default=config.HINDCAST_H, ge=1)
    forecast_hours: int = Field(default=config.FORECAST_H, ge=1)
    search_radius_km: float = Field(default=config.SEARCH_RADIUS_KM, gt=0, allow_inf_nan=False)
    origin_window_hours: float = Field(default=config.ORIGIN_WINDOW_H, gt=0, allow_inf_nan=False)
    ensemble_n: int = Field(default=config.ENSEMBLE_N, ge=1)
    prefer_model: bool = True
    threshold_db: Optional[float] = None
    top_n: int = 10
    render_overlays: bool = True
    metocean_profile: Literal["default", "norse2019"] = "default"
    # The caller may name the run so it can poll progress while the synchronous
    # request is still open. Constrained because it becomes a filename.
    job_id: Optional[str] = Field(default=None, pattern=r"^job_[A-Za-z0-9_-]{1,48}$")

    @field_validator("t_sat")
    @classmethod
    def _valid_timestamp(cls, value):
        return _validate_iso_timestamp(value)


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
# Stage 4 (M4): Contract C, candidate attribution. Unknowns stay null.
# ---------------------------------------------------------------------------

class Stage4Range(BaseModel):
    """A min / nominal / max range. All three are null together, or none are."""

    model_config = ConfigDict(extra="forbid")

    min: Optional[float] = None
    nominal: Optional[float] = None
    max: Optional[float] = None

    @model_validator(mode="after")
    def _ordered(self):
        vals = [self.min, self.nominal, self.max]
        present = [v is not None for v in vals]
        if any(present) and not all(present):
            raise ValueError("a range must be all null or fully populated")
        if all(present):
            if any((not math.isfinite(v)) or v < 0 for v in vals):
                raise ValueError("range values must be finite and non-negative")
            if not (self.min <= self.nominal <= self.max):
                raise ValueError("range must satisfy min <= nominal <= max")
        return self


class Stage4DarkTarget(BaseModel):
    """Radar dark-target comparison. 'unavailable' is the honest default."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["unavailable", "detected", "not_detected_in_supported_imagery"] = "unavailable"
    reason: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _explain(self):
        if self.status == "unavailable" and not self.reason:
            raise ValueError("an unavailable dark-target status needs a reason")
        return self


class Stage4Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mmsi: str
    vessel_name: Optional[str] = None
    time_overlap_minutes: Optional[float] = Field(default=None, ge=0.0)
    distance_to_origin_km: Optional[float] = Field(default=None, ge=0.0)
    speed_change_knots: Optional[float] = None
    signals: List[str] = Field(default_factory=list)
    score: float = Field(ge=0.0, le=1.0, description="prioritisation aid, not a probability of guilt")
    score_explanation: str
    evidence_quality: Literal["low", "medium", "high"]
    h3_cells: List[str] = Field(default_factory=list)
    dark_target_match: Stage4DarkTarget = Field(default_factory=lambda: Stage4DarkTarget(
        status="unavailable", reason="not computed"))
    slick_volume_m3: Stage4Range = Field(default_factory=Stage4Range)
    derived_flow_m3_h: Stage4Range = Field(default_factory=Stage4Range)
    assumptions: List[str] = Field(default_factory=list)
    unavailable_features: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)


class Stage4Verdict(BaseModel):
    incident_id: Optional[str] = None
    case_type: Literal["real_historical", "synthetic_demo", "manual_demo"]
    candidates: List[Stage4Candidate] = Field(default_factory=list)
    conclusion: str
    stage4_status: Dict[str, str] = Field(default_factory=dict)
    ais_coverage: Dict[str, Any] = Field(default_factory=dict)
    h3: Dict[str, Any] = Field(default_factory=dict)
    slick: Dict[str, Any] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _no_candidates_without_ais(self):
        if self.ais_coverage.get("attribution_status") == "not_possible" and self.candidates:
            raise ValueError("candidates were listed although AIS attribution was not possible")
        return self

    @field_validator("conclusion")
    @classmethod
    def _no_guilt_claim(cls, v: str) -> str:
        low = v.lower()
        if "not proof" not in low or "finding of guilt" not in low:
            raise ValueError("conclusion must say the result is not proof and not a finding of guilt")
        return v
