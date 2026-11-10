/* SentinelTrace — stage status, provenance, uncertainty and dossier UI
   ---------------------------------------------------------------------------
   Everything here renders from ONE object: the analysis document produced by
   js/adapter.js. No number is recomputed in this file, and nothing is written
   back into the job document.

   The module is additive. app.js keeps owning the Leaflet console; it emits
   `sentinel:job`, `sentinel:progress` and `sentinel:scene` events, and this file
   listens. If this script fails to load, the existing console still works.
*/
(function () {
  "use strict";

  var A = window.SentinelAdapter;
  var D = window.SentinelDossier;
  if (!A) { console.warn("SentinelTrace: adapter.js did not load; stage UI disabled"); return; }

  var state = {
    job: null,
    scene: null,
    analysis: A.empty({}),
    ctx: { health: null, config: null, scenes: [] },
    endpoints: { mode: "legacy", analysis: false, dossier: false, checkedAt: null },
    progress: null,
    dossier: null,
    dossierJob: null,
    building: false,
    radiusCircle: null
  };

  /* ---------------------------------------------------------------- helpers */

  function byId(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }

  function clear(node) { if (node) node.innerHTML = ""; }

  function fmt(v, d) {
    if (v === null || v === undefined || v === "" || (typeof v === "number" && !isFinite(v))) return "not available";
    if (typeof v === "number") return v.toFixed(d === undefined ? 2 : d);
    return String(v);
  }

  function statusBadge(status, opts) {
    opts = opts || {};
    var def = A.DATA_STATUS[status] || A.DATA_STATUS.missing;
    var n = el(opts.compact ? "span" : "span", "badge badge-" + def.tone + (opts.compact ? " compact" : ""));
    n.appendChild(el("span", "badge-ic", def.icon));
    n.appendChild(el("span", "badge-tx", def.label));
    n.title = def.help + (opts.source ? (" · source: " + opts.source) : "") +
      (opts.date ? (" · date: " + opts.date) : "") + (opts.note ? (" · " + opts.note) : "");
    if (opts.labelledBy) n.setAttribute("aria-label", def.label + (opts.source ? ", source " + opts.source : ""));
    return n;
  }

  function stageTone(status) {
    var d = A.STAGE_STATUS[status] || A.STAGE_STATUS.not_started;
    return d;
  }

  function kv(parent, key, value) {
    var row = el("div", "kv");
    row.appendChild(el("span", "k", key));
    row.appendChild(el("span", "v", value === null || value === undefined || value === "" ? "not available" : String(value)));
    parent.appendChild(row);
    return row;
  }

  function unavailableBlock(feature, reason) {
    var n = el("div", "unavail");
    n.appendChild(el("span", "unavail-ic", "\u2298"));
    var b = el("div", "unavail-body");
    b.appendChild(el("div", "unavail-t", feature));
    b.appendChild(el("div", "unavail-r", "Not available: " + (reason || "reason not recorded")));
    n.appendChild(b);
    return n;
  }

  /* ------------------------------------------------------------- page context */

  function getJSON(path) {
    return fetch(path, { headers: { Accept: "application/json" }, cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }

  function loadContext() {
    return Promise.all([
      A.detect().then(function (found) { state.endpoints = found; return found; }),
      getJSON("/api/health").catch(function () { return null; }),
      getJSON("/api/config").catch(function () { return null; }),
      getJSON("/api/scenes").catch(function () { return []; })
    ]).then(function (res) {
      state.ctx.health = res[1];
      state.ctx.config = res[2];
      state.ctx.scenes = res[3] || [];
      renderRouteBadge();
      renderDiagnostics();
      renderStrip(state.analysis);
      renderDossierCard();
    });
  }

  function sceneFor(id) {
    if (!id) return state.scene;
    var found = (state.ctx.scenes || []).filter(function (s) { return s.id === id; })[0];
    return found || state.scene;
  }

  function rebuild() {
    var job = state.job;
    if (!job) {
      state.analysis = A.empty({ scene: state.scene, health: state.ctx.health, endpoints: state.endpoints });
    } else {
      state.analysis = A.build(job, {
        scene: sceneFor((job.input || {}).scene_id),
        health: state.ctx.health,
        config: state.ctx.config,
        endpoints: state.endpoints
      });
      state.analysis.source = {
        mode: state.endpoints.mode,
        analysis: state.endpoints.analysis,
        dossier: state.endpoints.dossier
      };
    }
    renderAll();
  }

  function renderAll() {
    renderStrip(state.analysis);
    renderStageDetail();
    renderInputs();
    renderUncertainty();
    renderCandidateExtras();
    renderPanels();
    renderLegend();
    renderMapStatus();
    renderDiagnostics();
    renderMapRadius();
    renderDossierCard();
    scheduleDossier();
  }

  /* ----------------------------------------------------------- stage strip */

  var STEP_STAGE = {
    DETECT: "segment", CHAR: "segment", EO: "segment", RENDER: "segment",
    METOCEAN: "hindcast", HINDCAST: "hindcast", FORECAST: "hindcast",
    COAST: "hindcast", AGE_PROXY: "hindcast",
    AIS: "attribute", FILTER: "attribute", SCORE: "attribute", STAGE4: "attribute"
  };

  function liveStages() {
    var doc = state.analysis;
    var stages = (doc.stages || []).slice();
    if (!state.progress || !state.progress.running) return stages;
    var done = {};
    (state.progress.done || []).forEach(function (s) { done[s] = true; });
    return stages.map(function (s) {
      if (s.id === "ingest") return s;
      if (s.id === "present") return s;
      var current = STEP_STAGE[state.progress.step];
      var hasDone = Object.keys(done).some(function (k) { return STEP_STAGE[k] === s.id; });
      var copy = Object.assign({}, s);
      if (current === s.id) {
        copy.status = "running";
        copy.statusLabel = "Running";
        copy.statusIcon = "\u25D4";
        copy.tone = "run";
        copy.reason = "Step " + (state.progress.step || "") + " in flight" +
          (state.progress.index ? (" (" + state.progress.index + " of " + state.progress.total + ")") : "") + ".";
      } else if (hasDone) {
        copy.status = "done";
        copy.statusLabel = "Done";
        copy.statusIcon = "\u2713";
        copy.tone = "ok";
      } else {
        copy.status = "not_started";
        copy.statusLabel = "Not started";
        copy.statusIcon = "\u25CB";
        copy.tone = "idle";
        copy.reason = "Waiting for the run to reach this stage.";
      }
      return copy;
    });
  }

  function renderStrip(doc) {
    var box = byId("stage-strip");
    if (!box) return;
    clear(box);
    var stages = liveStages();
    stages.forEach(function (s) {
      var b = el("button", "stage-chip");
      b.type = "button";
      b.dataset.status = s.status;
      b.dataset.stage = s.id;
      b.setAttribute("aria-label", "Stage " + s.index + " " + s.name + ": " + s.statusLabel +
        (s.reason ? ". " + s.reason : ""));
      b.appendChild(el("span", "sc-ic", s.statusIcon));
      b.appendChild(el("span", "sc-name", s.index + " " + s.name));
      b.appendChild(el("span", "sc-st", s.statusLabel));
      var reason = el("span", "sc-reason");
      reason.appendChild(el("b", null, s.name + " · " + s.statusLabel));
      reason.appendChild(el("span", null, s.reason || "No reason recorded."));
      b.appendChild(reason);
      b.addEventListener("click", function () {
        openStage(s.id);
        var link = document.querySelector('.navlink[data-view="stages"]');
        if (link) link.click();
      });
      box.appendChild(b);
    });
    var route = byId("route-badge");
    if (route) route.dataset.mode = (doc.source && doc.source.mode) || "legacy";
  }

  function renderRouteBadge() {
    var badge = byId("route-badge");
    if (!badge) return;
    clear(badge);
    var mode = state.endpoints.mode;
    var defs = mode === "contract"
      ? { label: "Contract v1", icon: "\u2713", cls: "ok" }
      : { label: "Legacy route", icon: "\u26A0", cls: "warn" };
    badge.className = "route-badge " + defs.cls;
    badge.appendChild(el("span", "rb-ic", defs.icon));
    badge.appendChild(el("span", "rb-tx", defs.label));
    badge.title = mode === "contract"
      ? "Reading /api/v1/analysis/{job_id}."
      : "No /api/v1/analysis/{job_id} endpoint was found in /openapi.json, so the console maps the current " +
        "job document into the analysis shape locally. Diagnostics lists the probe result.";
    badge.setAttribute("aria-label", badge.title);
  }

  function openStage(id) {
    Array.prototype.forEach.call(document.querySelectorAll("#stage-detail details"), function (d) {
      if (d.dataset.stage === id) d.open = true;
    });
    var target = document.querySelector('#stage-detail details[data-stage="' + id + '"]');
    if (target && target.scrollIntoView) target.scrollIntoView({ block: "nearest" });
  }

  /* ----------------------------------------------------------- stage detail */

  function renderStageDetail() {
    var box = byId("stage-detail");
    if (!box) return;
    clear(box);
    var stages = liveStages();
    stages.forEach(function (s) {
      var d = el("details", "stagecard");
      d.dataset.stage = s.id;
      d.dataset.status = s.status;
      var sum = el("summary");
      sum.appendChild(el("span", "stagecard-ic", s.statusIcon));
      sum.appendChild(el("span", "stagecard-n", String(s.index)));
      var t = el("span", "stagecard-t");
      t.appendChild(el("b", null, s.name));
      t.appendChild(el("span", "stagecard-o", s.owner + " \u00B7 " + s.blurb));
      sum.appendChild(t);
      sum.appendChild(el("span", "stagecard-st", s.statusLabel));
      d.appendChild(sum);

      var body = el("div", "stagecard-b");
      body.appendChild(el("p", "stagecard-reason", s.reason || "No reason recorded."));
      if (s.detail) body.appendChild(el("p", "hint", s.detail));
      if (s.outputs && s.outputs.length) {
        var box2 = el("div", "stagecard-out");
        s.outputs.forEach(function (o) { kv(box2, o.label, o.value); });
        body.appendChild(box2);
      }
      body.appendChild(el("div", "stagecard-code", s.code));
      if (s.status === "unavailable") {
        body.appendChild(unavailableBlock(s.name, s.reason));
      }
      d.appendChild(body);
      box.appendChild(d);
    });
  }

  /* --------------------------------------------------------------- inputs */

  function renderInputs() {
    var doc = state.analysis;
    var compactBox = byId("input-badges");
    var fullBox = byId("data-badges");
    if (compactBox) {
      clear(compactBox);
      if (!(doc.inputs || []).length) {
        compactBox.appendChild(el("p", "hint", "Run the analysis to see per-input data status."));
      }
      (doc.inputs || []).forEach(function (i) {
        var row = el("div", "input-row");
        var left = el("div", "input-l");
        left.appendChild(el("span", "input-n", i.label));
        var meta = [];
        if (i.provenance.source) meta.push(i.provenance.source);
        if (i.provenance.date) meta.push(A.utils.utc(i.provenance.date) || i.provenance.date);
        if (meta.length) left.appendChild(el("span", "input-s", meta.join(" \u00B7 ")));
        row.appendChild(left);
        row.appendChild(statusBadge(i.provenance.status, {
          compact: true,
          source: i.provenance.source,
          date: i.provenance.date,
          note: i.provenance.note
        }));
        compactBox.appendChild(row);
      });
    }

    if (fullBox) {
      clear(fullBox);
      if (!(doc.inputs || []).length) {
        fullBox.appendChild(el("p", "hint", "No inputs recorded yet."));
      }
      (doc.inputs || []).forEach(function (i) {
        var card = el("div", "input-card");
        card.dataset.status = i.provenance.status;
        var head = el("div", "input-card-h");
        head.appendChild(el("span", "input-n", i.label));
        head.appendChild(statusBadge(i.provenance.status));
        card.appendChild(head);
        kv(card, "Used by", i.usedBy);
        kv(card, "Source", i.provenance.source);
        kv(card, "Date", i.provenance.date ? (A.utils.utc(i.provenance.date) || i.provenance.date) : null);
        if (i.provenance.note) card.appendChild(el("p", "hint", i.provenance.note));
        if (i.extra) card.appendChild(el("p", "input-extra", i.extra));
        fullBox.appendChild(card);
      });
    }
  }

  /* ---------------------------------------------------------- uncertainty */

  function uncertaintyNode(full) {
    var u = state.analysis.uncertainty || {};
    var wrap = el("div", "unc");

    var o = u.origin || {};
    var ob = el("div", "unc-block");
    ob.appendChild(el("h3", null, "Estimated origin"));
    if (o.available) {
      kv(ob, "Zone centre", fmt(o.lat, 4) + ", " + fmt(o.lon, 4));
      kv(ob, "Origin time", o.time);
      kv(ob, "Zone radius", o.radiusKm != null ? fmt(o.radiusKm, 2) + " km (90th pct)" : null);
      kv(ob, "Buffer", o.bufferKm != null ? fmt(o.bufferKm, 2) + " km" : null);
      kv(ob, "Zone area", o.areaKm2 != null ? fmt(o.areaKm2, 2) + " km\u00B2" : null);
      ob.appendChild(el("p", "hint", o.note || "Estimated zone, not a verified release point."));
      if (full) ob.appendChild(el("p", "hint", o.method || ""));
    } else {
      ob.appendChild(el("p", "hint", o.reason || "No origin estimate for this case."));
    }
    wrap.appendChild(ob);

    var wb = el("div", "unc-block");
    wb.appendChild(el("h3", null, "Time windows"));
    var windows = u.windows || [];
    if (!windows.length) wb.appendChild(el("p", "hint", "No time window is reported."));
    windows.forEach(function (w) {
      var line = el("div", "unc-window");
      line.appendChild(el("span", "k", w.label));
      var v = el("span", "v", (A.utils.utc(w.start) || "n/a") + " \u2192 " + (A.utils.utc(w.end) || "n/a"));
      line.appendChild(v);
      if (w.note) line.appendChild(el("span", "unc-note", w.note));
      wb.appendChild(line);
    });
    wrap.appendChild(wb);

    var db = el("div", "unc-block");
    db.appendChild(el("h3", null, "Detection confidence"));
    var det = u.detection || {};
    if (det.polygons) {
      kv(db, "Oil polygons", det.polygons);
      kv(db, "Per-polygon confidence", det.bestConfidence != null ? fmt(det.bestConfidence, 3) : null);
      kv(db, "Method", det.method);
      db.appendChild(el("p", "hint", det.note || ""));
    } else {
      db.appendChild(el("p", "hint", det.reason || "No detection confidence."));
    }
    wrap.appendChild(db);

    var sb = el("div", "unc-block");
    sb.appendChild(el("h3", null, "Score confidence"));
    var sc = u.scores || {};
    if (sc.max !== undefined && sc.max !== null) {
      kv(sb, "Top ranked score", fmt(sc.max, 1) + " of 100");
      kv(sb, "Top track confidence", sc.confidence != null ? fmt(sc.confidence, 3) : null);
      sb.appendChild(el("p", "hint", sc.note || ""));
    } else {
      sb.appendChild(el("p", "hint", sc.reason || "No candidate was scored."));
    }
    wrap.appendChild(sb);

    var fb = el("div", "unc-block");
    fb.appendChild(el("h3", null, "Forcing limits"));
    var f = u.forcing || {};
    if (!f.available) {
      fb.appendChild(el("p", "hint", "No forcing field is reported for this case."));
    } else {
      kv(fb, "Source", f.source);
      kv(fb, "Cube window", f.cube);
      kv(fb, "Synthetic field", f.synthetic ? "YES" : "no");
      kv(fb, "Covers footprint/time", f.coversScene === null || f.coversScene === undefined ? null : (f.coversScene ? "yes" : "no"));
      kv(fb, "Wave forcing", f.stokes ? "yes" : "no (Stokes omitted)");
      (f.limits || []).forEach(function (l) { fb.appendChild(el("div", "unc-limit", l)); });
    }
    wrap.appendChild(fb);
    return wrap;
  }

  function renderUncertainty() {
    [byId("uncertainty"), byId("uncertainty-full")].forEach(function (box, i) {
      if (!box) return;
      clear(box);
      box.appendChild(uncertaintyNode(i === 1));
    });
  }

  /* ------------------------------------------------- candidate evidence plus */

  function renderCandidateExtras() {
    var wrap = byId("suspects");
    if (!wrap) return;
    Array.prototype.forEach.call(wrap.querySelectorAll(".evi-plus"), function (n) { n.remove(); });
    var byMmsi = {};
    (state.analysis.candidates || []).forEach(function (c) { byMmsi[c.mmsi] = c; });

    Array.prototype.forEach.call(wrap.querySelectorAll(".suspect"), function (card) {
      var c = byMmsi[String(card.dataset.mmsi)];
      if (!c) return;
      var box = el("div", "evi-plus");
      box.appendChild(el("div", "evi-h", "Evidence detail"));

      var cov = el("div", "evi-block");
      cov.appendChild(el("div", "evi-k", "Track coverage"));
      cov.appendChild(el("div", "evi-v",
        (c.coverage.receivedPositions != null ? c.coverage.receivedPositions + " received positions" : "positions not reported") +
        (c.coverage.deadReckonedFraction != null
          ? " \u00B7 " + fmt(c.coverage.deadReckonedFraction * 100, 1) + "% dead reckoned" : "") +
        (c.coverage.gaps ? " \u00B7 " + c.coverage.gaps + " gap(s)" : "")));
      if (c.coverage.timeOverlapMinutes != null) {
        cov.appendChild(el("div", "evi-v",
          fmt(c.coverage.timeOverlapMinutes, 1) + " min in search radius (" +
          fmt(c.coverage.receivedOverlapMinutes, 1) + " min received)"));
      }
      if (c.evidenceQuality) {
        cov.appendChild(el("div", "evi-v", "Evidence quality: " + c.evidenceQuality +
          " (rule: low below 6 receptions or confidence < 0.5; high at >= 0.8)"));
      }
      box.appendChild(cov);

      if (c.assumptions && c.assumptions.length) {
        var det = el("details", "evi-det");
        det.appendChild(el("summary", null, "Assumptions for this candidate (" + c.assumptions.length + ")"));
        c.assumptions.forEach(function (a) { det.appendChild(el("div", "evi-li", a)); });
        box.appendChild(det);
      } else {
        box.appendChild(el("div", "evi-v", "No candidate-specific assumption is recorded."));
      }

      var un = (c.unavailable || []).slice();
      if (c.darkTarget && c.darkTarget.status === "unavailable" && c.darkTarget.reason &&
          !un.some(function (x) { return x.indexOf("dark_target") === 0; })) {
        un.push("dark_target_match: " + c.darkTarget.reason);
      }
      if (un.length) {
        var ud = el("details", "evi-det");
        ud.appendChild(el("summary", null, "Not available for this candidate (" + un.length + ")"));
        un.forEach(function (x) { ud.appendChild(el("div", "evi-li unavail-tx", x)); });
        box.appendChild(ud);
      }
      card.appendChild(box);
    });
  }

  /* ------------------------------------------------- assumptions / limits */

  function listNode(items, cls, prefix) {
    var box = el("div", cls || "simple-list");
    if (!items || !items.length) {
      box.appendChild(el("p", "hint", "Nothing recorded for this case."));
      return box;
    }
    items.forEach(function (x) {
      var row = el("div", "simple-li");
      row.appendChild(el("span", "simple-ic", prefix || "\u2022"));
      row.appendChild(el("span", null, String(x)));
      box.appendChild(row);
    });
    return box;
  }

  function renderPanels() {
    var doc = state.analysis;
    var ab = byId("assumptions-panel");
    if (ab) { clear(ab); ab.appendChild(listNode(doc.assumptions)); }
    var lb = byId("limitations-panel");
    if (lb) { clear(lb); lb.appendChild(listNode(doc.limitations)); }
    var ub = byId("unavailable-panel");
    if (ub) {
      clear(ub);
      var list = doc.unavailable || [];
      if (!list.length) ub.appendChild(el("p", "hint", "Nothing is marked unavailable for this case."));
      list.forEach(function (u) { ub.appendChild(unavailableBlock(u.feature, u.reason)); });
    }
    var nb = byId("not-established");
    if (nb) {
      clear(nb);
      [
        "that any vessel caused this spill, or that anyone is guilty;",
        "a release point or release time (the origin is an estimated zone);",
        "the volume released, or a chemical age for the slick;",
        "that AIS coverage was complete (a gap is a missing broadcast);",
        "that the detection is complete (look-alikes separate only on the baseline path);",
        "that the file is unaltered since it left this machine beyond the SHA-256 byte check."
      ].forEach(function (t) {
        var row = el("div", "simple-li");
        row.appendChild(el("span", "simple-ic", "\u2715"));
        row.appendChild(el("span", null, "It does not establish " + t));
        nb.appendChild(row);
      });
    }
  }

  /* ------------------------------------------------------------ map legend */

  var KIND = {
    observed: { label: "Observed", icon: "\u25CF", cls: "obs" },
    model: { label: "Modelled", icon: "\u25C7", cls: "mod" },
    simulated: { label: "Simulated", icon: "\u2248", cls: "sim" },
    unavailable: { label: "Not available", icon: "\u2298", cls: "na" }
  };

  function renderLegend() {
    var box = byId("legend-status");
    if (!box) return;
    clear(box);
    var layers = (state.analysis.layers || []).slice();
    var order = ["observed", "model", "simulated", "unavailable"];
    order.forEach(function (kind) {
      var group = layers.filter(function (l) { return l.kind === kind; });
      if (!group.length) return;
      var h = el("div", "legend-h legend-" + kind);
      h.appendChild(el("span", "legend-ic", KIND[kind].icon));
      h.appendChild(el("span", null, KIND[kind].label));
      box.appendChild(h);
      group.forEach(function (l) {
        var row = el("div", "legend-row");
        row.appendChild(el("span", "legend-ic", KIND[kind].icon));
        var t = el("span", "legend-t", l.label);
        t.title = l.note || "";
        row.appendChild(t);
        box.appendChild(row);
      });
    });
    var note = el("p", "legend-note",
      "A simulated or modelled layer is never drawn as an observed one. Tick the boxes above to show or hide each layer.");
    box.appendChild(note);
  }

  function renderMapStatus() {
    var box = byId("map-status");
    if (!box) return;
    clear(box);
    var inputs = state.analysis.inputs || [];
    var pick = { sar_scene: "SAR", ais: "AIS", wind: "Wind", model: "Model" };
    Object.keys(pick).forEach(function (id) {
      var i = inputs.filter(function (x) { return x.id === id; })[0];
      if (!i) return;
      var chip = el("div", "map-badge");
      chip.appendChild(el("span", "map-badge-k", pick[id]));
      chip.appendChild(statusBadge(i.provenance.status, { compact: true }));
      chip.title = i.label + ": " + i.provenance.status.toUpperCase() +
        (i.provenance.source ? (" · " + i.provenance.source) : "");
      box.appendChild(chip);
    });
  }

  function renderMapRadius() {
    var app = window.__sentinel;
    if (!app || !app.map || !app.layers || !app.layers.origin) return;
    if (state.radiusCircle) {
      app.layers.origin.removeLayer(state.radiusCircle);
      state.radiusCircle = null;
    }
    var o = (state.analysis.uncertainty || {}).origin || {};
    if (!o.available || o.radiusKm == null || o.lat == null || o.lon == null) return;
    if (typeof L === "undefined") return;
    state.radiusCircle = L.circle([o.lat, o.lon], {
      radius: o.radiusKm * 1000,
      color: "#e8734a", weight: 1, dashArray: "2,5", opacity: 0.75,
      fill: false, interactive: true
    }).bindTooltip(
      "Displayed uncertainty radius " + fmt(o.radiusKm, 1) + " km \u00B7 90th-percentile particle distance \u00B7 uncalibrated",
      { sticky: true }
    );
    state.radiusCircle.addTo(app.layers.origin);
  }

  /* ----------------------------------------------------------- diagnostics */

  function renderDiagnostics() {
    var box = byId("diagnostics");
    if (!box) return;
    clear(box);
    var e = state.endpoints || {};
    var rows = [
      ["Analysis endpoint", e.analysis ? "present (/api/v1/analysis/{job_id})" : "absent — legacy mapping"],
      ["Dossier endpoint", e.dossier ? "present (/api/v1/dossier/{job_id}/pdf)" : "absent — dossier built in the browser"],
      ["Probe source", "/openapi.json at " + (e.checkedAt || "not checked")],
      ["Mode in use", e.mode === "contract" ? "contract" : "legacy route"],
      ["Analysis document", state.analysis.contract + " (derived)"],
      ["Rendered job", (state.analysis.case || {}).jobId || "none"],
      ["Dossier format", "PDF (PDF/A not validated, so not claimed)"],
      ["PDF digest", state.dossier ? state.dossier.sha : "not generated yet"]
    ];
    rows.forEach(function (r) { kv(box, r[0], r[1]); });
    var status = el("div", "diag-status " + (e.mode === "contract" ? "ok" : "warn"));
    status.appendChild(el("span", "diag-ic", e.mode === "contract" ? "\u2713" : "\u26A0"));
    status.appendChild(el("span", null, e.mode === "contract"
      ? "Using the versioned analysis endpoint."
      : "Using legacy routes. Responses are mapped into the analysis shape locally; no data is invented."));
    box.insertBefore(status, box.firstChild);
  }

  /* -------------------------------------------------------------- dossier */

  function scheduleDossier() {
    if (!state.job) { state.dossier = null; state.dossierJob = null; renderDossierCard(); return; }
    if (state.dossierJob === state.job.job_id && state.dossier) return;
    if (state.building) return;
    state.building = true;
    renderDossierCard();
    var analysis = state.analysis;
    Promise.resolve().then(function () {
      if (!D) throw new Error("dossier writer did not load");
      var out = D.build(analysis);
      return A.sha256Hex(out.bytes).then(function (hex) {
        out.sha = hex;
        out.jobId = (analysis.case || {}).jobId;
        out.builtAt = new Date().toISOString();
        return out;
      });
    }).then(function (out) {
      state.dossier = out;
      state.dossierJob = out.jobId;
      state.building = false;
      renderDossierCard();
      renderDiagnostics();
    }).catch(function (err) {
      state.building = false;
      state.dossier = null;
      renderDossierCard(err);
    });
  }

  function bytesHuman(n) {
    if (n == null) return "not available";
    if (n < 1024) return n + " B";
    return (n / 1024).toFixed(1) + " KB";
  }

  function renderDossierCard(err) {
    var card = byId("dossier-card");
    if (!card) return;
    clear(card);
    if (!state.job) {
      card.appendChild(el("p", "hint", "Run the analysis to generate a dossier for the case."));
      var d0 = byId("dossier-download");
      if (d0) { d0.setAttribute("aria-disabled", "true"); d0.removeAttribute("href"); }
      return;
    }
    if (state.building) {
      card.appendChild(el("p", "hint", "Generating the PDF from the analysis document…"));
      return;
    }
    if (err) {
      card.appendChild(el("div", "notice bad", "Dossier could not be generated: " + err.message));
      return;
    }
    if (!state.dossier) {
      card.appendChild(el("p", "hint", "No dossier has been generated for this case yet."));
      return;
    }

    var d = state.dossier;
    var meta = el("div", "dossier-meta");
    kv(meta, "File", d.filename);
    kv(meta, "Format", "PDF (not PDF/A; no PDF/A validation was run)");
    kv(meta, "Bytes", bytesHuman(d.bytes.length));
    kv(meta, "Generated", d.builtAt.replace("T", " ").replace(/\..*/, " UTC"));
    card.appendChild(meta);

    var shaBox = el("div", "sha-box");
    shaBox.appendChild(el("div", "sha-k", "SHA-256 of these exact bytes"));
    var code = el("code", "sha-v");
    code.id = "dossier-sha";
    code.textContent = d.sha;
    shaBox.appendChild(code);
    var btns = el("div", "sha-actions");
    var copy = el("button", "mini", "Copy digest");
    copy.type = "button";
    copy.addEventListener("click", function () {
      var done = function () { copy.textContent = "Copied"; setTimeout(function () { copy.textContent = "Copy digest"; }, 1500); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(d.sha).then(done).catch(fallback);
      } else { fallback(); }
      function fallback() {
        var r = document.createRange();
        r.selectNodeContents(code);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(r);
        copy.textContent = "Selected — press Ctrl+C";
      }
    });
    btns.appendChild(copy);
    shaBox.appendChild(btns);
    card.appendChild(shaBox);

    var dl = byId("dossier-download");
    if (dl) {
      var blob = new Blob([d.bytes], { type: "application/pdf" });
      if (dl._url) URL.revokeObjectURL(dl._url);
      dl._url = URL.createObjectURL(blob);
      dl.href = dl._url;
      dl.download = d.filename;
      dl.setAttribute("aria-disabled", "false");
      dl.classList.add("ready");
    }
    card.appendChild(el("p", "hint",
      "The PDF is written from the same analysis document this page renders. Generate and download are the same bytes, so the digest above is the digest of the file you save."));
  }

  function verifyResult(kind, title, detail) {
    var box = byId("verify-result");
    if (!box) return;
    clear(box);
    box.className = "verify-result " + kind;
    var ic = el("span", "verify-ic", kind === "match" ? "\u2713" : (kind === "mismatch" ? "\u2715" : "\u2026"));
    box.appendChild(ic);
    var body = el("div", "verify-body");
    body.appendChild(el("div", "verify-t", title));
    if (detail) body.appendChild(el("div", "verify-d", detail));
    box.appendChild(body);
    box.setAttribute("role", "status");
    box.setAttribute("aria-live", "polite");
  }

  function verifyBytes(bytes) {
    if (!state.dossier) {
      verifyResult("mismatch", "MISMATCH", "No dossier digest is published for this case, so nothing can be compared.");
      return;
    }
    A.sha256Hex(bytes).then(function (hex) {
      var same = hex.toLowerCase() === state.dossier.sha.toLowerCase();
      if (same) {
        verifyResult("match", "MATCH",
          "The SHA-256 computed from the selected bytes equals the published digest. The file is byte-identical to the one generated here.");
      } else {
        verifyResult("mismatch", "MISMATCH",
          "Computed " + hex + " — published " + state.dossier.sha + ". The bytes differ from the generated dossier.");
      }
      var detail = byId("verify-hash");
      if (detail) detail.textContent = hex;
    }).catch(function (e) {
      verifyResult("mismatch", "Could not hash the file", e.message);
    });
  }

  function bindVerifier() {
    var input = byId("verify-file");
    if (input) {
      input.addEventListener("change", function () {
        var f = input.files && input.files[0];
        if (!f) return;
        verifyResult("working", "Checking…", "Hashing " + f.name + " (" + bytesHuman(f.size) + ") with the Web Crypto API.");
        var reader = new FileReader();
        reader.onload = function () { verifyBytes(new Uint8Array(reader.result)); };
        reader.onerror = function () { verifyResult("mismatch", "Could not read the file", "The browser refused to read it."); };
        reader.readAsArrayBuffer(f);
      });
    }
    var self = byId("verify-selftest");
    if (self) {
      self.addEventListener("click", function () {
        if (!state.dossier) return;
        var altered = new Uint8Array(state.dossier.bytes);
        var at = Math.floor(altered.length / 2);
        altered[at] = altered[at] ^ 0x01;   // one bit, in one byte
        verifyResult("working", "Checking a deliberately altered copy…", "One byte was changed before hashing.");
        A.sha256Hex(altered).then(function (hex) {
          var same = hex.toLowerCase() === state.dossier.sha.toLowerCase();
          verifyResult(same ? "match" : "mismatch", same ? "MATCH" : "MISMATCH",
            same ? "Unexpected: changing a byte did not change the digest."
              : "One byte changed, so the digest no longer matches the published SHA-256. This is the failure case of the verifier.");
        });
      });
    }
    var rebuild = byId("dossier-rebuild");
    if (rebuild) {
      rebuild.addEventListener("click", function () {
        state.dossierJob = null;
        scheduleDossier();
      });
    }
  }

  /* ------------------------------------------------------------- event glue */

  function applyJob(job) {
    state.job = job || null;
    state.progress = null;
    if (!job) {
      state.dossier = null;
      state.dossierJob = null;
    }
    rebuild();
  }

  function init() {
    bindVerifier();
    document.addEventListener("sentinel:job", function (e) { applyJob(e.detail && e.detail.job); });
    document.addEventListener("sentinel:progress", function (e) { state.progress = e.detail; renderStrip(state.analysis); renderStageDetail(); });
    document.addEventListener("sentinel:scene", function (e) {
      state.scene = e.detail && e.detail.scene;
      if (!state.job) rebuild();
      renderMapStatus();
    });
    document.addEventListener("click", function (e) {
      var link = e.target.closest ? e.target.closest("[data-view]") : null;
      if (link && link.dataset.view === "dossier") scheduleDossier();
    });
    // Start from a placeholder so every panel exists before the first run.
    renderStrip(state.analysis);
    renderStageDetail();
    renderInputs();
    renderUncertainty();
    renderPanels();
    renderLegend();
    renderMapStatus();
    renderDiagnostics();
    renderDossierCard();
    loadContext();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { setTimeout(init, 0); });
  } else {
    setTimeout(init, 0);
  }
})();
