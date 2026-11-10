/* SentinelTrace analysis adapter
   ---------------------------------------------------------------------------
   One module owns the mapping between what the API returns and what the UI and
   the dossier render. Nothing else in app/static/ reads a raw job document for
   stage status, data status or provenance.

   CONTRACT STATUS: there is no separately agreed analysis-document contract in
   this repository. `app/schemas.py` defines per-route models (Contract A vision
   output lives in app/vision/schema.py, Contract C in app/schemas.Stage4Verdict)
   but there is no document that joins all five stages. So this module DEFINES a
   derived shape, `sentineltrace.analysis/1`, built only from fields the job
   document, the scene registry and /api/health actually carry. It never invents
   a value: a field that is absent becomes null plus an explicit reason, which
   the UI prints as "not available".

   If a versioned endpoint appears later (/api/v1/analysis/{job_id}), the adapter
   prefers it and reports `source: "contract"`. Until then it reports
   `source: "legacy"`, which the console shows in its diagnostics area.
*/
(function () {
  "use strict";

  var CONTRACT = "sentineltrace.analysis/1";

  /* The five pipeline stages, named the way the repository's audit and roadmap
     name them. `key` is the job-document / stage_status key where one exists. */
  var STAGES = [
    {
      id: "ingest", index: 1, name: "Ingest & gate", owner: "M2",
      blurb: "Scene validation, incidence handling, 3-12 m/s wind gate, CA-CFAR screen",
      code: "app/stage1.py"
    },
    {
      id: "segment", index: 2, name: "Segment", owner: "M1",
      blurb: "SAR oil / look-alike segmentation and slick characterisation",
      code: "app/ml/infer.py, app/geo/geometry.py"
    },
    {
      id: "hindcast", index: 3, name: "Hindcast & forecast", owner: "M3",
      blurb: "Backward ensemble, estimated origin zone, forward forecast cone",
      code: "app/drift/"
    },
    {
      id: "attribute", index: 4, name: "Attribute", owner: "M4",
      blurb: "AIS reconstruction, spatio-temporal funnel, candidate scoring",
      code: "app/ais/"
    },
    {
      id: "present", index: 5, name: "Present & package", owner: "M5",
      blurb: "Console views, evidence panels and the downloadable dossier",
      code: "app/static/"
    }
  ];

  var STAGE_STATUS = {
    not_started: { label: "Not started", icon: "\u25CB", tone: "idle" },
    running: { label: "Running", icon: "\u25D4", tone: "run" },
    done: { label: "Done", icon: "\u2713", tone: "ok" },
    failed: { label: "Failed", icon: "\u2715", tone: "bad" },
    unavailable: { label: "Unavailable", icon: "\u2014", tone: "na" }
  };

  var DATA_STATUS = {
    real: { label: "REAL", icon: "\u25CF", tone: "real", help: "Measured or recorded input" },
    simulated: { label: "SIMULATED", icon: "\u2248", tone: "sim", help: "Generated input, not observed" },
    missing: { label: "MISSING", icon: "\u2715", tone: "missing", help: "Not present for this case" }
  };

  /* ------------------------------------------------------------------ utils */

  function num(v) {
    return (typeof v === "number" && isFinite(v)) ? v : null;
  }

  function txt(v) {
    if (v === null || v === undefined) return null;
    var s = String(v).trim();
    return s ? s : null;
  }

  function utc(iso) {
    if (!iso) return null;
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    return d.toISOString().replace(".000Z", "Z").replace("T", " ").replace("Z", " UTC");
  }

  function isoFromTs(ts) {
    if (ts === null || ts === undefined) return null;
    var d = new Date(Number(ts) * 1000);
    return isNaN(d.getTime()) ? null : d.toISOString();
  }

  function addHours(iso, hours) {
    if (!iso || hours === null || hours === undefined) return null;
    var d = new Date(iso);
    if (isNaN(d.getTime())) return null;
    return new Date(d.getTime() + Number(hours) * 3600 * 1000).toISOString();
  }

  function one(v, fallback) {
    return v === undefined || v === null || v === "" ? (fallback === undefined ? null : fallback) : v;
  }

  function uniq(list) {
    var seen = {};
    return list.filter(function (x) {
      var k = typeof x === "string" ? x : JSON.stringify(x);
      if (seen[k]) return false;
      seen[k] = 1;
      return true;
    });
  }

  /* ------------------------------------------------------- data status rules */

  function badge(status, source, date, note) {
    var def = DATA_STATUS[status] || DATA_STATUS.missing;
    return {
      status: status,
      label: def.label,
      icon: def.icon,
      tone: def.tone,
      help: def.help,
      source: source || null,
      date: date || null,
      note: note || null
    };
  }

  function detectorName(metrics) {
    metrics = metrics || {};
    if (metrics.detector === "unet") return "U-Net++ checkpoint";
    if (metrics.detector) return "dB baseline (no checkpoint)";
    return null;
  }

  /* ------------------------------------------------------------ stage rules */

  function stage(id, status, reason, detail, extra) {
    var def = STAGES.filter(function (s) { return s.id === id; })[0] || { id: id, name: id };
    var st = STAGE_STATUS[status] || STAGE_STATUS.not_started;
    return Object.assign({
      id: id,
      index: def.index,
      name: def.name,
      owner: def.owner,
      blurb: def.blurb,
      code: def.code,
      status: status,
      statusLabel: st.label,
      statusIcon: st.icon,
      tone: st.tone,
      reason: reason || null,
      detail: detail || null
    }, extra || {});
  }

  /* ------------------------------------------------------- analysis builder */

  function build(job, ctx) {
    ctx = ctx || {};
    if (!job) return empty(ctx);

    var det = job.detection || {};
    var metrics = det.metrics || {};
    var drift = job.drift || null;
    var attr = job.attribution || {};
    var stage4 = attr.stage4 || {};
    var input = job.input || {};
    var scene = job.scene || ctx.scene || {};
    var mo = (drift && drift.metocean) || {};
    var physics = (drift && drift.physics) || {};
    var origin = (drift && drift.origin) || {};
    var tSat = input.t_sat || scene.t_sat || null;
    var inputHours = one(input.hindcast_hours, ctx.config && ctx.config.hindcast_hours);
    var forecastHours = one(input.forecast_hours);
    var windowHours = one(input.origin_window_hours);
    var polys = det.polygons || [];
    var looks = det.lookalikes || [];
    var suspects = attr.suspects || [];
    var s4cands = stage4.candidates || [];
    var radiometry = metrics.radiometry || {};
    var aisSources = attr.sources_used || (attr.funnel || {}).sources_used || {};
    var aisData = attr.ais_data || scene.ais_data || {};
    var aisStatus = aisData.status || "";
    var aisSimulated = aisStatus.indexOf("simulated_") === 0 || aisStatus.indexOf("mixed_") === 0 ||
      Object.keys(aisSources).some(function (k) { return /synthetic|simulated|selftest/i.test(k); });
    var aisReal = aisStatus.indexOf("real_") === 0 || aisStatus.indexOf("mixed_") === 0 ||
      Object.keys(aisSources).some(function (k) { return !/synthetic|simulated|selftest/i.test(k); });
    var aisKind = aisSimulated ? "simulated" : aisReal ? "real" : "missing";
    var h3 = stage4.h3 || {};
    var baseline = metrics.detector && metrics.detector !== "unet";

    /* ---- inputs: every one carries status + source + date, never a guess --- */
    var inputs = [];

    inputs.push({
      id: "sar_scene",
      label: "Sentinel-1 SAR chip",
      usedBy: "Segment",
      provenance: badge(
        det.metrics && scene && scene.exists === false ? "missing" : (det.polygons || det.metrics ? "real" : "missing"),
        scene.source || null,
        tSat,
        (scene.license || null)
      ),
      extra: scene.id ? ("Scene " + scene.id) : null
    });

    if (scene.mask_path === null || scene.has_truth_mask === false || scene.mask_path === undefined) {
      inputs.push({
        id: "ground_truth", label: "Validation mask / ground truth", usedBy: "Segment (scoring only)",
        provenance: badge("missing", null, null,
          "No ground-truth mask is indexed for this scene, so detection accuracy against truth is not reported."),
        extra: null
      });
    } else {
      inputs.push({
        id: "ground_truth", label: "Validation mask / ground truth", usedBy: "Segment (scoring only)",
        provenance: badge("real", scene.mask_path, tSat, null), extra: null
      });
    }

    var eo = det.eo || {};
    inputs.push({
      id: "optical", label: "Sentinel-2 optical chip (corroboration)", usedBy: "Segment",
      provenance: eo.available ? badge("real", eo.source || "Sentinel-2 L2A", eo.acquired || null,
        eo.offset_label || null)
        : badge("missing", null, null, eo.reason || "No optical chip is cached for this footprint."),
      extra: null
    });

    inputs.push({
      id: "wind", label: "ERA5 10 m wind field", usedBy: "Hindcast",
      provenance: mo.source
        ? badge(mo.synthetic ? "simulated" : "real", mo.source, mo.t_start || null,
          mo.synthetic ? "No cached cube covers this scene; a constant field was substituted." : null)
        : badge("missing", null, null, "Drift did not run, so no wind field is reported."),
      extra: mo.t_start ? ("Cube " + utc(mo.t_start) + " to " + utc(mo.t_end)) : null
    });

    inputs.push({
      id: "current", label: "Surface current field", usedBy: "Hindcast",
      provenance: !mo.source ? badge("missing", null, null, "Drift did not run.")
        : (mo.synthetic
          ? badge("simulated", mo.source, mo.t_start, "A synthetic constant current is used only as a fallback; no real current observations are available.")
          : mo.has_currents === false
          ? badge("missing", mo.source, mo.t_start, "The cached cube carries wind but no ocean current for this basin; drift is wind driven only.")
          : badge(mo.synthetic ? "simulated" : "real", mo.source, mo.t_start, null)),
      extra: null
    });

    inputs.push({
      id: "waves", label: "Wave forcing (Stokes drift)", usedBy: "Hindcast",
      provenance: mo.stokes_available ? badge("real", mo.source, mo.t_start, null)
        : badge("missing", null, null,
          "No usable wave fields in the cached forcing, so Stokes drift is omitted and documented as omitted."),
      extra: physics.stokes_available === false ? "Physics metadata confirms Stokes unavailable" : null
    });

    inputs.push({
      id: "ais", label: "AIS vessel tracks", usedBy: "Attribute",
      provenance: !Object.keys(aisSources).length
        ? badge(aisKind, null, null,
          aisData.label || (suspects.length ? "Track source not reported by the job document." : "No AIS rows were used for this case."))
        : badge(aisKind,
          Object.keys(aisSources).sort().join(", "),
          (stage4.parameters && stage4.parameters.window_start_ts
            ? isoFromTs(stage4.parameters.window_start_ts) : null),
          aisSimulated ? "Simulated traffic over the scene's real geobox and time window. Not received positions." : null),
      extra: Object.keys(aisSources).length
        ? Object.keys(aisSources).map(function (k) { return k + "=" + aisSources[k]; }).join("  ")
        : null
    });

    inputs.push({
      id: "model", label: "Trained segmentation checkpoint", usedBy: "Segment",
      provenance: baseline
        ? badge("missing", "models/oil_unet_best.pt", null,
          "No checkpoint loaded, so the dB baseline ran. The console names the baseline wherever it reports a detection.")
        : (metrics.detector ? badge("real", "models/oil_unet_best.pt", null,
          (metrics.detector_detail && metrics.detector_detail.checkpoint_sha256) || null)
          : badge("missing", null, null, "Detection did not run.")),
      extra: detectorName(metrics)
    });

    inputs.push({
      id: "stage1", label: "Stage 1 gate output (wind gate, CFAR)", usedBy: "Ingest & gate",
      provenance: badge("missing", null, null,
        "app/stage1.py exists but no stage1 block is written into the job document, so there is no gate result to show."),
      extra: null
    });

    if (h3.status) {
      inputs.push({
        id: "h3", label: "H3 spatial index", usedBy: "Attribute",
        provenance: h3.status === "implemented"
          ? badge("real", "h3 python package, resolution " + h3.resolution, null, h3.note || null)
          : badge("missing", null, null, h3.note || "The optional h3 package is not installed."),
        extra: null
      });
    }

    /* ---- stages ----------------------------------------------------------- */
    var stages = [];

    stages.push(stage("ingest", "unavailable",
      "Stage 1 (app/stage1.py) is not wired into the pipeline: the job document has no stage1 block. " +
      "No wind gate, incidence-normalisation status or CA-CFAR screen is available for this case.",
      input.metocean_profile ? ("Run profile: " + input.metocean_profile) : null,
      {
        outputs: [
          { label: "Wind gate (3-12 m/s)", value: "not available in this build" },
          { label: "Incidence normalisation", value: "not available in this build" },
          { label: "CA-CFAR candidate windows", value: "not available in this build" }
        ]
      }));

    if (!det || Object.keys(det).length === 0) {
      stages.push(stage("segment", "not_started", "Segmentation has not run for this job."));
    } else if (det.error) {
      stages.push(stage("segment", "failed", String(det.error)));
    } else {
      var segReason = polys.length
        ? (detectorName(metrics) || "detector") + " found " + polys.length + " oil polygon" +
          (polys.length === 1 ? "" : "s") + " and " + looks.length + " look-alike" + (looks.length === 1 ? "" : "s") + "."
        : ((job.clean_scene && job.clean_scene.headline) || "No oil polygon above the reporting threshold.") +
          " An empty result is reported as a result, not a failure.";
      stages.push(stage("segment", "done", segReason, null, {
        outputs: [
          { label: "Oil polygons", value: String(polys.length) },
          { label: "Look-alikes (excluded)", value: String(looks.length) },
          { label: "Total oil area", value: metrics.oil_area_km2 != null ? metrics.oil_area_km2 + " km\u00B2" : "n/a" },
          { label: "Detector", value: detectorName(metrics) || "not reported" },
          { label: "Water contrast span", value: radiometry.dynamic_range_db != null ? radiometry.dynamic_range_db + " dB" : "n/a" }
        ]
      }));
    }

    if (!drift) {
      stages.push(stage("hindcast", "not_started",
        polys.length ? "Drift has not run for this job."
          : "No slick to trace back, so drift and forecast were not run. That is by design."));
    } else {
      var solverBits = [];
      if (physics.solver) solverBits.push(String(physics.solver));
      if (physics.dt_seconds) solverBits.push((physics.dt_seconds / 60) + " min steps");
      if (physics.n_particles) solverBits.push(physics.n_particles + " particles");
      stages.push(stage("hindcast", "done",
        "Backward ensemble converged on a minimum-variance origin; forecast cone and threatened box computed.",
        solverBits.length ? solverBits.join(", ") : null, {
          outputs: [
            { label: "Origin (zone centre)", value: origin.lat != null ? origin.lat + ", " + origin.lon : "n/a" },
            { label: "Origin time", value: utc(origin.t) || "n/a" },
            { label: "Zone radius", value: origin.spread_km != null ? origin.spread_km + " km (90th pct, uncalibrated)" : "n/a" },
            { label: "Zone area", value: origin.area_km2 != null ? origin.area_km2 + " km\u00B2" : "n/a" },
            { label: "Forecast horizon", value: forecastHours != null ? forecastHours + " h" : "n/a" }
          ]
        }));
    }

    if (stage4.error) {
      stages.push(stage("attribute", "failed", String(stage4.error)));
    } else if (!attr.suspects) {
      stages.push(stage("attribute", "not_started", "No AIS attribution was run for this job."));
    } else {
      var src = Object.keys(aisSources).sort().join(", ");
      stages.push(stage("attribute", "done",
        suspects.length
          ? suspects.length + " candidate" + (suspects.length === 1 ? "" : "s") + " ranked from " +
            (src || "the AIS store") + ". Ranking is a prioritisation aid, not a probability."
          : "No vessel passed the spatio-temporal filter. Reporting no suspects rather than forcing a culprit.",
        Object.keys(stage4.stage4_status || {}).length
          ? "Stage 4 features: " + Object.keys(stage4.stage4_status).map(function (k) {
            return k + "=" + stage4.stage4_status[k];
          }).join(", ") : null, {
          outputs: [
            { label: "Candidates ranked", value: String(suspects.length) },
            { label: "AIS source", value: aisSimulated ? "SIMULATED traffic" : (src || "not reported") },
            { label: "Evidence quality (top)", value: (s4cands[0] && s4cands[0].evidence_quality) || "n/a" },
            { label: "Dark-target comparison", value: (stage4.stage4_status && stage4.stage4_status.dark_target) || "unavailable" }
          ]
        }));
    }

    stages.push(stage("present", "done",
      "This document is the single source for every panel on the right and for the dossier PDF. " +
      "The dossier is rendered from it without recomputation.",
      "Dossier integrity: SHA-256 of the generated PDF is shown in the Dossier view.",
      {
        outputs: [
          { label: "Document", value: CONTRACT },
          { label: "Job document", value: job.job_id || "n/a" },
          { label: "Run wall time", value: job.total_ms != null ? (job.total_ms / 1000).toFixed(1) + " s" : "n/a" }
        ]
      }));

    /* ---- uncertainty ------------------------------------------------------ */
    var uncertainty = {
      origin: drift ? {
        available: true,
        lat: num(origin.lat),
        lon: num(origin.lon),
        time: utc(origin.t),
        radiusKm: num(origin.spread_km),
        bufferKm: num(origin.buffer_km),
        areaKm2: num(origin.area_km2),
        hoursBack: num(origin.index_hours_back),
        zoneGeometry: (drift.origin_zone || {}).geometry || null,
        method: "Approximate 95% KDE highest-density region buffered by " +
          (origin.buffer_km != null ? origin.buffer_km + " km" : "a fixed radius") +
          ". The displayed radius is the 90th-percentile particle distance. Neither is a calibrated probability region.",
        note: "The origin is an estimated zone, not a verified release point."
      } : {
        available: false,
        reason: polys.length ? "Drift did not run for this job." : "No slick to trace back."
      },
      windows: buildWindows(tSat, origin, inputHours, forecastHours, windowHours, stage4),
      detection: polys.length ? {
        polygons: polys.length,
        bestConfidence: num((polys[0] || {}).properties && polys[0].properties.confidence),
        method: detectorName(metrics) || "not reported",
        note: "Per-polygon confidence is the detector's own score for this scene, not a calibrated probability."
      } : { polygons: 0, reason: "No oil polygon reported." },
      forcing: {
        available: !!mo.source,
        source: mo.source || null,
        synthetic: !!mo.synthetic,
        coversScene: drift ? drift.metocean_covers_scene !== false : null,
        hasCurrents: mo.has_currents !== false,
        stokes: !!mo.stokes_available,
        windFactor: physics.alpha_wind != null ? physics.alpha_wind : null,
        deflectionDeg: physics.deflection_deg != null ? physics.deflection_deg : null,
        cube: mo.t_start ? (utc(mo.t_start) + " to " + utc(mo.t_end)) : null,
        limits: [
          mo.synthetic ? "Synthetic constant forcing: clause (b) is not satisfied until a real cube is cached." : null,
          mo.has_currents === false ? "Wind only: no ocean current data for this basin." : null,
          !mo.stokes_available ? "Stokes drift omitted: no usable wave forcing." : null,
          drift && drift.metocean_covers_scene === false ? "Cached forcing does not fully cover the scene time or footprint; edge values were clamped." : null
        ].filter(Boolean)
      },
      scores: suspects.length ? {
        max: num(suspects[0].score),
        confidence: num(suspects[0].confidence),
        note: "Score is a prioritisation aid on documented weights. It is not a probability and is not calibrated against ground truth."
      } : { reason: "No candidate was scored." }
    };

    /* ---- candidates ------------------------------------------------------- */
    var s4ByMmsi = {};
    s4cands.forEach(function (c) { s4ByMmsi[String(c.mmsi)] = c; });

    var candidates = suspects.map(function (s) {
      var s4 = s4ByMmsi[String(s.mmsi)] || {};
      var d = s.detail || {};
      var gaps = d.gaps || [];
      var gapMin = gaps.reduce(function (a, g) { return Math.max(a, num(g.minutes) || 0); }, 0);
      return {
        mmsi: String(s.mmsi),
        rank: s.rank,
        name: s.name || null,
        type: s.type || null,
        score: num(s.score),
        confidence: num(s.confidence),
        scoreBeforeConfidence: num(s.score_before_confidence),
        reasons: (s.reasons || []).slice(),
        signals: (s4.signals || []).slice(),
        components: {
          proximity: num((s.components || {}).prox),
          time: num((s.components || {}).time),
          behaviour: num((s.components || {}).beh),
          type: num((s.components || {}).type),
          trajectory: num((s.components || {}).traj)
        },
        weighted: s.weighted || {},
        coverage: {
          receivedPositions: num(d.raw_positions),
          deadReckonedFraction: num(d.dead_reckoned_fraction),
          gaps: gaps.length,
          longestGapMinutes: gapMin || null,
          timeOverlapMinutes: num(s4.time_overlap_minutes),
          receivedOverlapMinutes: num((s4.evidence || {}).time_overlap_received_minutes)
        },
        distanceToOriginKm: num(d.origin_distance_km != null ? d.origin_distance_km : d.min_distance_km),
        closestApproach: utc(d.closest_approach_utc),
        assumptions: (s4.assumptions || []).slice(),
        unavailable: (s4.unavailable_features || []).slice(),
        evidenceQuality: s4.evidence_quality || null,
        darkTarget: s4.dark_target_match || null,
        volume: s4.slick_volume_m3 || null,
        flow: s4.derived_flow_m3_h || null,
        h3Cells: (s4.h3_cells || []).length,
        trackGeometry: (s.track || {}).geojson || null,
        samples: (s.track || {}).samples || []
      };
    });

    /* ---- assumptions, limitations, unavailable ---------------------------- */
    var assumptions = [];
    candidates.forEach(function (c) {
      c.assumptions.forEach(function (a) { assumptions.push(a); });
    });
    assumptions = uniq(assumptions);
    assumptions.push("Age is the time between the estimated origin and the radar pass. It is a drift proxy, not a chemical weathering age.");
    assumptions.push("Origin time is chosen at minimum ensemble variance and its region is an uncalibrated KDE hull.");
    if (drift && physics.alpha_wind != null) {
      assumptions.push("Surface drift = current + " + physics.alpha_wind + " x 10 m wind" +
        (physics.deflection_deg != null ? ", with " + physics.deflection_deg + " deg leeway deflection" : "") +
        ". Stokes drift is " + (mo.stokes_available ? "included" : "omitted") + ".");
    }
    if (aisSimulated) assumptions.push("Candidate vessels come from simulated AIS traffic over this scene's real geobox and time window, written in MarineCadastre columns.");
    if (baseline) assumptions.push("Detection ran on the dB baseline because no trained checkpoint was loaded. It is identified as a baseline everywhere.");
    if (suspects.length) assumptions.push("Proximity decays with distance to the estimated origin point (R = zone radius). A track mostly reconstructed by dead reckoning cannot outrank one built from received positions.");
    assumptions = uniq(assumptions);

    var limitations = [];
    limitations.push("Ranked candidates are investigation leads, not a finding of guilt and not proof of causation.");
    limitations.push("The origin is an estimated zone. It is not a verified release position, and its probability level is not calibrated.");
    limitations.push("AIS gaps are missing broadcasts. A gap is not evidence of intent.");
    limitations.push("Look-alike polygons are excluded from attribution by design.");
    limitations.push("The trained detector is a binary oil segmenter, so the shipped model never draws a look-alike; only the dB baseline separates them.");
    limitations.push("There is no SAR vessel-target detection in this build, so AIS cannot be compared against radar dark targets.");
    limitations.push("The dossier PDF is a plain PDF. No PDF/A validation has been run on it, so it is not described as PDF/A.");
    if (aisSimulated) limitations.push("This scene sits outside public AIS coverage; vessel tracks are simulated, not received.");
    if (mo.synthetic) limitations.push("Forcing is a synthetic constant field for this scene; clause (b) is not satisfied.");
    if (mo.has_currents === false && !mo.synthetic) limitations.push("Only wind forcing is available for this basin; currents are absent from the cached cube.");
    (job.warnings || []).forEach(function (w) { limitations.push(w); });
    limitations = uniq(limitations);

    var unavailable = [];
    unavailable.push({
      feature: "Stage 1 wind gate, incidence normalisation and CA-CFAR screen",
      reason: "app/stage1.py is not wired into the pipeline, so these results are not in the job document."
    });
    unavailable.push({
      feature: "Radar dark-target (SAR vessel detection) comparison",
      reason: (s4cands[0] && (s4cands[0].dark_target_match || {}).reason) ||
        "No SAR vessel-detection stage exists in this build. A missing detection is not evidence that no vessel was there."
    });
    unavailable.push({
      feature: "PDF/A archival profile (not claimed)",
      reason: "Output is a plain PDF. No PDF/A validator (for example veraPDF) has been run in this environment, so PDF/A is not claimed."
    });
    if (h3.status && h3.status !== "implemented") {
      unavailable.push({ feature: "H3 spatial index", reason: h3.note || "The optional h3 package is not installed." });
    }
    if (s4cands.length && !(s4cands[0].slick_volume_m3 || {}).nominal) {
      unavailable.push({
        feature: "Slick volume and derived flow ranges",
        reason: "Reported only when a measured slick area and an explicit thickness assumption are supplied; otherwise the range stays null."
      });
    }
    if (!mo.stokes_available) {
      unavailable.push({ feature: "Stokes (wave-driven) drift", reason: "No usable wave forcing in the cached cube; the term is omitted from the physics." });
    }
    unavailable.push({
      feature: "Live satellite tasking",
      reason: "Imagery is an archive Sentinel-1 acquisition read from disk. Nothing in this build tasks a satellite."
    });

    if (aisSimulated) {
      unavailable.push({ feature: "Real received AIS for this footprint", reason: "Outside public AIS coverage; simulated traffic is used and labelled." });
    }

    /* ---- provenance + model/forcing metadata ------------------------------ */
    var model = {
      detector: detectorName(metrics) || "not reported",
      baseline: !!baseline,
      fallbackReason: metrics.fallback_reason || null,
      checkpoint: (metrics.detector_detail && metrics.detector_detail.checkpoint) || null,
      checkpointSha256: (metrics.detector_detail && metrics.detector_detail.checkpoint_sha256) || null,
      reportedMetrics: (metrics.detector_detail && metrics.detector_detail.metrics) || null,
      metricsNote: "Reported checkpoint metrics are measured on the Zenodo validation tiles, not on this scene.",
      tileSize: ctx.config && ctx.config.tile,
      thresholdDb: (metrics.detector_detail && metrics.detector_detail.threshold_db) != null
        ? metrics.detector_detail.threshold_db
        : (ctx.config && ctx.config.oil_db_threshold)
    };

    var forcing = {
      source: mo.source || null,
      cube: mo.t_start ? (utc(mo.t_start) + " to " + utc(mo.t_end)) : null,
      synthetic: !!mo.synthetic,
      hasCurrents: mo.has_currents !== false,
      hasWaves: !!mo.stokes_available,
      meanWindMs: num(mo.mean_wind_ms),
      meanCurrentMs: num(mo.mean_current_ms),
      live: !!mo.live,
      coversScene: drift ? drift.metocean_covers_scene !== false : null,
      alphaWind: num(physics.alpha_wind),
      deflectionDeg: num(physics.deflection_deg),
      particles: num(physics.n_particles),
      solver: physics.solver || null,
      dtSeconds: num(physics.dt_seconds)
    };

    var dataset = {
      contract: CONTRACT,
      contractStatus: "derived",
      contractNote: "No agreed five-stage analysis contract exists in this repository. This document is derived from the job document, the scene registry and /api/health; absent fields are null with a reason.",
      generatedAt: new Date().toISOString(),
      source: ctx.endpoints || { mode: "legacy", analysis: false, dossier: false },
      case: {
        jobId: job.job_id || null,
        sceneId: input.scene_id || scene.id || null,
        title: scene.title || input.scene_id || "Untitled case",
        tSat: utc(tSat),
        tSatRaw: tSat,
        created: utc(job.created),
        status: job.status || "unknown",
        caseType: (stage4.case_type) || null,
        detector: detectorName(metrics),
        totalMs: num(job.total_ms),
        headcount: candidates.length,
        primaryAreaKm2: num(metrics.oil_area_km2),
        cleanScene: job.clean_scene || null,
        configVersion: (job.config && job.config.version) || (ctx.health && ctx.health.version) || null
      },
      stages: stages,
      inputs: inputs,
      uncertainty: uncertainty,
      candidates: candidates,
      assumptions: assumptions,
      limitations: limitations,
      unavailable: unavailable,
      provenance: {
        note: "Every input below is reported with the status the pipeline actually recorded. A simulated or missing input is never presented as real.",
        inputs: inputs.map(function (i) {
          return {
            id: i.id, label: i.label, usedBy: i.usedBy,
            status: i.provenance.status, source: i.provenance.source,
            date: i.provenance.date, note: i.provenance.note
          };
        })
      },
      model: model,
      forcing: forcing,
      layers: buildLayers(det, drift, aisSimulated, !!eo.available)
    };

    return dataset;
  }

  function buildWindows(tSat, origin, hindcastHours, forecastHours, windowHours, stage4) {
    var out = [];
    out.push({ label: "Radar acquisition", start: tSat, end: tSat, note: "Single SAR pass time." });
    if (origin && origin.t) {
      out.push({
        label: "Hindcast window",
        start: origin.t,
        end: tSat,
        note: hindcastHours != null ? ("Up to " + hindcastHours + " h backward, " + (origin.index_hours_back != null ? origin.index_hours_back + " h selected" : "selected by minimum variance")) : null
      });
      if (windowHours != null) {
        out.push({
          label: "AIS search window",
          start: addHours(origin.t, -windowHours),
          end: addHours(origin.t, windowHours),
          note: "Plus or minus " + windowHours + " h around the estimated origin time."
        });
      }
    }
    if (stage4 && stage4.parameters && stage4.parameters.window_start_ts) {
      out.push({
        label: "AIS window as applied",
        start: isoFromTs(stage4.parameters.window_start_ts),
        end: isoFromTs(stage4.parameters.window_end_ts),
        note: "Window actually applied by the attribution stage."
      });
    }
    if (tSat && forecastHours != null) {
      out.push({
        label: "Forecast window",
        start: tSat,
        end: addHours(tSat, forecastHours),
        note: "Forward drift envelope, not a prediction of observed oil."
      });
    }
    return out;
  }

  function buildLayers(det, drift, aisSimulated, opticalAvailable) {
    var layers = [
      { id: "oil", label: "Oil polygons", kind: "observed", note: "Derived from the real SAR chip by the detector." },
      { id: "lookalike", label: "Look-alikes (excluded)", kind: "observed", note: "Baseline path only; excluded from attribution." },
      { id: "hindcast", label: "Back-trajectory ensemble median", kind: "model", note: "Modelled from cached forcing." },
      { id: "cone_back", label: "Hindcast cone", kind: "model", note: "Modelled envelope, not an observed path." },
      { id: "origin", label: "Release zone (estimated origin)", kind: "model", note: "Uncalibrated KDE region; not a verified release point." },
      { id: "forecast", label: "Forecast track", kind: "model", note: "Model projection." },
      { id: "cone_fwd", label: "Forecast cone", kind: "model", note: "90 percent ensemble envelope." },
      { id: "tracks", label: "Vessel tracks", kind: aisSimulated ? "simulated" : "observed", note: aisSimulated ? "Simulated AIS traffic, not received positions." : "Real recorded AIS tracks." },
      { id: "vessels", label: "Vessel marks", kind: aisSimulated ? "simulated" : "observed", note: "Timeline position of each ranked vessel." }
    ];
    if (!drift) {
      layers.forEach(function (l) { if (l.kind === "model") l.kind = "unavailable"; });
    }
    if (!opticalAvailable) {
      layers.push({ id: "optical", label: "Optical (Sentinel-2)", kind: "unavailable", note: "No optical chip cached for this footprint." });
    } else {
      layers.push({ id: "optical", label: "Optical (Sentinel-2)", kind: "observed", note: "Context only; not an input to detection." });
    }
    layers.push({ id: "sar", label: "SAR image", kind: "observed", note: "Archive Sentinel-1 acquisition." });
    layers.push({ id: "mask", label: "Class mask", kind: "observed", note: "Detector class output." });
    return layers;
  }

  function empty(ctx) {
    ctx = ctx || {};
    var stages = STAGES.map(function (s) {
      return stage(s.id, "not_started", "No run yet. Pick a scene and run the analysis.");
    });
    return {
      contract: CONTRACT,
      contractStatus: "derived",
      contractNote: "No agreed five-stage analysis contract exists in this repository.",
      generatedAt: new Date().toISOString(),
      source: ctx.endpoints || { mode: "legacy", analysis: false, dossier: false },
      case: {
        jobId: null,
        sceneId: ctx.scene ? ctx.scene.id : null,
        title: ctx.scene ? ctx.scene.title : "No run yet",
        tSat: ctx.scene ? utc(ctx.scene.t_sat) : null,
        created: null, status: "idle", caseType: null, detector: null, totalMs: null, headcount: 0,
        primaryAreaKm2: null, cleanScene: null, configVersion: (ctx.health && ctx.health.version) || null
      },
      stages: stages,
      inputs: [],
      uncertainty: { origin: { available: false, reason: "No run yet." }, windows: [], detection: { reason: "No run yet." }, forcing: { available: false, limits: [] }, scores: { reason: "No run yet." } },
      candidates: [],
      assumptions: [],
      limitations: [],
      unavailable: [],
      provenance: { note: "", inputs: [] },
      model: {}, forcing: {},
      layers: buildLayers({}, null, false, false)
    };
  }

  /* --------------------------------------------------------- endpoint probe */

  function detect() {
    var found = { mode: "legacy", analysis: false, dossier: false, checkedAt: null, paths: [] };
    return fetch("/openapi.json", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (spec) {
        found.checkedAt = new Date().toISOString();
        if (!spec || !spec.paths) return found;
        var paths = Object.keys(spec.paths);
        found.paths = paths;
        found.analysis = paths.indexOf("/api/v1/analysis/{job_id}") >= 0;
        found.dossier = paths.indexOf("/api/v1/dossier/{job_id}/pdf") >= 0;
        found.mode = found.analysis ? "contract" : "legacy";
        return found;
      })
      .catch(function () {
        found.checkedAt = new Date().toISOString();
        return found;
      });
  }

  /* Fetch the analysis document: the versioned endpoint when it exists, else a
     local mapping of the current job document. Same shape either way. */
  function load(job, ctx) {
    ctx = ctx || {};
    if (ctx.endpoints && ctx.endpoints.analysis && job && job.job_id) {
      return fetch("/api/v1/analysis/" + encodeURIComponent(job.job_id), { cache: "no-store" })
        .then(function (r) { if (!r.ok) throw new Error("analysis endpoint " + r.status); return r.json(); })
        .then(function (doc) { doc.source = doc.source || { mode: "contract" }; return doc; })
        .catch(function () { return build(job, ctx); });
    }
    return Promise.resolve(build(job, ctx));
  }

  /* ------------------------------------------------------------ SHA-256 I/O */

  function bytesOf(input) {
    if (input instanceof Uint8Array) return input;
    if (input instanceof ArrayBuffer) return new Uint8Array(input);
    return new Uint8Array(input);
  }

  function sha256Hex(input) {
    var bytes = bytesOf(input);
    if (!(window.crypto && window.crypto.subtle && window.crypto.subtle.digest)) {
      return Promise.reject(new Error("Web Crypto is unavailable. Serve the console over http://127.0.0.1 or https, not a bare file:// page."));
    }
    return window.crypto.subtle.digest("SHA-256", bytes).then(function (buf) {
      return Array.prototype.map.call(new Uint8Array(buf), function (b) {
        return ("0" + b.toString(16)).slice(-2);
      }).join("");
    });
  }

  window.SentinelAdapter = {
    CONTRACT: CONTRACT,
    STAGES: STAGES,
    STAGE_STATUS: STAGE_STATUS,
    DATA_STATUS: DATA_STATUS,
    build: build,
    empty: empty,
    detect: detect,
    load: load,
    sha256Hex: sha256Hex,
    badge: badge,
    detectorName: detectorName,
    utils: { num: num, txt: txt, utc: utc, uniq: uniq, bytesOf: bytesOf }
  };
})();
