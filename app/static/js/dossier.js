/* SentinelTrace dossier PDF
   ---------------------------------------------------------------------------
   The dossier is rendered from the analysis document the console already drew.
   It does no physics, no scoring and no recomputation: `Dossier.blocks()` reads
   only fields that are on the object handed to it.

   PDF/A IS NOT CLAIMED. This writer emits a plain PDF 1.4 (Helvetica/Courier
   base-14 fonts, no embedded fonts, no XMP, no output intent). No PDF/A
   validator has been run against it, so every label says "PDF".

   The file deliberately does not contain its own SHA-256: a file cannot hold its
   own digest. The digest of these exact bytes is published in the console and
   written next to the download, and the console can recompute it from the bytes
   the user selects. That is an integrity check only.
*/
(function () {
  "use strict";

  var PAGE_W = 595;
  var PAGE_H = 842;
  var MARGIN = 48;
  var BOTTOM = 58;

  /* --------------------------------------------------------------- text prep */

  var REPL = [
    ["\u00B0", " deg"], ["\u00B1", "+/-"], ["\u00B2", "2"], ["\u00B3", "3"],
    ["\u00B7", "-"], ["\u2013", "-"], ["\u2014", "-"], ["\u2018", "'"],
    ["\u2019", "'"], ["\u201C", '"'], ["\u201D", '"'], ["\u00D7", "x"],
    ["\u2265", ">="], ["\u2264", "<="], ["\u2192", "->"], ["\u2248", "~"],
    ["\u2713", "[ok]"], ["\u2715", "[x]"], ["\u25CF", "*"], ["\u25CB", "-"],
    ["\u00A0", " "], ["\u2026", "..."]
  ];

  function ascii(s) {
    var out = String(s === null || s === undefined ? "" : s);
    REPL.forEach(function (r) { out = out.split(r[0]).join(r[1]); });
    out = out.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, " ");
    var safe = "";
    for (var i = 0; i < out.length; i++) {
      var c = out.charCodeAt(i);
      safe += (c >= 32 && c <= 126) ? out.charAt(i) : "?";
    }
    return safe;
  }

  function esc(s) {
    return ascii(s).replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
  }

  function wrap(text, maxChars) {
    var clean = ascii(text).replace(/\s+/g, " ").trim();
    if (!clean) return [""];
    var words = clean.split(" ");
    var lines = [];
    var line = "";
    words.forEach(function (w) {
      if (!line.length) { line = w; return; }
      if ((line + " " + w).length <= maxChars) { line += " " + w; }
      else { lines.push(line); line = w; }
    });
    if (line.length) lines.push(line);
    return lines;
  }

  /* ------------------------------------------------------------- PDF writer */

  function Pdf() {
    this.pages = [];
    this.page = null;
    this.y = 0;
    this.addPage();
  }

  Pdf.prototype.addPage = function () {
    this.page = [];
    this.pages.push(this.page);
    this.y = PAGE_H - MARGIN;
  };

  Pdf.prototype.space = function (pt) {
    this.y -= pt;
    if (this.y < BOTTOM + 14) this.addPage();
  };

  Pdf.prototype.line = function (text, opts) {
    opts = opts || {};
    var font = opts.font || "F1";
    var size = opts.size || 9;
    var indent = opts.indent || 0;
    var widthPer = font === "F3" ? size * 0.60 : (font === "F2" ? size * 0.54 : size * 0.50);
    var usable = PAGE_W - MARGIN * 2 - indent;
    var maxChars = Math.max(20, Math.floor(usable / widthPer));
    var lead = opts.lead || (size + 3.2);
    var lines = wrap(text, maxChars);
    var self = this;

    lines.forEach(function (ln) {
      if (self.y - lead < BOTTOM) self.addPage();
      self.page.push({
        f: font, s: size, x: MARGIN + indent, y: self.y, t: ln,
        c: opts.color || null
      });
      self.y -= lead;
    });
  };

  Pdf.prototype.h1 = function (text) {
    this.space(6);
    this.line(text, { font: "F2", size: 19, color: [0.07, 0.11, 0.15], lead: 24 });
    this.y -= 4;
  };

  Pdf.prototype.h2 = function (text) {
    if (this.y < BOTTOM + 90) this.addPage();
    this.space(10);
    this.line(String(text).toUpperCase(), { font: "F2", size: 8.5, color: [0.45, 0.30, 0.16], lead: 13 });
    this.rule();
    this.y -= 2;
  };

  Pdf.prototype.h3 = function (text) {
    if (this.y < BOTTOM + 70) this.addPage();
    this.space(6);
    this.line(text, { font: "F2", size: 10, color: [0.09, 0.13, 0.18], lead: 14 });
  };

  Pdf.prototype.p = function (text, opts) {
    this.line(text, Object.assign({ size: 9, lead: 12.4 }, opts || {}));
  };

  Pdf.prototype.bullet = function (text) {
    var lines = wrap(text, 92);
    var self = this;
    lines.forEach(function (ln, i) {
      if (self.y - 12.4 < BOTTOM) self.addPage();
      self.page.push({
        f: "F1", s: 9, x: MARGIN + 8, y: self.y, t: (i === 0 ? "- " : "  ") + ln, c: null
      });
      self.y -= 12.4;
    });
  };

  Pdf.prototype.kv = function (key, value) {
    var k = ascii(key) + ": ";
    var v = ascii(value === null || value === undefined || value === "" ? "not available" : value);
    var lines = wrap(k + v, 96);
    var self = this;
    lines.forEach(function (ln, i) {
      if (self.y - 12 < BOTTOM) self.addPage();
      self.page.push({ f: i === 0 ? "F2" : "F1", s: 8.7, x: MARGIN + 4, y: self.y, t: ln, c: null });
      self.y -= 12;
    });
    // The value is also printed in plain body so a long value stays readable.
  };

  Pdf.prototype.mono = function (text) {
    this.line(text, { font: "F3", size: 8.2, lead: 11.2, color: [0.20, 0.24, 0.28] });
  };

  Pdf.prototype.rule = function () {
    if (this.y - 6 < BOTTOM) this.addPage();
    this.page.push({ rule: true, x: MARGIN, y: this.y + 3, w: PAGE_W - MARGIN * 2 });
    this.y -= 6;
  };

  Pdf.prototype.finish = function (footer) {
    var pages = this.pages;
    var total = pages.length;
    var objects = {};
    var next = 1;
    var catNum = next++;
    var pagesNum = next++;
    var f1 = next++;
    var f2 = next++;
    var f3 = next++;
    var pageNums = [];

    pages.forEach(function (commands, index) {
      var ops = [];
      commands.forEach(function (c) {
        if (c.rule) {
          ops.push("0.72 0.75 0.78 RG 0.6 w " + c.x + " " + c.y + " m " + (c.x + c.w) + " " + c.y + " l S");
          return;
        }
        var color = c.c ? c.c.join(" ") + " rg" : "0.12 0.16 0.20 rg";
        ops.push(color + " BT /" + c.f + " " + c.s + " Tf 1 0 0 1 " +
          round(c.x) + " " + round(c.y) + " Tm (" + esc(c.t) + ") Tj ET");
      });
      // Footer, added once the page count is known.
      ops.push("0.55 0.58 0.62 rg BT /F1 7.5 Tf 1 0 0 1 " + MARGIN + " 30 Tm (" +
        esc(footer + "  |  page " + (index + 1) + " of " + total) + ") Tj ET");

      var content = ops.join("\n");
      var cNum = next++;
      objects[cNum] = "<< /Length " + content.length + " >>\nstream\n" + content + "\nendstream";
      var pNum = next++;
      objects[pNum] = "<< /Type /Page /Parent " + pagesNum + " 0 R /MediaBox [0 0 " +
        PAGE_W + " " + PAGE_H + "] /Resources << /Font << /F1 " + f1 + " 0 R /F2 " + f2 +
        " 0 R /F3 " + f3 + " 0 R >> >> /Contents " + cNum + " 0 R >>";
      pageNums.push(pNum);
    });

    objects[catNum] = "<< /Type /Catalog /Pages " + pagesNum + " 0 R >>";
    objects[pagesNum] = "<< /Type /Pages /Kids [" +
      pageNums.map(function (n) { return n + " 0 R"; }).join(" ") + "] /Count " + pageNums.length + " >>";
    objects[f1] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>";
    objects[f2] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>";
    objects[f3] = "<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>";

    var max = next - 1;
    var out = "%PDF-1.4\n";
    var offsets = [];
    for (var n = 1; n <= max; n++) {
      offsets[n] = out.length;
      out += n + " 0 obj\n" + objects[n] + "\nendobj\n";
    }
    var xrefAt = out.length;
    out += "xref\n0 " + (max + 1) + "\n";
    out += "0000000000 65535 f \n";
    for (var i = 1; i <= max; i++) {
      out += ("0000000000" + offsets[i]).slice(-10) + " 00000 n \n";
    }
    out += "trailer\n<< /Size " + (max + 1) + " /Root " + catNum + " 0 R >>\n";
    out += "startxref\n" + xrefAt + "\n%%EOF\n";

    var bytes = new Uint8Array(out.length);
    for (var j = 0; j < out.length; j++) bytes[j] = out.charCodeAt(j) & 0xff;
    return bytes;
  };

  function round(v) { return Math.round(v * 100) / 100; }

  /* --------------------------------------------------------- document model */

  function fmtNum(v, d) {
    if (v === null || v === undefined || (typeof v === "number" && !isFinite(v))) return null;
    if (typeof v === "number") return v.toFixed(d === undefined ? 2 : d);
    return String(v);
  }

  function statusText(s) {
    if (!s) return "not available";
    return (s.label || s.status || "not available") + (s.source ? (" - " + s.source) : "") +
      (s.date ? (" - " + s.date) : "");
  }

  function rangeText(r, unit) {
    if (!r || r.nominal === null || r.nominal === undefined) return "not available";
    return fmtNum(r.min, 2) + " to " + fmtNum(r.max, 2) + " " + unit + " (nominal " + fmtNum(r.nominal, 2) + ")";
  }

  function blocks(a) {
    var b = [];
    var c = a.case || {};
    var u = a.uncertainty || {};
    var m = a.model || {};
    var f = a.forcing || {};

    b.push({ kind: "h1", text: "SentinelTrace dossier" });
    b.push({ kind: "p", text: "Case " + (c.jobId || "not available") + " - " + (c.title || "untitled scene"), size: 10 });
    b.push({ kind: "p", text: "Investigation aid. Not a finding of guilt and not proof of causation.", size: 9, color: [0.55, 0.28, 0.16] });
    b.push({ kind: "mono", text: "Document contract: " + a.contract + " (derived in the console; no separate agreed five-stage contract exists in this repository)" });
    b.push({ kind: "mono", text: "Generated from the same analysis document the console renders. No recomputation." });

    /* 1 ---------------------------------------------------------------- case */
    b.push({ kind: "h2", text: "1. Case metadata" });
    b.push({ kind: "kv", key: "Job id", value: c.jobId });
    b.push({ kind: "kv", key: "Scene", value: c.sceneId });
    b.push({ kind: "kv", key: "Acquisition (UTC)", value: c.tSat });
    b.push({ kind: "kv", key: "Run created (UTC)", value: c.created });
    b.push({ kind: "kv", key: "Run status", value: c.status });
    b.push({ kind: "kv", key: "Case type", value: c.caseType || "not reported by this job" });
    b.push({ kind: "kv", key: "Detector", value: c.detector || "not reported" });
    b.push({ kind: "kv", key: "Console version", value: c.configVersion || "not reported" });
    b.push({ kind: "kv", key: "Wall time", value: c.totalMs != null ? (c.totalMs / 1000).toFixed(1) + " s" : "not reported" });

    /* 2 -------------------------------------------------------------- result */
    b.push({ kind: "h2", text: "2. Result in brief" });
    if (c.cleanScene) {
      b.push({ kind: "p", text: (c.cleanScene.headline || "No slick detected.") + " " + (c.cleanScene.detail || "") });
      b.push({ kind: "p", text: "An empty detection is a reported result. Drift and attribution were not run because there is no slick to trace." });
    } else if (c.primaryAreaKm2 !== null && c.primaryAreaKm2 !== undefined) {
      b.push({ kind: "p", text: "Total slick area reported by the detector: " + fmtNum(c.primaryAreaKm2, 3) + " km2." });
      if (u.origin && u.origin.available) {
        b.push({ kind: "p", text: "Estimated release zone centre " + fmtNum(u.origin.lat, 4) + ", " +
          fmtNum(u.origin.lon, 4) + " at " + u.origin.time + ". Estimated, not verified." });
      }
      if (a.candidates && a.candidates.length) {
        var top = a.candidates[0];
        b.push({ kind: "p", text: "Lead candidate: " + (top.name || "UNKNOWN") + " (MMSI " + top.mmsi + "), ranked score " +
          fmtNum(top.score, 1) + " of 100, track confidence " + fmtNum((top.confidence != null ? top.confidence : 1) * 100, 0) +
          " percent. Ranked lead only, not an attribution." });
      } else {
        b.push({ kind: "p", text: "No vessel passed the spatio-temporal filter. No suspect is reported rather than forcing one." });
      }
    } else {
      b.push({ kind: "p", text: "No result is reported for this case." });
    }

    /* 3 -------------------------------------------------------------- stages */
    b.push({ kind: "h2", text: "3. Stage results" });
    (a.stages || []).forEach(function (s) {
      b.push({ kind: "h3", text: s.index + ". " + s.name + " (" + s.owner + ") - " + s.statusLabel });
      if (s.reason) b.push({ kind: "p", text: s.reason });
      (s.outputs || []).forEach(function (o) {
        b.push({ kind: "kv", key: o.label, value: o.value });
      });
    });

    /* 4 ----------------------------------------------------------- provenance */
    b.push({ kind: "h2", text: "4. Input provenance and data status" });
    b.push({ kind: "p", text: "REAL means measured or recorded. SIMULATED means generated and never presented as observed. MISSING means the input is not present for this case." });
    (a.inputs || []).forEach(function (i) {
      var s = i.provenance || {};
      b.push({ kind: "h3", text: i.label + " [" + (s.label || "MISSING") + "]" });
      b.push({ kind: "kv", key: "Used by", value: i.usedBy });
      b.push({ kind: "kv", key: "Status", value: statusText(s) });
      if (s.note) b.push({ kind: "kv", key: "Note", value: s.note });
      if (i.extra) b.push({ kind: "kv", key: "Detail", value: i.extra });
    });

    /* 5 --------------------------------------------------------- model/forcing */
    b.push({ kind: "h2", text: "5. Model and forcing metadata" });
    b.push({ kind: "kv", key: "Detector", value: m.detector });
    b.push({ kind: "kv", key: "Checkpoint", value: m.checkpoint || (m.baseline ? "not loaded - dB baseline ran" : "not reported") });
    b.push({ kind: "kv", key: "Checkpoint SHA-256", value: m.checkpointSha256 || "not reported by this job" });
    b.push({ kind: "kv", key: "Fallback reason", value: m.fallbackReason || "n/a" });
    b.push({ kind: "kv", key: "Metric provenance", value: m.metricsNote });
    if (m.reportedMetrics) {
      Object.keys(m.reportedMetrics).forEach(function (k) {
        b.push({ kind: "kv", key: "Reported " + k, value: fmtNum(m.reportedMetrics[k], 4) });
      });
    }
    b.push({ kind: "kv", key: "Forcing source", value: f.source || "not reported" });
    b.push({ kind: "kv", key: "Forcing cube window", value: f.cube || "not reported" });
    b.push({ kind: "kv", key: "Forcing synthetic", value: f.synthetic ? "YES - constant substitute field" : "no" });
    b.push({ kind: "kv", key: "Currents present", value: f.hasCurrents ? "yes" : "no" });
    b.push({ kind: "kv", key: "Wave forcing present", value: f.hasWaves ? "yes" : "no - Stokes omitted" });
    b.push({ kind: "kv", key: "Covers scene footprint and time", value: f.coversScene === null || f.coversScene === undefined ? "not reported" : (f.coversScene ? "yes" : "no - edge values clamped") });
    b.push({ kind: "kv", key: "Mean wind", value: f.meanWindMs != null ? fmtNum(f.meanWindMs, 2) + " m/s" : "not reported" });
    b.push({ kind: "kv", key: "Mean current", value: f.meanCurrentMs != null ? fmtNum(f.meanCurrentMs, 3) + " m/s" : "not reported" });
    b.push({ kind: "kv", key: "Wind drift factor", value: f.alphaWind != null ? String(f.alphaWind) : "not reported" });
    b.push({ kind: "kv", key: "Leeway deflection", value: f.deflectionDeg != null ? f.deflectionDeg + " deg" : "not reported" });
    b.push({ kind: "kv", key: "Ensemble", value: f.particles != null ? (f.particles + " particles" + (f.solver ? ", " + f.solver : "") + (f.dtSeconds ? ", " + (f.dtSeconds / 60) + " min steps" : "")) : "not reported" });

    /* 6 --------------------------------------------------------- uncertainty */
    b.push({ kind: "h2", text: "6. Uncertainty and time windows" });
    if (u.origin && u.origin.available) {
      b.push({ kind: "kv", key: "Origin zone centre", value: fmtNum(u.origin.lat, 4) + ", " + fmtNum(u.origin.lon, 4) });
      b.push({ kind: "kv", key: "Origin time", value: u.origin.time });
      b.push({ kind: "kv", key: "Displayed radius", value: (u.origin.radiusKm != null ? fmtNum(u.origin.radiusKm, 2) + " km (90th-percentile particle distance)" : "not reported") });
      b.push({ kind: "kv", key: "Buffer", value: u.origin.bufferKm != null ? fmtNum(u.origin.bufferKm, 2) + " km" : "not reported" });
      b.push({ kind: "kv", key: "Zone area", value: u.origin.areaKm2 != null ? fmtNum(u.origin.areaKm2, 2) + " km2" : "not reported" });
      b.push({ kind: "p", text: u.origin.method });
      b.push({ kind: "p", text: u.origin.note });
    } else {
      b.push({ kind: "p", text: (u.origin && u.origin.reason) || "No origin estimate for this case." });
    }
    (u.windows || []).forEach(function (w) {
      b.push({ kind: "kv", key: w.label, value: (w.start || "n/a") + " to " + (w.end || "n/a") + (w.note ? " - " + w.note : "") });
    });
    if (u.detection && u.detection.polygons) {
      b.push({ kind: "kv", key: "Detection confidence (first polygon)", value: u.detection.bestConfidence != null ? fmtNum(u.detection.bestConfidence, 3) : "not reported" });
      b.push({ kind: "p", text: u.detection.note });
    }
    if (u.scores && u.scores.max !== undefined && u.scores.max !== null) {
      b.push({ kind: "kv", key: "Top ranked score", value: fmtNum(u.scores.max, 1) + " of 100" });
      b.push({ kind: "kv", key: "Top track confidence", value: u.scores.confidence != null ? fmtNum(u.scores.confidence, 3) : "not reported" });
      b.push({ kind: "p", text: u.scores.note });
    }
    (f.limits || []).forEach(function (l) { b.push({ kind: "bullet", text: l }); });

    /* 7 ----------------------------------------------------------- candidates */
    b.push({ kind: "h2", text: "7. Ranked candidate evidence" });
    if (!a.candidates || !a.candidates.length) {
      b.push({ kind: "p", text: "No candidate passed the spatio-temporal filter. An empty leaderboard is a reported result." });
    } else {
      a.candidates.slice(0, 10).forEach(function (cand) {
        b.push({ kind: "h3", text: "#" + cand.rank + " " + (cand.name || "UNKNOWN") + " - MMSI " + cand.mmsi });
        b.push({ kind: "kv", key: "Ranked score", value: fmtNum(cand.score, 1) + " of 100 (prioritisation aid, not a probability)" });
        b.push({ kind: "kv", key: "Track confidence", value: cand.confidence != null ? fmtNum(cand.confidence, 3) : "not reported" });
        b.push({ kind: "kv", key: "Evidence-only score", value: cand.scoreBeforeConfidence != null ? fmtNum(cand.scoreBeforeConfidence, 1) : "not reported" });
        b.push({ kind: "kv", key: "Vessel type", value: cand.type || "not reported" });
        b.push({ kind: "kv", key: "Evidence quality", value: cand.evidenceQuality || "not reported" });
        b.push({ kind: "kv", key: "Distance to origin", value: cand.distanceToOriginKm != null ? fmtNum(cand.distanceToOriginKm, 1) + " km" : "not reported" });
        b.push({ kind: "kv", key: "Closest approach", value: cand.closestApproach || "not reported" });
        b.push({ kind: "kv", key: "Time in search radius", value: cand.coverage.timeOverlapMinutes != null ? fmtNum(cand.coverage.timeOverlapMinutes, 1) + " min (" + fmtNum(cand.coverage.receivedOverlapMinutes, 1) + " min from received positions)" : "not reported" });
        b.push({ kind: "kv", key: "Track coverage", value: (cand.coverage.receivedPositions != null ? cand.coverage.receivedPositions + " received positions" : "not reported") +
          (cand.coverage.deadReckonedFraction != null ? ", " + fmtNum(cand.coverage.deadReckonedFraction * 100, 1) + " percent dead reckoned" : "") +
          (cand.coverage.gaps ? ", " + cand.coverage.gaps + " gap(s)" : "") });
        b.push({ kind: "kv", key: "Sub-scores", value: "proximity " + fmtNum(cand.components.proximity, 2) + ", time " + fmtNum(cand.components.time, 2) + ", behaviour " + fmtNum(cand.components.behaviour, 2) + ", type " + fmtNum(cand.components.type, 2) + ", trajectory " + fmtNum(cand.components.trajectory, 2) });
        b.push({ kind: "kv", key: "Reasons", value: (cand.reasons || []).join(", ") || "none recorded" });
        b.push({ kind: "kv", key: "Dark-target comparison", value: (cand.darkTarget && cand.darkTarget.status) || "unavailable" });
        b.push({ kind: "kv", key: "Volume range", value: rangeText(cand.volume, "m3") });
        b.push({ kind: "kv", key: "Derived flow range", value: rangeText(cand.flow, "m3/h") });
        if (cand.assumptions && cand.assumptions.length) {
          b.push({ kind: "kv", key: "Assumptions for this candidate", value: "" });
          cand.assumptions.forEach(function (x) { b.push({ kind: "bullet", text: x }); });
        }
        (cand.unavailable || []).forEach(function (x) { b.push({ kind: "bullet", text: "Not available: " + x }); });
      });
    }

    /* 8 ---------------------------------------------------------- assumptions */
    b.push({ kind: "h2", text: "8. Assumptions" });
    if (!(a.assumptions || []).length) b.push({ kind: "p", text: "No assumptions are recorded for this case." });
    (a.assumptions || []).forEach(function (x) { b.push({ kind: "bullet", text: x }); });

    /* 9 ---------------------------------------------------------- limitations */
    b.push({ kind: "h2", text: "9. Limitations" });
    (a.limitations || []).forEach(function (x) { b.push({ kind: "bullet", text: x }); });
    b.push({ kind: "h2", text: "10. Not available in this build" });
    (a.unavailable || []).forEach(function (x) {
      b.push({ kind: "h3", text: x.feature });
      b.push({ kind: "p", text: "Not available: " + x.reason });
    });

    /* 11 ----------------------------------------------------- what it does not */
    b.push({ kind: "h2", text: "11. What this report does not establish" });
    [
      "It does not establish that any vessel caused this spill, and it is not a finding of guilt.",
      "It does not establish a release point or a release time. The origin is an estimated zone from a backward ensemble.",
      "It does not establish the volume of oil released. Any volume or flow range is an assumption-bounded illustration.",
      "It does not establish the chemical age of the slick. Age here is drift time from the estimated origin.",
      "It does not establish that AIS coverage was complete. A gap is a missing broadcast, not evidence of intent.",
      "It does not establish that the detection is complete. Look-alikes are separated only on the baseline path.",
      "It does not establish that this file has not been altered since it left this machine. The SHA-256 digest published alongside it shows only whether the bytes changed after generation."
    ].forEach(function (x) { b.push({ kind: "bullet", text: x }); });

    /* 12 ----------------------------------------------------------- integrity */
    b.push({ kind: "h2", text: "12. Report integrity" });
    b.push({ kind: "p", text: "Format: PDF. This document is not PDF/A; no PDF/A validator has been run on it, so PDF/A is not claimed." });
    b.push({ kind: "p", text: "A PDF cannot contain its own SHA-256. The digest of these exact bytes is published in the console's Dossier view and in the adjacent file name shown there. The console recomputes SHA-256 from the bytes you select and reports MATCH or MISMATCH." });
    b.push({ kind: "p", text: "A matching digest is an integrity check only. It shows the bytes are unchanged since generation. It does not establish authenticity of the underlying data, and it does not establish causation or guilt." });
    b.push({ kind: "kv", key: "Job document", value: c.jobId });
    b.push({ kind: "kv", key: "Analysis contract", value: a.contract });
    b.push({ kind: "kv", key: "Document generated (UTC)", value: a.generatedAt });

    return b;
  }

  function build(analysis) {
    var blocksIn = blocks(analysis);
    var pdf = new Pdf();
    pdf.h1("SentinelTrace dossier");

    // The first h1 is drawn by the header pass below, so drop the duplicate.
    var seenTitle = false;
    blocksIn.forEach(function (blk) {
      if (blk.kind === "h1") { seenTitle = true; return; }
      if (!seenTitle) return;
      switch (blk.kind) {
        case "h2": pdf.h2(blk.text); break;
        case "h3": pdf.h3(blk.text); break;
        case "p":
          pdf.p(blk.text, { size: blk.size || 9, color: blk.color || null });
          break;
        case "mono": pdf.mono(blk.text); break;
        case "kv": pdf.kv(blk.key, blk.value); break;
        case "bullet": pdf.bullet(blk.text); break;
        default: pdf.p(blk.text || "");
      }
    });

    var jobId = (analysis.case || {}).jobId || "job";
    var bytes = pdf.finish("SentinelTrace - " + jobId + " - investigation aid, not proof of guilt");
    return {
      bytes: bytes,
      filename: "sentineltrace_dossier_" + String(jobId).replace(/[^A-Za-z0-9_-]/g, "_") + ".pdf",
      mime: "application/pdf",
      blocks: blocksIn
    };
  }

  window.SentinelDossier = { build: build, blocks: blocks, ascii: ascii };
})();
