"""Async HTTP client for the WLED JSON and file endpoints."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from .exceptions import WLEDConnectionError, WLEDValidationError

DEFAULT_REQUEST_TIMEOUT = 10.0
DEFAULT_UPLOAD_TIMEOUT = 30.0
DEFAULT_MAX_PRESETS_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class WLEDInfo:
    """Subset of WLED info metadata needed by the integration."""

    brand: str
    product: str | None
    name: str
    version: str
    architecture: str
    build_id: int
    mac_address: str
    device_id: str | None


@dataclass(frozen=True)
class WLEDClientCapabilities:
    """Capabilities exposed by the WLED client implementation."""

    presets_upload_supported: bool = True
    presets_upload_verified: bool = False


class WLEDClient:
    """Purpose-built aiohttp client for the WLED backup surface."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        *,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        upload_timeout: float = DEFAULT_UPLOAD_TIMEOUT,
        max_presets_bytes: int = DEFAULT_MAX_PRESETS_BYTES,
        capabilities: WLEDClientCapabilities | None = None,
    ) -> None:
        """Initialize the client using Home Assistant's shared aiohttp session."""
        self._session = session
        self._base_url = _normalize_base_url(host)
        self._request_timeout = request_timeout
        self._upload_timeout = upload_timeout
        self._max_presets_bytes = max_presets_bytes
        self.capabilities = capabilities or WLEDClientCapabilities()

    @property
    def base_url(self) -> str:
        """Return the normalized base URL for this WLED device."""
        return self._base_url

    async def async_get_info(self) -> WLEDInfo:
        """Return structured device info from `/json/info`."""
        payload = await self._async_get_json("/json/info")
        return WLEDInfo(
            brand=_require_str(payload, "brand"),
            product=_optional_str(payload, "product"),
            name=_require_str(payload, "name"),
            version=_require_str(payload, "ver"),
            architecture=_require_str(payload, "arch"),
            build_id=_require_int(payload, "vid"),
            mac_address=_require_identity(payload),
            device_id=_optional_str(payload, "deviceId"),
        )

    async def async_get_config(self) -> dict[str, Any]:
        """Return the raw WLED config object from `/json/cfg`."""
        return await self._async_get_json("/json/cfg")

    async def async_get_state(self) -> dict[str, Any]:
        """Return the raw WLED state object from `/json/state`."""
        return await self._async_get_json("/json/state")

    async def async_get_presets_raw(self) -> bytes:
        """Return the raw presets file contents from `/presets.json`."""
        return await self._async_get_bytes(
            "/presets.json",
            timeout=self._request_timeout,
            max_bytes=self._max_presets_bytes,
        )

    async def async_set_config(self, config: dict[str, Any]) -> None:
        """POST a full or partial config object to `/json/cfg`."""
        await self._async_post_json("/json/cfg", config, timeout=self._request_timeout)

    async def async_set_state(self, state: dict[str, Any]) -> None:
        """POST a state object to `/json/state`."""
        await self._async_post_json(
            "/json/state",
            state,
            timeout=self._request_timeout,
        )

    async def async_reboot(self) -> None:
        """Request an immediate reboot through `/json/state`."""
        await self.async_set_state({"rb": True})

    async def async_upload_presets(self, payload: bytes) -> None:
        """Upload `presets.json` to the WLED `/edit` filesystem endpoint."""
        if not self.capabilities.presets_upload_supported:
            raise WLEDValidationError("Preset upload is not supported by this client")

        form = aiohttp.FormData()
        form.add_field(
            "data",
            payload,
            filename="presets.json",
            content_type="application/json",
        )
        await self._async_request(
            "POST",
            "/edit",
            timeout=self._upload_timeout,
            data=form,
            expect_json=False,
        )

    async def async_close(self) -> None:
        """Close resources owned by the client.

        The shared Home Assistant aiohttp session is owned by Home Assistant, so
        this method is intentionally a no-op.
        """

    async def _async_get_json(self, path: str) -> dict[str, Any]:
        """GET and validate a JSON object response."""
        response = await self._async_request(
            "GET",
            path,
            timeout=self._request_timeout,
            expect_json=True,
        )
        try:
            payload = await response.json(content_type=None)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as err:
            raise WLEDValidationError(
                f"WLED returned invalid JSON for {path}"
            ) from err

        if not isinstance(payload, dict):
            raise WLEDValidationError(
                f"WLED returned a non-object JSON payload for {path}"
            )
        return payload

    async def _async_get_bytes(
        self,
        path: str,
        *,
        timeout: float,
        max_bytes: int,
    ) -> bytes:
        """GET a raw response body with a bounded maximum size."""
        response = await self._async_request(
            "GET",
            path,
            timeout=timeout,
            expect_json=False,
        )

        chunks: list[bytes] = []
        size = 0
        async for chunk in response.content.iter_chunked(8192):
            size += len(chunk)
            if size > max_bytes:
                raise WLEDValidationError(
                    f"WLED response from {path} exceeded {max_bytes} bytes"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    async def _async_post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout: float,
    ) -> None:
        """POST JSON and detect explicit WLED error bodies."""
        response = await self._async_request(
            "POST",
            path,
            timeout=timeout,
            json=payload,
            expect_json=False,
        )

        body = await response.read()
        if not body:
            return

        if _looks_like_json_response(response):
            try:
                parsed = json.loads(body.decode(response.charset or "utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return
            if isinstance(parsed, dict) and (
                parsed.get("success") is False or parsed.get("error")
            ):
                raise WLEDConnectionError(
                    f"WLED reported a failure for {path}: {parsed!r}"
                )

    async def _async_request(
        self,
        method: str,
        path: str,
        *,
        timeout: float,
        expect_json: bool,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """Perform a bounded HTTP request with WLED-specific error mapping."""
        request_timeout = aiohttp.ClientTimeout(total=timeout)
        url = f"{self._base_url}{path}"
        try:
            response = await self._session.request(
                method,
                url,
                timeout=request_timeout,
                **kwargs,
            )
        except TimeoutError as err:
            raise WLEDConnectionError(
                f"Timed out talking to WLED at {self._base_url} for {method} {path}"
            ) from err
        except (aiohttp.ClientError, OSError) as err:
            raise WLEDConnectionError(
                f"Failed talking to WLED at {self._base_url} for {method} {path}: {err}"
            ) from err

        if response.status < 200 or response.status >= 300:
            body = await response.read()
            response.release()
            raise WLEDConnectionError(
                f"WLED returned HTTP {response.status} for {method} {path}: "
                f"{body[:200]!r}"
            )

        if expect_json and not _looks_like_json_response(response):
            body = await response.read()
            response.release()
            raise WLEDValidationError(
                f"WLED returned unexpected content type {response.content_type!r} "
                f"for {path}: {body[:200]!r}"
            )

        return response


def _normalize_base_url(host: str) -> str:
    """Normalize a raw host or URL to a stable base URL."""
    candidate = host.strip()
    if "://" not in candidate:
        candidate = f"http://{candidate}"

    parts = urlsplit(candidate)
    scheme = parts.scheme or "http"
    netloc = parts.netloc or parts.path
    path = parts.path if parts.netloc else ""
    normalized_path = path.rstrip("/")
    return urlunsplit((scheme, netloc, normalized_path, "", "")).rstrip("/")


def _looks_like_json_response(response: aiohttp.ClientResponse) -> bool:
    """Return whether a response advertises a JSON content type."""
    content_type = response.content_type or ""
    return content_type == "application/json" or content_type.endswith("+json")


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    """Return an optional string value from a JSON object."""
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise WLEDValidationError(f"WLED response field {key!r} must be a string")
    return value


def _require_str(payload: dict[str, Any], key: str) -> str:
    """Return a required non-empty string field."""
    value = _optional_str(payload, key)
    if value is None:
        raise WLEDValidationError(f"WLED response is missing required field {key!r}")
    return value


def _require_int(payload: dict[str, Any], key: str) -> int:
    """Return a required integer field."""
    value = payload.get(key)
    if not isinstance(value, int):
        raise WLEDValidationError(f"WLED response field {key!r} must be an integer")
    return value


def _require_identity(payload: dict[str, Any]) -> str:
    """Return the best available WLED identity field."""
    device_id = _optional_str(payload, "deviceId")
    if device_id is not None:
        return device_id
    return _require_str(payload, "mac")