"""Pydantic v2 schemas for Contract A ('M1 vision output').

Enables downstream modules (M2 drift forecasting, M4 attribution) and external
consumers to validate segmentation and slick characterisation results.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class GeoJSONPolygonGeometry(BaseModel):
    """GeoJSON Polygon geometry: list of linear rings [ [ [lon, lat], ... ] ]."""
    type: Literal["Polygon"] = "Polygon"
    coordinates: List[List[List[float]]]


class GeoJSONMultiPolygonGeometry(BaseModel):
    """GeoJSON MultiPolygon geometry: list of polygon rings."""
    type: Literal["MultiPolygon"] = "MultiPolygon"
    coordinates: List[List[List[List[float]]]]


class SlickPolygonProperties(BaseModel):
    """Properties attached to each detected polygon feature."""
    polygon_id: str
    class_: int = Field(alias="class")
    class_name: str
    pixel_count: int
    area_km2: float
    perimeter_km: float
    length_km: float
    width_km: float
    orientation_deg: float
    compactness: float
    centroid_lon: float
    centroid_lat: float
    bbox: List[float]
    confidence: float
    mean_sigma0_db: Optional[float] = None
    contrast_db: Optional[float] = None

    model_config = {"populate_by_name": True, "extra": "allow"}


class SlickPolygonFeature(BaseModel):
    """GeoJSON Feature for a single slick connected component."""
    type: Literal["Feature"] = "Feature"
    geometry: GeoJSONPolygonGeometry
    properties: Dict[str, Any]


class SceneMetadata(BaseModel):
    """Georeferencing and temporal metadata of the SAR acquisition."""
    source: str
    acquired_at_utc: str
    crs: str
    raster_path: str
    bounds_lonlat: List[float] = Field(
        ...,
        description="Bounding box [west, south, east, north] in EPSG:4326 degrees",
    )


class SlickDetection(BaseModel):
    """Characterisation of the detected slick(s)."""
    geometry: Optional[GeoJSONMultiPolygonGeometry] = Field(
        None,
        description="MultiPolygon uniting all mineral oil polygons, or null if none",
    )
    polygon_count: int = Field(..., ge=0)
    area_km2: Optional[float] = Field(
        None,
        ge=0,
        description="Sum of oil polygon areas in km², or null if none detected",
    )
    confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Overall detection confidence score, or null if no slick detected",
    )
    confidence_definition: str = Field(
        ...,
        description="Explanation of how the confidence value was derived",
    )
    method: Literal["model", "baseline", "manual_demo"]
    polygons: List[SlickPolygonFeature] = Field(
        default_factory=list,
        description="List of mineral oil polygons (class 2) as GeoJSON Features",
    )
    polygons_lookalike: List[SlickPolygonFeature] = Field(
        default_factory=list,
        description="List of look-alike polygons (class 1) as GeoJSON Features",
    )


class MaskMetadata(BaseModel):
    """Paths and properties of the exported raster mask."""
    path: Optional[str] = Field(None, description="Path to .npy mask file")
    shape: List[int]
    dtype: str = "uint8"
    classes: Dict[str, str] = Field(
        default_factory=lambda: {"0": "sea", "1": "look_alike", "2": "mineral_oil"}
    )
    georeferenced_tif: Optional[str] = Field(
        None,
        description="Path to georeferenced GeoTIFF mask file",
    )


class ModelMetadata(BaseModel):
    """Model architecture, weights provenance, and validation metrics."""
    arch: Optional[str] = None
    encoder: Optional[str] = None
    checkpoint_sha256: Optional[str] = None
    reported_metrics: Optional[Dict[str, Any]] = None
    reported_metrics_note: Optional[str] = (
        "measured by the original authors on their own validation tiles, not on this scene"
    )


class ProvenanceMetadata(BaseModel):
    """Execution and cache provenance."""
    served_from_cache: bool = False
    computed_at_utc: str
    cache_key: str
    checkpoint_sha256: Optional[str] = None


class ContractADocument(BaseModel):
    """Contract A standard output document for M1 vision detection."""
    incident_id: str
    case_type: Literal["real_historical", "synthetic_demo", "manual_demo"]
    scene: SceneMetadata
    slick: SlickDetection
    mask: MaskMetadata
    model: ModelMetadata
    provenance: Optional[ProvenanceMetadata] = None
    quality_flags: List[str] = Field(default_factory=list)
    elapsed_s: float = Field(..., ge=0.0)

    model_config = {"extra": "allow"}

