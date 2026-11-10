"""Unit and integration tests for SentinelTrace NuGen AI Assistant."""
from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

from app import assistant, config
from app.api.assistant import ChatRequest, get_assistant_status, post_chat


def test_assistant_status_unconfigured():
    """When NUGEN_API_KEY is not set, assistant reports unconfigured status."""
    with patch.object(config, "NUGEN_API_KEY", ""):
        st = assistant.get_status()
        assert st["configured"] is False
        assert st["model_id"] == config.NUGEN_MODEL_ID
        assert st["base_model"] == "Llama-3.2-3B-Instruct"
        assert st["status"] == "experimental"

        api_st = get_assistant_status()
        assert api_st["configured"] is False


def test_assistant_status_configured():
    """When NUGEN_API_KEY is set, assistant reports configured status."""
    with patch.object(config, "NUGEN_API_KEY", "test_key_abc123"):
        st = assistant.get_status()
        assert st["configured"] is True

        api_st = get_assistant_status()
        assert api_st["configured"] is True


def test_assistant_chat_unconfigured():
    """When unconfigured, chat returns friendly message without calling remote API."""
    with patch.object(config, "NUGEN_API_KEY", ""):
        res = assistant.chat([{"role": "user", "content": "Explain SentinelTrace methodology."}])
        assert res["status"] == "unconfigured"
        assert "not configured" in res["reply"].lower()
        assert res["experimental"] is True

        api_res = post_chat(ChatRequest(prompt="Explain SAR detection"))
        assert api_res["status"] == "unconfigured"
        assert "not configured" in api_res["reply"].lower()


def test_assistant_chat_success():
    """When configured and API responds, returns formatted model reply."""
    mock_response_body = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "SentinelTrace uses SAR backscatter damping to detect candidate slicks.",
                },
                "finish_reason": "stop",
            }
        ],
    }
    raw_bytes = json.dumps(mock_response_body).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = raw_bytes
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch.object(config, "NUGEN_API_KEY", "dummy_key"):
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            res = assistant.chat(
                [{"role": "user", "content": "How does SAR detection work?"}],
                max_tokens=256,
            )
            assert res["status"] == "ok"
            assert "SentinelTrace uses SAR backscatter" in res["reply"]
            assert res["experimental"] is True

            # Verify request headers and payload
            assert mock_urlopen.called
            req = mock_urlopen.call_args[0][0]
            assert req.get_header("Authorization") == "Bearer dummy_key"
            payload = json.loads(req.data.decode("utf-8"))
            assert payload["model"] == config.NUGEN_MODEL_ID
            # Ensure system prompt is prepended
            assert payload["messages"][0]["role"] == "system"
            assert "look-alike" in payload["messages"][0]["content"].lower()
            assert payload["messages"][1]["content"] == "How does SAR detection work?"


def test_assistant_chat_http_error():
    """Handles HTTPError (e.g. 401 Unauthorized or 429 Quota Exceeded) gracefully."""
    error_stream = io.BytesIO(b'{"error": "Invalid API key"}')
    http_error = urllib.error.HTTPError(
        url="https://api.nugen.in/api/v3/inference/chat/completions",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=error_stream,
    )

    with patch.object(config, "NUGEN_API_KEY", "bad_key"):
        with patch("urllib.request.urlopen", side_effect=http_error):
            res = assistant.chat([{"role": "user", "content": "Test prompt"}])
            assert res["status"] == "error"
            assert "401" in res["reply"] or "NuGen service error" in res["reply"]
            assert res["experimental"] is True


def test_assistant_chat_network_timeout():
    """Handles network timeout or URLError without raising unhandled exceptions."""
    url_error = urllib.error.URLError(reason="Connection timed out")

    with patch.object(config, "NUGEN_API_KEY", "valid_key"):
        with patch("urllib.request.urlopen", side_effect=url_error):
            res = assistant.chat([{"role": "user", "content": "Test prompt"}])
            assert res["status"] == "error"
            assert "unable to connect" in res["reply"].lower()


def test_assistant_chat_api_route_empty():
    """Posting empty request returns clean error response."""
    res = post_chat(ChatRequest())
    assert res["status"] == "error"
    assert "No prompt or message list" in res["reply"]


def test_assistant_isolation_from_pipeline():
    """Verify assistant functions have zero side-effects on config or pipeline constants."""
    assert config.ALPHA_WIND == 0.03
    assert config.DEFLECTION_DEG == 15.0
    assert config.OFFLINE is True
    assert "nugen_configured" in config.as_dict()
    assert config.as_dict()["nugen_base_model"] == "Llama-3.2-3B-Instruct"
