"""SentinelTrace AI Intelligence Assistant (NuGen domain model proxy).

Provides domain-specific AI assistance for oil spill investigation, SAR
interpretation, drift modelling explanation, and vessel attribution methodology.

This module is strictly isolated from the core oil detection and drift pipeline:
it never alters segmentation masks, drift vectors, scores, or attribution.
It operates via Python standard library HTTP (`urllib.request`) to preserve
the offline boundary constraints.
"""
from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, List

from . import config

log = logging.getLogger("sentineltrace.assistant")

SYSTEM_PROMPT = """You are SentinelTrace AI, an expert domain intelligence assistant specialized in marine remote sensing, satellite SAR interpretation, ocean-current oil drift modeling, and vessel attribution.

Your domain knowledge principles:
1. SAR Detection & Look-alikes:
   - Synthetic Aperture Radar (SAR) detects surface roughness. Mineral oil dampens capillary-gravity waves, creating low-backscatter dark patches.
   - Low backscatter does NOT automatically imply mineral oil. Common look-alikes include biogenic films (plankton/algal blooms), grease ice, internal solitary waves, rain cells, and calm wind zones (< 2-3 m/s).
   - Wind speed gating (e.g. 3-12 m/s optimal window) and multi-feature analysis (contrast, gradient, edge roughness, shape) are essential to discriminate slicks.

2. Drift Modelling (Hindcast & Forecast):
   - Oil drift follows Lagrangian particle tracking driven by combined metocean forces: surface currents (e.g. Copernicus / HYCOM / ECMWF) plus direct wind drift (typically 3% wind factor with Ekman deflection, ~15° in the Northern hemisphere).
   - Backtracking (hindcast) projects candidate origin regions at past timestamps to identify where and when a discharge likely occurred.
   - Forward drift (forecast) projects the slick's movement and trajectory for containment and environmental risk assessment.

3. Vessel Attribution:
   - Attribution correlates historical vessel AIS positions with the backtracked spill origin area and time window.
   - Splicing spatial proximity, temporal alignment, navigation behavior (e.g. loitering, speed changes), vessel type (tankers, cargo), and trajectory alignment.
   - CRITICAL SAFEGUARD: Never assert vessel guilt or definitive culpability without corroborating evidence. Always state findings as probabilistic correlation or investigative leads.

Tone and style:
- Objective, technically rigorous, concise, and professional.
- Clearly note that responses are supplementary investigative guidance and should be verified with ground truth.
"""


def get_status() -> Dict[str, Any]:
    """Return status and configuration of the NuGen AI Assistant."""
    configured = bool(config.NUGEN_API_KEY)
    return {
        "configured": configured,
        "model_id": config.NUGEN_MODEL_ID,
        "base_model": config.NUGEN_BASE_MODEL,
        "status": "experimental",
        "title": "SentinelTrace AI Intelligence",
        "description": "Domain-specific AI assistance for oil-spill investigation and SAR interpretation.",
    }


def chat(
    messages: List[Dict[str, str]],
    max_tokens: int = 400,
    temperature: float = 0.3,
    timeout: float = 25.0,
) -> Dict[str, Any]:
    """Send conversation messages to the NuGen chat completions API endpoint.

    Returns a dict with 'status' ('ok', 'unconfigured', or 'error'),
    'reply', and supplementary metadata.
    """
    if not config.NUGEN_API_KEY:
        return {
            "status": "unconfigured",
            "reply": "AI Assistant is not configured. Add your NuGen API key to the backend environment.",
            "experimental": True,
        }

    # Format conversation history, ensuring system prompt is prepended
    formatted_messages: List[Dict[str, str]] = []
    has_system = any(m.get("role") == "system" for m in messages)
    if not has_system:
        formatted_messages.append({"role": "system", "content": SYSTEM_PROMPT})

    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if content:
            formatted_messages.append({"role": role, "content": content})

    payload = {
        "model": config.NUGEN_MODEL_ID,
        "messages": formatted_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        # NuGen defaults chat completions to SSE streaming. This caller expects
        # one JSON document and reads the response with json.loads(), so opt out
        # of streaming explicitly.
        "stream": False,
    }

    body_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        config.NUGEN_API_URL,
        data=body_bytes,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.NUGEN_API_KEY}",
            "User-Agent": f"SentinelTrace/{config.VERSION}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_response = resp.read().decode("utf-8")
            data = json.loads(raw_response)

        # Standard OpenAI-compatible completion parsing
        choices = data.get("choices") or []
        if choices and isinstance(choices, list):
            reply_text = choices[0].get("message", {}).get("content", "")
        elif "reply" in data:
            reply_text = data["reply"]
        elif "text" in data:
            reply_text = data["text"]
        else:
            reply_text = str(data)

        return {
            "status": "ok",
            "reply": reply_text.strip(),
            "model_id": config.NUGEN_MODEL_ID,
            "base_model": config.NUGEN_BASE_MODEL,
            "experimental": True,
        }

    except urllib.error.HTTPError as exc:
        err_msg = f"NuGen API HTTP error {exc.code}: {exc.reason}"
        try:
            err_body = exc.read().decode("utf-8")
            err_data = json.loads(err_body)
            if "message" in err_data:
                err_msg = f"{err_msg} - {err_data['message']}"
            elif "error" in err_data:
                err_msg = f"{err_msg} - {err_data['error']}"
        except Exception:
            pass
        log.warning("NuGen API call failed: %s", err_msg)
        return {
            "status": "error",
            "reply": f"NuGen service error ({exc.code}). Please verify your API key and quota.",
            "error_detail": err_msg,
            "experimental": True,
        }

    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        log.warning("NuGen API connection error: %s", exc)
        return {
            "status": "error",
            "reply": "Unable to connect to NuGen AI service. Check your internet connection or proxy settings.",
            "error_detail": str(exc),
            "experimental": True,
        }

    except Exception as exc:
        log.warning("NuGen API unexpected error: %s", exc)
        return {
            "status": "error",
            "reply": "An unexpected error occurred while processing the AI request.",
            "error_detail": str(exc),
            "experimental": True,
        }
