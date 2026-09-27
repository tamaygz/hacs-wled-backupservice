"""Tests for the WLED HTTP client."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses

from custom_components.wled_backupservice.exceptions import (
    WLEDConnectionError,
    WLEDValidationError,
)
from custom_components.wled_backupservice.wled_client import (
    WLEDClient,
    WLEDClientCapabilities,
    WLEDInfo,
    _looks_like_json_response,
    _normalize_base_url,
    _optional_str,
    _require_identity,
    _require_int,
    _require_str,
)


@pytest.mark.asyncio
async def test_async_get_info_parses_required_fields() -> None:
    """The info endpoint should be parsed into a typed WLEDInfo model."""
    async with aiohttp.ClientSession() as session:
        client = WLEDClient("wled.local", session)
        with aioresponses() as mocked:
            mocked.get(
                "http://wled.local/json/info",
                payload={
                    "brand": "WLED",
                    "product": "FOSS",
                    "name": "Kitchen",
                    "ver": "0.16.0",
                    "arch": "esp32",
                    "vid": 2601010,
                    "mac": "aabbccddeeff",
                    "deviceId": "wled-aabbccddeeff",
                },
            )

            info = await client.async_get_info()

    assert info == WLEDInfo(
        brand="WLED",
        product="FOSS",
        name="Kitchen",
        version="0.16.0",
        architecture="esp32",
        build_id=2601010,
        mac_address="wled-aabbccddeeff",
        device_id="wled-aabbccddeeff",
    )


@pytest.mark.asyncio
async def test_async_get_info_falls_back_to_mac_when_device_id_missing() -> None:
    """Older WLED payloads should still use the MAC address as identity."""
    async with aiohttp.ClientSession() as session:
        client = WLEDClient("http://wled.local", session)
        with aioresponses() as mocked:
            mocked.get(
                "http://wled.local/json/info",
                payload={
                    "brand": "WLED",
                    "name": "Kitchen",
                    "ver": "0.15.0",
                    "arch": "esp8266",
                    "vid": 2501010,
                    "mac": "aabbccddeeff",
                },
            )

            info = await client.async_get_info()

    assert info.mac_address == "aabbccddeeff"
    assert info.device_id is None
    assert client.base_url == "http://wled.local"


@pytest.mark.asyncio
async def test_async_get_json_methods_map_transport_and_validation_errors() -> None:
    """GET helpers should map timeouts, invalid content types, and bad JSON cleanly."""
    async with aiohttp.ClientSession() as session:
        client = WLEDClient("wled.local", session)
        with aioresponses() as mocked:
            mocked.get(
                "http://wled.local/json/cfg",
                exception=TimeoutError(),
            )
            with pytest.raises(WLEDConnectionError, match="Timed out"):
                await client.async_get_config()

        with aioresponses() as mocked:
            mocked.get(
                "http://wled.local/json/state",
                body="<html>not json</html>",
                content_type="text/html",
            )
            with pytest.raises(WLEDValidationError, match="unexpected content type"):
                await client.async_get_state()

        with aioresponses() as mocked:
            mocked.get(
                "http://wled.local/json/cfg",
                body="{broken",
                content_type="application/json",
            )
            with pytest.raises(WLEDValidationError, match="invalid JSON"):
                await client.async_get_config()

        with aioresponses() as mocked:
            mocked.get(
                "http://wled.local/json/state",
                payload=["not", "an", "object"],
            )
            with pytest.raises(WLEDValidationError, match="non-object"):
                await client.async_get_state()

        with aioresponses() as mocked:
            mocked.get(
                "http://wled.local/json/cfg",
                exception=aiohttp.ClientConnectionError("boom"),
            )
            with pytest.raises(WLEDConnectionError, match="Failed talking to WLED"):
                await client.async_get_config()

        with aioresponses() as mocked:
            mocked.get(
                "http://wled.local/json/cfg",
                exception=OSError("offline"),
            )
            with pytest.raises(WLEDConnectionError, match="offline"):
                await client.async_get_config()


@pytest.mark.asyncio
async def test_async_get_presets_raw_enforces_max_size() -> None:
    """The presets download should reject oversized payloads."""
    async with aiohttp.ClientSession() as session:
        client = WLEDClient(
            "wled.local",
            session,
            max_presets_bytes=8,
        )
        with aioresponses() as mocked:
            mocked.get("http://wled.local/presets.json", body=b"0123456789")
            with pytest.raises(WLEDValidationError, match="exceeded 8 bytes"):
                await client.async_get_presets_raw()


@pytest.mark.asyncio
async def test_async_get_presets_raw_returns_bytes() -> None:
    """The presets backup endpoint should return raw bytes unchanged."""
    async with aiohttp.ClientSession() as session:
        client = WLEDClient("wled.local", session)
        payload = b'{"1":{"n":"Preset 1"}}'
        with aioresponses() as mocked:
            mocked.get("http://wled.local/presets.json", body=payload)

            result = await client.async_get_presets_raw()

    assert result == payload


@pytest.mark.asyncio
async def test_async_set_config_and_state_detect_http_failures() -> None:
    """Write helpers should surface non-2xx failures as connection errors."""
    async with aiohttp.ClientSession() as session:
        client = WLEDClient("wled.local", session)
        with aioresponses() as mocked:
            mocked.post("http://wled.local/json/cfg", status=403, body="locked")
            with pytest.raises(WLEDConnectionError, match="HTTP 403"):
                await client.async_set_config({"wifi": {}})

        with aioresponses() as mocked:
            mocked.post(
                "http://wled.local/json/state",
                payload={"success": False, "error": "bad state"},
            )
            with pytest.raises(WLEDConnectionError, match="bad state"):
                await client.async_set_state({"on": True})

        with aioresponses() as mocked:
            mocked.post(
                "http://wled.local/json/cfg",
                body="ok",
                content_type="text/plain",
            )
            await client.async_set_config({"wifi": {}})

        with aioresponses() as mocked:
            mocked.post(
                "http://wled.local/json/state",
                body="{not-json",
                content_type="application/json",
            )
            await client.async_set_state({"on": True})


@pytest.mark.asyncio
async def test_async_reboot_posts_reboot_flag() -> None:
    """Reboot should POST the documented JSON state reboot command."""
    captured: dict[str, object] = {}

    def callback(url: object, **kwargs: object) -> CallbackResult:
        captured["json"] = kwargs["json"]
        return CallbackResult(status=200, body=b"")

    async with aiohttp.ClientSession() as session:
        client = WLEDClient("wled.local", session)
        with aioresponses() as mocked:
            mocked.post("http://wled.local/json/state", callback=callback)
            await client.async_reboot()

    assert captured["json"] == {"rb": True}


@pytest.mark.asyncio
async def test_async_upload_presets_builds_multipart_edit_request() -> None:
    """Preset restore should POST a multipart upload to `/edit`."""
    captured: dict[str, object] = {}

    def callback(url: object, **kwargs: object) -> CallbackResult:
        captured["data"] = kwargs["data"]
        return CallbackResult(status=200, body=b"")

    async with aiohttp.ClientSession() as session:
        client = WLEDClient("wled.local", session)
        with aioresponses() as mocked:
            mocked.post("http://wled.local/edit", callback=callback)
            await client.async_upload_presets(b'{"1": {}}')

    form = captured["data"]
    assert isinstance(form, aiohttp.FormData)
    field = form._fields[0]
    assert field[0]["name"] == "data"
    assert field[0]["filename"] == "presets.json"


@pytest.mark.asyncio
async def test_async_upload_presets_can_be_capability_gated() -> None:
    """The client should expose and enforce preset-upload support flags."""
    async with aiohttp.ClientSession() as session:
        client = WLEDClient(
            "wled.local",
            session,
            capabilities=WLEDClientCapabilities(
                presets_upload_supported=False,
                presets_upload_verified=False,
            ),
        )
        assert client.capabilities.presets_upload_verified is False

        with pytest.raises(WLEDValidationError, match="not supported"):
            await client.async_upload_presets(b"{}")


@pytest.mark.asyncio
async def test_async_close_is_a_noop() -> None:
    """The client should not attempt to close the shared Home Assistant session."""
    async with aiohttp.ClientSession() as session:
        client = WLEDClient("wled.local", session)
        await client.async_close()
        assert session.closed is False


def test_base_url_normalization_tolerates_scheme_and_path() -> None:
    """Host normalization should add an HTTP scheme and preserve base paths."""
    client = WLEDClient(
        "example.local/wled",
        session=SimpleNamespace(),  # type: ignore[arg-type]
    )
    assert client.base_url == "http://example.local/wled"


def test_base_url_normalization_preserves_existing_scheme() -> None:
    """Existing schemes should be preserved by host normalization."""
    assert _normalize_base_url("https://example.local/api/") == "https://example.local/api"


def test_helper_field_validators_cover_error_paths() -> None:
    """Helper validators should enforce required types and identity fallbacks."""
    assert _optional_str({"name": "Kitchen"}, "name") == "Kitchen"
    assert _optional_str({}, "name") is None
    assert _require_str({"name": "Kitchen"}, "name") == "Kitchen"
    assert _require_int({"vid": 123}, "vid") == 123
    assert _require_identity({"mac": "aabbccddeeff"}) == "aabbccddeeff"

    with pytest.raises(WLEDValidationError, match="must be a string"):
        _optional_str({"name": 123}, "name")

    with pytest.raises(WLEDValidationError, match="missing required field"):
        _require_str({}, "name")

    with pytest.raises(WLEDValidationError, match="must be an integer"):
        _require_int({"vid": "123"}, "vid")


def test_json_content_type_helper_accepts_application_and_suffix_json() -> None:
    """JSON content-type detection should accept standard and +json media types."""
    assert _looks_like_json_response(
        cast(Any, SimpleNamespace(content_type="application/json"))
    )
    assert _looks_like_json_response(
        cast(Any, SimpleNamespace(content_type="application/problem+json"))
    )
    assert not _looks_like_json_response(
        cast(Any, SimpleNamespace(content_type="text/plain"))
    )