from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import aiohttp
from loguru import logger

from utils import osu_http
from utils.osu_domain import RULESET_IDS, calculate_accuracy, decode_mods
from utils.osu_http import (
    OSU_API_V1_BASE_URL,
    OSU_OAUTH_TOKEN_URL,
    ApiResponse,
    OsuAPITokenError,
    RequestParams,
    api_v2_url,
    expect_dict,
    expect_list,
    parse_response,
)

TOKEN_EXPIRY_SKEW_SECONDS = 60
API_V2_PAGE_LIMIT = 100
OsuAPIError = osu_http.OsuAPIError
OsuAPIResponseError = osu_http.OsuAPIResponseError
OsuAPIDataError = osu_http.OsuAPIDataError


@dataclass(frozen=True, kw_only=True)
class BeatmapAttributesRequest:
    mods: int | list[str] | str | None
    ruleset_id: int | None
    ruleset_short_name: str | None


class OsuAPI:
    def __init__(self, *, client_id: str, client_secret: str, api_v1_key: str) -> None:
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
        *,
        params: RequestParams | None = None,
        json_payload: RequestParams | None = None,
    ) -> ApiResponse:
        """Send a request to osu! API v2 and return parsed JSON data."""
        await self._ensure_token()
        session = await self._get_session()
        url = api_v2_url(endpoint)
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
        self, response: aiohttp.ClientResponse, url: str, *, params: RequestParams | None = None
    ) -> ApiResponse:
        return await parse_response(response, url, params=params)

    async def get_user(
        self, user_identifier: str, *, mode: str | None = None, identifier_type: str | None = None
    ) -> dict[str, Any]:
        """Retrieve details for a user."""
        endpoint = f"/users/{user_identifier}"
        if mode:
            endpoint += f"/{mode}"

        params = {"key": "username"} if identifier_type == "username" else {}
        return expect_dict(await self._request("GET", endpoint, params=params), endpoint)

    async def get_user_recent(
        self,
        user_id: int | str,
        *,
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

        return expect_list(await self._request("GET", endpoint, params=params), endpoint)

    async def get_user_best(
        self,
        user_id: int | str,
        *,
        mode: str | None = None,
        limit: int = API_V2_PAGE_LIMIT,
        offset: int | None = None,
    ) -> list[Any]:
        """Retrieve a user's best scores, following offset pagination."""
        scores: list[Any] = []
        current_offset = offset or 0

        while len(scores) < limit:
            request_limit = min(API_V2_PAGE_LIMIT, limit - len(scores))
            page = await self._get_user_best_page(
                user_id, mode=mode, limit=request_limit, offset=current_offset
            )
            if not page:
                break

            scores.extend(page)
            current_offset += len(page)
            if len(page) < request_limit:
                break

        logger.debug(f"[get_user_best] Fetched {len(scores)} scores for user {user_id}.")
        return scores

    async def _get_user_best_page(
        self, user_id: int | str, *, mode: str | None, limit: int, offset: int
    ) -> list[Any]:
        endpoint = f"/users/{user_id}/scores/best"
        params: RequestParams = {"limit": limit, "offset": offset}
        if mode:
            params["mode"] = mode
        return expect_list(await self._request("GET", endpoint, params=params), endpoint)

    async def get_user_beatmapsets(
        self, user_id: int | str, beatmap_type: str, *, limit: int = 50, offset: int = 0
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
        return expect_dict(await self._request("GET", endpoint), endpoint)

    async def get_beatmap_details(self, beatmap_id: int) -> dict[str, Any]:
        """Retrieve details for a beatmap difficulty."""
        endpoint = f"/beatmaps/{beatmap_id}"
        return expect_dict(await self._request("GET", endpoint), endpoint)

    async def get_beatmap_attributes(
        self,
        beatmap_id: int,
        *,
        mods: int | list[str] | str | None = None,
        ruleset_id: int | None = None,
        ruleset_short_name: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve difficulty attributes for a beatmap."""
        endpoint = f"/beatmaps/{beatmap_id}/attributes"
        payload = _beatmap_attributes_payload(
            BeatmapAttributesRequest(
                mods=mods, ruleset_id=ruleset_id, ruleset_short_name=ruleset_short_name
            )
        )
        return expect_dict(await self._request("POST", endpoint, json_payload=payload), endpoint)

    def decode_mods(self, mods_int: int | list[str]) -> str:
        """Convert mod bitmask or API v2 mod list to a compact mod string."""
        return decode_mods(mods_int)

    def calculate_accuracy(self, statistics: dict[str, Any], mode: str = "osu") -> float:
        """Calculate accuracy from osu! API score statistics."""
        return calculate_accuracy(statistics, mode)

    async def get_score_v1(
        self, beatmap_id: int, user_id: int | str, *, mode: int = 0
    ) -> dict[str, Any] | None:
        """Retrieve a user's best score on a beatmap from osu! API v1."""
        if not self.api_v1_key:
            logger.warning("[get_score_v1] API v1 key is not configured. Skipping fallback.")
            return None

        session = await self._get_session()
        params = {"k": self.api_v1_key, "b": beatmap_id, "u": user_id, "m": mode, "limit": 1}
        async with session.get(f"{OSU_API_V1_BASE_URL}/get_scores", params=params) as response:
            data = await self._parse_response(response, str(response.url))

        scores = expect_list(data, "get_score_v1")
        return scores[0] if scores and isinstance(scores[0], dict) else None


def _beatmap_attributes_payload(request: BeatmapAttributesRequest) -> RequestParams:
    payload: RequestParams = {}
    if request.mods is not None:
        payload["mods"] = _normalize_mods_payload(request.mods)
    final_ruleset_id = request.ruleset_id or _ruleset_id_from_name(request.ruleset_short_name)
    if final_ruleset_id is not None:
        payload["ruleset_id"] = final_ruleset_id
    return payload


def _normalize_mods_payload(mods: int | list[str] | str) -> int | list[str] | str:
    if not isinstance(mods, str) or len(mods) == 0 or len(mods) % 2 != 0:
        return mods
    return [mods[index : index + 2] for index in range(0, len(mods), 2)]


def _ruleset_id_from_name(ruleset_short_name: str | None) -> int | None:
    return RULESET_IDS.get(ruleset_short_name.lower()) if ruleset_short_name else None
