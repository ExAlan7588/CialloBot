from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

from loguru import logger

if TYPE_CHECKING:
    import aiohttp

OSU_API_V2_BASE_URL = "https://osu.ppy.sh/api/v2"
OSU_OAUTH_TOKEN_URL = "https://osu.ppy.sh/oauth/token"
OSU_API_V1_BASE_URL = "https://osu.ppy.sh/api"

HTTP_NO_CONTENT = 204
HTTP_ERROR_MIN = 400
RESPONSE_PREVIEW_LENGTH = 500

ApiResponse: TypeAlias = dict[str, Any] | list[Any]
RequestParams: TypeAlias = dict[str, Any]


class OsuAPIError(Exception):
    """Base exception for osu! API failures."""


class OsuAPITokenError(OsuAPIError):
    """Raised when OAuth token acquisition fails."""


class OsuAPIResponseError(OsuAPIError):
    """Raised when osu! API returns an HTTP error response."""


class OsuAPIDataError(OsuAPIError):
    """Raised when osu! API returns data in an unexpected shape."""


def api_v2_url(endpoint: str) -> str:
    return (
        f"{OSU_API_V2_BASE_URL}/{endpoint}"
        if not endpoint.startswith("/")
        else f"{OSU_API_V2_BASE_URL}{endpoint}"
    )


async def parse_response(
    response: aiohttp.ClientResponse, url: str, *, params: RequestParams | None = None
) -> ApiResponse:
    if response.status == HTTP_NO_CONTENT:
        return {}

    response_text = await response.text()
    logger.debug(f"[OSU_API] {response.status} {url}: {response_text[:RESPONSE_PREVIEW_LENGTH]}")
    if response.status >= HTTP_ERROR_MIN:
        msg = f"osu! API request failed ({response.status}) for {url} params={params}: {response_text}"
        raise OsuAPIResponseError(msg)
    if not response_text:
        return {}

    data = await response.json()
    if isinstance(data, (dict, list)):
        return data

    msg = f"osu! API returned unsupported JSON payload: {type(data).__name__}"
    raise OsuAPIDataError(msg)


def expect_dict(data: ApiResponse, context: str) -> dict[str, Any]:
    if isinstance(data, dict):
        return data
    msg = f"Expected object response for {context}, got {type(data).__name__}"
    raise OsuAPIDataError(msg)


def expect_list(data: ApiResponse, context: str) -> list[Any]:
    if isinstance(data, list):
        return data
    msg = f"Expected list response for {context}, got {type(data).__name__}"
    raise OsuAPIDataError(msg)
