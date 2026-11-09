"""Bounded M3 run over available local mask and metocean products.

This checks the M3 drift core against the stored observation mask and cache. It
does not reprocess the missing source SAR or establish the mask's provenance.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest


@pytest.mark.real_data
def test_m3_local_gom_mask_and_cached_forcing(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    mask_path = root / "data" / "m1_out" / "gom_mc20_chronic_slick_mask.tif"
    field_path = root / "data" / "metocean" / "gom_mc20_chronic_slick.npz"
    if not mask_path.is_file() or not field_path.is_file():
        pytest.skip(
            "requires the local gom_mc20_chronic_slick M1 mask TIFF and metocean NPZ"
        )

    from app import config, pipeline
    from app.drift import fields
    from app.geo import geometry, raster

    monkeypatch.setattr(config, "OFFLINE", True)
    monkeypatch.setattr(config, "OPEN_METEO_LIVE", False)
    monkeypatch.setattr(config, "METOCEAN_DIR", root / "data" / "metocean")
    monkeypatch.setattr(
        fields, "synthetic_field",
        lambda *args, **kwargs: pytest.fail("real-data workflow used synthetic forcing"),
    )

    registry = json.loads((root / "data" / "sar" / "scenes.json").read_text("utf-8"))
    scene = next(row for row in registry["scenes"]
                 if row["id"] == "gom_mc20_chronic_slick")
    t_sat = datetime.fromisoformat(scene["t_sat"].replace("Z", "+00:00"))
    rasterized_mask = raster.load_sar(mask_path)
    polygons = geometry.polygons_from_mask(
        rasterized_mask.array[0], rasterized_mask, klass=2, min_pixels=500,
    )
    assert polygons, "the stored class-2 mask contains no usable seed geometry"
    seed = max(polygons, key=lambda polygon: polygon.area_km2)

    field = fields.load_for_scene(
        scene["id"], seed.centroid_lat, seed.centroid_lon, t_sat,
    )
    assert field.synthetic is False
    assert field.live is False
    assert field.source.startswith("Open-Meteo ERA5")
    assert field.covers(seed.centroid_lat, seed.centroid_lon, t_sat)

    result = pipeline.run_drift(
        seed.ring_lonlat, (seed.centroid_lon, seed.centroid_lat), t_sat,
        hindcast_hours=18, forecast_hours=36, ensemble_n=50,
        scene_id=scene["id"],
    )
    backward = result["_runs"]["back"]
    forward = result["_runs"]["forward"]
    assert result["metocean"]["synthetic"] is False
    assert result["metocean"]["live"] is False
    assert backward.lon.shape == (217, 50)
    assert forward.lon.shape == (37, 50)
    assert backward.meta["forcing_coverage_status"] == "covered"
    assert forward.meta["forcing_coverage_status"] == "covered"
    assert backward.meta["forcing_outside_coverage_evaluations"] == 0
    assert forward.meta["forcing_outside_coverage_evaluations"] == 0
    assert all(np.isfinite(values).all() for values in (
        backward.lon, backward.lat, forward.lon, forward.lat,
    ))
