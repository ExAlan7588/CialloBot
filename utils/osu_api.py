from __future__ import annotations

import time
from typing import Any, TypeAlias

import aiohttp
from loguru import logger

OSU_API_V2_BASE_URL = "https://osu.ppy.sh/api/v2"
OSU_OAUTH_TOKEN_URL = "https://osu.ppy.sh/oauth/token"
OSU_API_V1_BASE_URL = "https://osu.ppy.sh/api"

HTTP_NO_CONTENT = 204
HTTP_ERROR_MIN = 400
TOKEN_EXPIRY_SKEW_SECONDS = 60
API_V2_PAGE_LIMIT = 100
RESPONSE_PREVIEW_LENGTH = 500
MANIA_MAX_HIT_VALUE = 320
OSU_MAX_HIT_VALUE = 300
OSU_GOOD_HIT_VALUE = 100
OSU_MEH_HIT_VALUE = 50
MANIA_KATU_HIT_VALUE = 200
TAIKO_GOOD_WEIGHT = 0.5

ApiResponse: TypeAlias = dict[str, Any] | list[Any]
RequestParams: TypeAlias = dict[str, Any]

RULESET_IDS = {"osu": 0, "taiko": 1, "fruits": 2, "mania": 3}

MODS_ENUM = {
    1: "NF",
    2: "EZ",
    4: "TD",
    8: "HD",
    16: "HR",
    32: "SD",
    64: "DT",
    128: "RX",
    256: "HT",
    512: "NC",
    1024: "FL",
    2048: "AU",
    4096: "SO",
    8192: "AP",
    16384: "PF",
}

SPEED_MODS = {"NC", "DT", "HT"}


class OsuAPIError(Exception):
    """Base exception for osu! API failures."""


class OsuAPITokenError(OsuAPIError):
    """Raised when OAuth token acquisition fails."""


class OsuAPIResponseError(OsuAPIError):
    """Raised when osu! API returns an HTTP error response."""


class OsuAPIDataError(OsuAPIError):
    """Raised when osu! API returns data in an unexpected shape."""


class OsuAPI:
    def __init__(self, client_id: str, client_secret: str, api_v1_key: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_v1_key = api_v1_key
        self.session: aiohttp.ClientSession | None = None
        self._access_token: str | None = None
        self._token_expiry_time = 0.0

    async def setup(self) -> None:
        """Initialize the shared aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def close(self) -> None:
        """Close the shared aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        await self.setup()
        if self.session is None:
            msg = "aiohttp session was not initialized"
            raise RuntimeError(msg)
        return self.session

    async def _get_access_token(self) -> bool:
        """Acquire and store an OAuth access token."""
        session = await self._get_session()
        payload = self._token_payload()
        token_data = await self._fetch_token_data(session, payload)
        self._store_token_data(token_data)
        return True

    def _token_payload(self) -> dict[str, str]:
        return {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": "public",
        }

    async def _fetch_token_data(
        self, session: aiohttp.ClientSession, payload: dict[str, str]
    ) -> dict[str, Any]:
        async with session.post(OSU_OAUTH_TOKEN_URL, data=payload) as response:
            data = await self._parse_response(response, OSU_OAUTH_TOKEN_URL)

        if not isinstance(data, dict):
            msg = "OAuth token endpoint returned a non-object payload"
            raise OsuAPITokenError(msg)
        return data

    def _store_token_data(self, token_data: dict[str, Any]) -> None:
        access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in")
        if not isinstance(access_token, str) or not isinstance(expires_in, int):
            msg = "OAuth token response missing access_token or expires_in"
            raise OsuAPITokenError(msg)

        self._access_token = access_token
        self._token_expiry_time = time.time() + expires_in - TOKEN_EXPIRY_SKEW_SECONDS

    async def _ensure_token(self) -> None:
        """Ensure an unexpired OAuth access token is available."""
        if self._access_token is None or time.time() >= self._token_expiry_time:
            await self._get_access_token()

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: RequestParams | None = None,
        json_payload: RequestParams | None = None,
    ) -> ApiResponse:
        """Send a request to osu! API v2 and return parsed JSON data."""
        await self._ensure_token()
        session = await self._get_session()
        url = _api_v2_url(endpoint)
        headers = self._authorization_headers()

        async with session.request(
            method, url, params=params, json=json_payload, headers=headers
        ) as response:
            return await self._parse_response(response, url, params=params)

    def _authorization_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _parse_response(
        self, response: aiohttp.ClientResponse, url: str, params: RequestParams | None = None
    ) -> ApiResponse:
        if response.status == HTTP_NO_CONTENT:
            return {}

        response_text = await response.text()
        logger.debug(
            f"[OSU_API] {response.status} {url}: {response_text[:RESPONSE_PREVIEW_LENGTH]}"
        )
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

    async def get_user(
        self, user_identifier: str, mode: str | None = None, identifier_type: str | None = None
    ) -> dict[str, Any]:
        """Retrieve details for a user."""
        endpoint = f"/users/{user_identifier}"
        if mode:
            endpoint += f"/{mode}"

        params = {"key": "username"} if identifier_type == "username" else {}
        return _expect_dict(await self._request("GET", endpoint, params=params), endpoint)

    async def get_user_recent(
        self,
        user_id: int | str,
        mode: str | None = None,
        limit: int = 5,
        offset: int | None = None,
        include_fails: bool = True,
    ) -> list[Any]:
        """Retrieve a user's recent scores."""
        endpoint = f"/users/{user_id}/scores/recent"
        params: RequestParams = {"limit": limit, "include_fails": "1" if include_fails else "0"}
        if mode:
            params["mode"] = mode
        if offset is not None:
            params["offset"] = offset

        return _expect_list(await self._request("GET", endpoint, params=params), endpoint)

    async def get_user_best(
        self,
        user_id: int | str,
        mode: str | None = None,
        limit: int = API_V2_PAGE_LIMIT,
        offset: int | None = None,
    ) -> list[Any]:
        """Retrieve a user's best scores, following offset pagination."""
        scores: list[Any] = []
        current_offset = offset or 0

        while len(scores) < limit:
            request_limit = min(API_V2_PAGE_LIMIT, limit - len(scores))
            page = await self._get_user_best_page(user_id, mode, request_limit, current_offset)
            if not page:
                break

            scores.extend(page)
            current_offset += len(page)
            if len(page) < request_limit:
                break

        logger.debug(f"[get_user_best] Fetched {len(scores)} scores for user {user_id}.")
        return scores

    async def _get_user_best_page(
        self, user_id: int | str, mode: str | None, limit: int, offset: int
    ) -> list[Any]:
        endpoint = f"/users/{user_id}/scores/best"
        params: RequestParams = {"limit": limit, "offset": offset}
        if mode:
            params["mode"] = mode
        return _expect_list(await self._request("GET", endpoint, params=params), endpoint)

    async def get_user_beatmapsets(
        self, user_id: int | str, beatmap_type: str, limit: int = 50, offset: int = 0
    ) -> list[Any]:
        """Retrieve beatmapsets for a user and beatmapset type."""
        endpoint = f"/users/{user_id}/beatmapsets/{beatmap_type}"
        result = await self._request("GET", endpoint, params={"limit": limit, "offset": offset})
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and isinstance(result.get("beatmapsets"), list):
            return result["beatmapsets"]

        msg = f"Expected beatmapset list for {endpoint}, got {type(result).__name__}"
        raise OsuAPIDataError(msg)

    async def get_beatmapset(self, beatmapset_id: int) -> dict[str, Any]:
        """Retrieve details for a beatmapset."""
        endpoint = f"/beatmapsets/{beatmapset_id}"
        return _expect_dict(await self._request("GET", endpoint), endpoint)

    async def get_beatmap_details(self, beatmap_id: int) -> dict[str, Any]:
        """Retrieve details for a beatmap difficulty."""
        endpoint = f"/beatmaps/{beatmap_id}"
        return _expect_dict(await self._request("GET", endpoint), endpoint)

    async def get_beatmap_attributes(
        self,
        beatmap_id: int,
        mods: int | list[str] | str | None = None,
        ruleset_id: int | None = None,
        ruleset_short_name: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve difficulty attributes for a beatmap."""
        endpoint = f"/beatmaps/{beatmap_id}/attributes"
        payload = _beatmap_attributes_payload(mods, ruleset_id, ruleset_short_name)
        return _expect_dict(await self._request("POST", endpoint, json_payload=payload), endpoint)

    def decode_mods(self, mods_int: int | list[str]) -> str:
        """Convert mod bitmask or API v2 mod list to a compact mod string."""
        if isinstance(mods_int, list):
            return "".join(mods_int) if mods_int else "None"
        if not isinstance(mods_int, int):
            return "Invalid"
        if mods_int == 0:
            return "None"

        mods = _decode_speed_mods(mods_int)
        mods.extend(
            mod for value, mod in MODS_ENUM.items() if mod not in SPEED_MODS and mods_int & value
        )
        return "".join(mods) if mods else "None"

    def calculate_accuracy(self, statistics: dict[str, Any], mode: str = "osu") -> float:
        """Calculate accuracy from osu! API score statistics."""
        counts = _score_counts(statistics)
        if mode == "osu":
            return _calculate_osu_accuracy(counts)
        if mode == "taiko":
            return _calculate_taiko_accuracy(counts)
        if mode == "fruits":
            return _direct_accuracy(statistics)
        if mode == "mania":
            return _calculate_mania_accuracy(counts)
        return _direct_accuracy(statistics)

    async def get_score_v1(
        self, beatmap_id: int, user_id: int | str, mode: int = 0
    ) -> dict[str, Any] | None:
        """Retrieve a user's best score on a beatmap from osu! API v1."""
        if not self.api_v1_key:
            logger.warning("[get_score_v1] API v1 key is not configured. Skipping fallback.")
            return None

        session = await self._get_session()
        params = {"k": self.api_v1_key, "b": beatmap_id, "u": user_id, "m": mode, "limit": 1}
        async with session.get(f"{OSU_API_V1_BASE_URL}/get_scores", params=params) as response:
            data = await self._parse_response(response, str(response.url))

        scores = _expect_list(data, "get_score_v1")
        return scores[0] if scores and isinstance(scores[0], dict) else None


def _api_v2_url(endpoint: str) -> str:
    return (
        f"{OSU_API_V2_BASE_URL}/{endpoint}"
        if not endpoint.startswith("/")
        else f"{OSU_API_V2_BASE_URL}{endpoint}"
    )


def _expect_dict(data: ApiResponse, context: str) -> dict[str, Any]:
    if isinstance(data, dict):
        return data
    msg = f"Expected object response for {context}, got {type(data).__name__}"
    raise OsuAPIDataError(msg)


def _expect_list(data: ApiResponse, context: str) -> list[Any]:
    if isinstance(data, list):
        return data
    msg = f"Expected list response for {context}, got {type(data).__name__}"
    raise OsuAPIDataError(msg)


def _beatmap_attributes_payload(
    mods: int | list[str] | str | None, ruleset_id: int | None, ruleset_short_name: str | None
) -> RequestParams:
    payload: RequestParams = {}
    if mods is not None:
        payload["mods"] = _normalize_mods_payload(mods)
    final_ruleset_id = ruleset_id or _ruleset_id_from_name(ruleset_short_name)
    if final_ruleset_id is not None:
        payload["ruleset_id"] = final_ruleset_id
    return payload


def _normalize_mods_payload(mods: int | list[str] | str) -> int | list[str] | str:
    if not isinstance(mods, str) or len(mods) == 0 or len(mods) % 2 != 0:
        return mods
    return [mods[index : index + 2] for index in range(0, len(mods), 2)]


def _ruleset_id_from_name(ruleset_short_name: str | None) -> int | None:
    return RULESET_IDS.get(ruleset_short_name.lower()) if ruleset_short_name else None


def _decode_speed_mods(mods_int: int) -> list[str]:
    if mods_int & 512:
        return ["NC"]
    if mods_int & 64:
        return ["DT"]
    if mods_int & 256:
        return ["HT"]
    return []


def _score_counts(statistics: dict[str, Any]) -> dict[str, int]:
    return {
        "c300": int(statistics.get("count_300", 0)),
        "c100": int(statistics.get("count_100", 0)),
        "c50": int(statistics.get("count_50", 0)),
        "miss": int(statistics.get("count_miss", 0)),
        "geki": int(statistics.get("count_geki", 0)),
        "katu": int(statistics.get("count_katu", 0)),
    }


def _calculate_osu_accuracy(counts: dict[str, int]) -> float:
    total_hits = counts["c300"] + counts["c100"] + counts["c50"] + counts["miss"]
    if total_hits == 0:
        return 0.0
    score = (
        counts["c300"] * OSU_MAX_HIT_VALUE
        + counts["c100"] * OSU_GOOD_HIT_VALUE
        + counts["c50"] * OSU_MEH_HIT_VALUE
    )
    return round(score / (total_hits * OSU_MAX_HIT_VALUE) * 100, 2)


def _calculate_taiko_accuracy(counts: dict[str, int]) -> float:
    total_hits = counts["c300"] + counts["c100"] + counts["miss"]
    if total_hits == 0:
        return 0.0
    return round((counts["c300"] + counts["c100"] * TAIKO_GOOD_WEIGHT) / total_hits * 100, 2)


def _calculate_mania_accuracy(counts: dict[str, int]) -> float:
    total_notes = sum(counts.values())
    if total_notes == 0:
        return 0.0
    score = (
        counts["geki"] * MANIA_MAX_HIT_VALUE
        + counts["c300"] * OSU_MAX_HIT_VALUE
        + counts["katu"] * MANIA_KATU_HIT_VALUE
        + counts["c100"] * OSU_GOOD_HIT_VALUE
        + counts["c50"] * OSU_MEH_HIT_VALUE
    )
    return round(score / (total_notes * MANIA_MAX_HIT_VALUE) * 100, 2)


def _direct_accuracy(statistics: dict[str, Any]) -> float:
    accuracy = statistics.get("accuracy")
    return float(accuracy) * 100 if accuracy is not None else 0.0
