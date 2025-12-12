from __future__ import annotations

import time  # For token expiry

import aiohttp
from loguru import logger

# osu! API v2 的基礎 URL
OSU_API_V2_BASE_URL = "https://osu.ppy.sh/api/v2"
OSU_OAUTH_TOKEN_URL = "https://osu.ppy.sh/oauth/token"
# osu! API v1 的基礎 URL
OSU_API_V1_BASE_URL = "https://osu.ppy.sh/api"


class OsuAPI:
    def __init__(self, client_id: str, client_secret: str, api_v1_key: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_v1_key = api_v1_key  # Added for API v1
        self.session = None
        self._access_token = None
        self._token_expiry_time = 0  # Timestamp when the token expires

    async def setup(self) -> None:
        """初始化 aiohttp.ClientSession"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def close(self) -> None:
        """關閉 aiohttp.ClientSession"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def _get_access_token(self) -> bool | None:
        """使用 Client Credentials Grant 獲取 access token"""
        await self.setup()
        logger.debug("[OSU_API] Attempting to get new access token...")

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": "public",  # 通常請求公開資料需要 public scope
        }

        try:
            async with self.session.post(OSU_OAUTH_TOKEN_URL, data=payload) as response:
                response.raise_for_status()
                token_data = await response.json()
                self._access_token = token_data["access_token"]
                self._token_expiry_time = time.time() + token_data["expires_in"] - 60
                logger.debug(
                    f"[OSU_API] Successfully obtained new access token. Expires at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._token_expiry_time))}"
                )
                return True
        except aiohttp.ClientResponseError as e:
            logger.error(
                f"[OSU_API] 獲取 osu! API v2 access token 失敗 ({e.status}): {e.message} for URL {OSU_OAUTH_TOKEN_URL}. Response: {await e.response.text() if e.response else 'N/A'}"
            )
            self._access_token = None
            self._token_expiry_time = 0
            return False
        except Exception as e:
            logger.error(f"[OSU_API] 獲取 osu! API v2 access token 時發生未知錯誤: {e}")
            self._access_token = None
            self._token_expiry_time = 0
            return False

    async def _ensure_token(self) -> bool:
        """確保我們有一個有效的 (未過期的) access token"""
        logger.debug("[OSU_API] Ensuring token...")
        if self._access_token is None:
            logger.debug("[OSU_API] Token is None. Requesting new token.")
            return await self._get_access_token()
        if time.time() >= self._token_expiry_time:
            logger.debug(
                f"[OSU_API] Token expired at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._token_expiry_time))}. Requesting new token."
            )
            return await self._get_access_token()
        logger.debug("[OSU_API] Token is valid.")
        return True

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json_payload: dict | None = None,
    ) -> dict | list | None:
        """發送異步請求到 osu! API v2"""
        logger.debug(f"[OSU_API] Preparing request: {method} {endpoint}")
        if not await self._ensure_token():
            logger.error("[OSU_API] Failed to ensure valid access token. Aborting request.")
            return None

        await self.setup()  # 確保 session 已初始化
        logger.debug("[OSU_API] Session ensured.")

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",  # 通常 API v2 POST/PUT 需要
        }

        # API v2 的端點通常是完整的相對路徑，例如 /users/{id}/scores/best
        # Base URL 已經是 "https://osu.ppy.sh/api/v2"
        # 所以 endpoint 應該是 "/users/..." 這樣的形式
        if not endpoint.startswith("/"):
            url = f"{OSU_API_V2_BASE_URL}/{endpoint}"
        else:
            url = f"{OSU_API_V2_BASE_URL}{endpoint}"

        try:
            async with self.session.request(
                method, url, params=params, json=json_payload, headers=headers
            ) as response:
                logger.debug(f"[OSU_API] Request sent. URL: {response.url}")
                logger.debug(f"[OSU_API] Request Headers: {headers}")
                if response.status == 204:
                    logger.debug(f"[OSU_API] Response Status: 204 No Content for URL: {url}")
                    return {}

                response_text = await response.text()
                logger.debug(f"[OSU_API] Response Status: {response.status} for URL: {url}")
                # Limit logging large responses in debug, show first 500 chars
                logger.debug(f"[OSU_API] Response Text (first 500 chars): {response_text[:500]}")

                if response.status >= 400:
                    # Error already logged in the previous log, this one is more for raising the exception
                    logger.error(
                        f"osu! API v2 請求錯誤 ({response.status}): {response_text} for URL {url} with params {params}, payload {json_payload}"
                    )
                    response.raise_for_status()

                if not response_text and response.status == 200:  # Empty success response
                    logger.debug(f"[OSU_API] Empty successful response (200 OK) for URL: {url}")
                    return {}  # Or None, depending on expectation for empty 200s

                return await response.json()
        except aiohttp.ClientResponseError as e:
            # This block might be redundant if response.raise_for_status() is hit
            # and the error is re-raised and caught by the generic Exception block.
            # However, it's good for specific handling if needed.
            # response_text would have been logged above if readable
            logger.error(
                f"[OSU_API] ClientResponseError in _request ({e.status}): {e.message} for URL {url}. Response text was logged above if available."
            )
            return None
        except aiohttp.ClientError as e:
            logger.error(
                f"[OSU_API] ClientError (e.g., connection issue) in _request: {e} for URL {url}"
            )
            return None
        except Exception as e:
            # This catches errors from response.json() if text is not valid JSON, or other unexpected errors
            current_response_text = (
                response_text
                if "response_text" in locals()
                else "Response text not available or read yet"
            )
            logger.error(
                f"[OSU_API] Unknown error in _request: {type(e).__name__} - {e} for URL {url}. Response Text (first 200): {current_response_text[:200]}"
            )
            return None

    # --- API 端點方法 (需要完全重寫以適應 API v2) --- #

    # 示例：API v2 的 get_user (需要根據 v2 文檔調整)
    async def get_user(
        self, user_identifier: str, mode: str | None = None, identifier_type: str | None = None
    ) -> dict | None:
        """
        Retrieves details for a user.
        API: GET /users/{user_identifier}[/{mode}]
        user_identifier: User ID (as string) or username.
        mode: Optional game mode string (e.g., "osu", "taiko", "fruits", "mania").
              If provided, statistics for this mode are returned.
        identifier_type: 'username' 或 'id'，由上層明確傳遞，避免自動判斷誤加 key
        """
        endpoint = f"/users/{user_identifier}"
        if mode:
            endpoint += f"/{mode}"

        params = {}
        if identifier_type == "username":
            params["key"] = "username"
        # identifier_type == "id" 時不加任何 key

        return await self._request("GET", endpoint, params=params)

    # 以下方法是 API v1 的，需要刪除或重寫為 API v2
    # async def get_beatmaps... (此方法及其內容將被刪除)

    async def get_user_recent(
        self,
        user_id: int | str,
        mode: str | None = None,
        limit: int = 5,
        offset: int | None = None,
        include_fails: bool = True,
    ) -> list | None:
        """
        獲取使用者最近的遊玩紀錄。
        API v2 端點: /users/{user_id}/scores/recent
        """
        # 示例，需要根據 v2 文檔調整參數
        endpoint = f"/users/{user_id}/scores/recent"
        params = {"limit": limit, "include_fails": "1" if include_fails else "0"}
        if mode:  # osu! API v2 scores endpoints usually require mode as a query parameter
            params["mode"] = mode
        if offset is not None:
            params["offset"] = offset

        return await self._request("GET", endpoint, params=params)

    async def get_user_best(
        self,
        user_id: int | str,
        mode: str | None = None,
        limit: int = 100,
        offset: int | None = None,
    ) -> list | None:
        """
        獲取使用者的最佳表現。支援自動分頁獲取最多實際請求的 limit 數量。
        API v2 端點: /users/{user_id}/scores/best
        limit: 單次 API 請求的條目數，osu! API v2 通常上限為 100。
        offset: 初始偏移量，主要供內部遞迴使用。

        注意：此函數現在的 limit 參數是指示單次 API 請求的 limit，並非總目標數量。
        若要獲取特定總數，應由調用者多次調用或在此函數外部實現循環獲取邏輯。
        此處將保持與 osu! API 單次請求行為一致，即單次最多返回 `limit` 條 (上限100)。
        調用者如果需要200條，需要自行分頁，或者我們可以在這裡調整以獲取總數。

        更新：調整此方法以支持獲取指定的總數，透過內部處理分頁。
        將 `limit` 參數視為希望獲取的總記錄數。
        """
        all_scores = []
        current_offset = offset if offset is not None else 0
        # osu! API 的單頁最大 limit 似乎是 100
        page_limit = 100

        # The `limit` parameter for this function now means the total desired scores.
        # The `page_limit` is the per-request limit for the API.
        total_limit_to_fetch = limit

        while len(all_scores) < total_limit_to_fetch:
            actual_request_limit = min(page_limit, total_limit_to_fetch - len(all_scores))
            if (
                actual_request_limit <= 0
            ):  # Should not happen if loop condition is correct, but as a safeguard
                break

            endpoint = f"/users/{user_id}/scores/best"
            params = {"limit": actual_request_limit, "offset": current_offset}
            if mode:
                params["mode"] = mode

            logger.debug(
                f"[get_user_best] Requesting scores: user_id={user_id}, mode={mode}, limit={actual_request_limit}, offset={current_offset}"
            )

            scores_page = await self._request("GET", endpoint, params=params)

            if scores_page is None:  # Error in request
                logger.error(
                    f"[get_user_best] Error fetching scores page for user {user_id} at offset {current_offset}. Aborting further pagination."
                )
                # Return what we have so far, or None if nothing was fetched at all
                return all_scores or None

            if not isinstance(scores_page, list):
                logger.error(
                    f"[get_user_best] Expected list from API, got {type(scores_page)}. Aborting."
                )
                return all_scores or None

            if not scores_page:  # No more scores to fetch
                logger.debug(
                    f"[get_user_best] No more scores returned for user {user_id} at offset {current_offset}."
                )
                break

            all_scores.extend(scores_page)
            current_offset += len(
                scores_page
            )  # Increment offset by the number of scores actually received

            if (
                len(scores_page) < actual_request_limit
            ):  # API returned fewer than requested, means no more scores
                logger.debug(
                    f"[get_user_best] API returned fewer scores ({len(scores_page)}) than requested ({actual_request_limit}). Assuming no more scores."
                )
                break

        logger.debug(
            f"[get_user_best] Fetched a total of {len(all_scores)} scores for user {user_id}."
        )
        return all_scores or []  # Return empty list if nothing found, or None if error earlier

    async def get_user_beatmapsets(
        self, user_id: int | str, beatmap_type: str, limit: int = 50, offset: int = 0
    ) -> list | None:
        """
        Retrieves a list of beatmapsets for a user of a specific type.
        API: GET /users/{user_id}/beatmapsets/{type}?limit={limit}&offset={offset}
        user_id: The ID of the user.
        beatmap_type: Type of beatmapset (e.g., 'ranked', 'loved', 'graveyard', 'pending', 'nominated', 'guest').
        limit: Maximum number of results.
        offset: Offset of results for pagination.
        """
        endpoint = f"/users/{user_id}/beatmapsets/{beatmap_type}"
        params = {"limit": limit, "offset": offset}

        # The API documentation suggests that the response is an array of beatmapset objects.
        # It also includes 'total' and 'cursor_string' for some types (like guest/nominated),
        # but for general types like ranked/loved, simple limit/offset pagination is used.
        # For simplicity, we'll start with limit/offset.
        # We might need to handle cursor pagination later if it becomes an issue for certain types.

        logger.debug(
            f"[OSU_API get_user_beatmapsets] Fetching type '{beatmap_type}' for user {user_id} with limit {limit}, offset {offset}"
        )
        result = await self._request("GET", endpoint, params=params)

        # The API for /beatmapsets/{type} returns an array of beatmapset objects directly.
        # Some endpoints (like scores) wrap this in a dictionary with a 'data' key or similar,
        # but beatmapsets seems to return the array directly.
        # Let's assume it's a list for now. If it's a dict with a 'beatmapsets' key or similar,
        # we'll need to adjust. The debug logs from _request should clarify the structure.
        if isinstance(result, list):
            logger.debug(
                f"[OSU_API get_user_beatmapsets] Received {len(result)} beatmapsets of type '{beatmap_type}' for user {user_id}"
            )
            return result
        if (
            isinstance(result, dict)
            and "beatmapsets" in result
            and isinstance(result["beatmapsets"], list)
        ):
            # Handling cases where the API might wrap the list, e.g. for cursor-based pagination responses
            logger.debug(
                f"[OSU_API get_user_beatmapsets] Received {len(result['beatmapsets'])} beatmapsets (from dict) of type '{beatmap_type}' for user {user_id}"
            )
            # The dict might also contain 'total' and 'cursor' fields for cursor pagination.
            # For now, we just return the beatmapsets. The calling function will need to handle pagination logic.
            return result["beatmapsets"]
        if (
            result is not None
        ):  # Non-list, non-dict with 'beatmapsets' but not None (e.g. an error dict not caught by _request)
            logger.warning(
                f"[OSU_API get_user_beatmapsets] Expected a list or dict with 'beatmapsets' key for '{beatmap_type}' for user {user_id}, but got {type(result)}. Data: {str(result)[:200]}"
            )
            return None  # Or an empty list, depending on how we want to handle unexpected formats
        # result is None (error already logged by _request)
        logger.error(
            f"[OSU_API get_user_beatmapsets] Failed to fetch beatmapsets of type '{beatmap_type}' for user {user_id}"
        )
        return None

    async def get_beatmapset(self, beatmapset_id: int) -> dict | None:
        """
        Retrieves details for a beatmapset.
        API: GET /beatmapsets/{beatmapset_id}
        """
        endpoint = f"/beatmapsets/{beatmapset_id}"
        return await self._request("GET", endpoint)

    async def get_beatmap_details(self, beatmap_id: int) -> dict | None:
        """
        Retrieves details for a specific beatmap difficulty.
        API: GET /beatmaps/{beatmap_id}
        """
        endpoint = f"/beatmaps/{beatmap_id}"
        return await self._request("GET", endpoint)

    async def get_beatmap_attributes(
        self,
        beatmap_id: int,
        mods: int | list | str | None = None,
        ruleset_id: int | None = None,
        ruleset_short_name: str | None = None,
    ) -> dict | None:
        """
        Retrieves difficulty attributes for a specific beatmap, optionally with mods and for a specific ruleset.
        API: POST /beatmaps/{beatmap_id}/attributes
        mods: Can be a bitmask integer, a list of mod acronyms (e.g., ["HD", "HR"]), or a string of acronyms (e.g., "HDHR").
        ruleset_id: The ID of the ruleset (0 for osu!, 1 for taiko, 2 for catch, 3 for mania).
        ruleset_short_name: Alternative to ruleset_id (e.g., "osu", "taiko", "fruits", "mania"). Will be converted to ID if ruleset_id is not provided.
        """
        endpoint = f"/beatmaps/{beatmap_id}/attributes"
        payload = {}
        if mods is not None:
            # API accepts mods as an array of strings or a bitmask integer.
            # If string of acronyms, convert to list.
            if isinstance(mods, str):
                # Simple split for combined mods like "HDHR" -> ["HD", "HR"] (assuming 2-letter mods)
                # More robust parsing might be needed for complex/combined mod strings from users.
                # For now, let's assume the caller provides a list or bitmask if it's not a single mod string.
                if len(mods) > 0 and len(mods) % 2 == 0:
                    payload["mods"] = [mods[i : i + 2] for i in range(0, len(mods), 2)]
                else:  # Assume single mod string or already a bitmask/list that will be passed directly
                    payload["mods"] = mods
            else:  # Already a list or int
                payload["mods"] = mods

        final_ruleset_id = ruleset_id
        if final_ruleset_id is None and ruleset_short_name:
            ruleset_map = {"osu": 0, "taiko": 1, "fruits": 2, "mania": 3}
            final_ruleset_id = ruleset_map.get(ruleset_short_name.lower())

        if final_ruleset_id is not None:
            payload["ruleset_id"] = final_ruleset_id

        return await self._request("POST", endpoint, json_payload=payload)

    # --- 輔助函數 (可能需要調整或可以保留，取決於 v2 API 回應) --- #

    def decode_mods(self, mods_int: int | list) -> str:
        """
        將 Mod 的數字表示 (v1) 或字串縮寫列表 (v2) 轉換為可讀的字串。
        API v2 通常直接返回 mods 的字串縮寫列表，例如 ["HD", "DT"]。
        """
        if isinstance(mods_int, list):  # API v2 style
            return "".join(mods_int) if mods_int else "None"

        # Fallback to v1 integer decoding if an integer is passed (for compatibility during transition or if v1 data is encountered)
        if isinstance(mods_int, int):
            if mods_int == 0:
                return "None"
            mods = []
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
            if mods_int & 512:
                mods.append("NC")
                mods_int &= ~64
                mods_int &= ~256
            elif mods_int & 64:
                mods.append("DT")
            for mod_val, mod_str in MODS_ENUM.items():
                if mod_str in {"NC", "DT", "HT"}:
                    if not (mod_str == "HT" and 512 & mods_int):
                        continue
                if mods_int & mod_val:
                    mods.append(mod_str)
            return "".join(mods) if mods else "None"
        return "Invalid"

    def calculate_accuracy(self, statistics: dict, mode: str = "osu") -> float:
        """
        根據 API v2 Score statistics 物件計算準確率。
        mode: 遊戲模式字串 (e.g., 'osu', 'taiko', 'fruits', 'mania')
        statistics: API v2 Score object's 'statistics' field, e.g. {'count_300': 100, 'count_100': 10, ...}
        """
        c300 = int(statistics.get("count_300", 0))
        c100 = int(statistics.get("count_100", 0))
        c50 = int(statistics.get("count_50", 0))
        cmiss = int(statistics.get("count_miss", 0))
        # API v2 scores also include geki and katu for mania and taiko
        c_geki = int(statistics.get("count_geki", 0))  # Perfect (Taiko), MAX (Mania)
        c_katu = int(
            statistics.get("count_katu", 0)
        )  # Good (Taiko), 300 (Mania) - careful with mania interpretation

        if mode == "osu":
            total_hits = c300 + c100 + c50 + cmiss
            if total_hits == 0:
                return 0.0
            accuracy = ((c300 * 300 + c100 * 100 + c50 * 50) / (total_hits * 300)) * 100
            return round(accuracy, 2)
        if mode == "taiko":
            total_hits = c300 + c100 + cmiss  # c50 is not used, geki/katu are part of c300/c100
            if total_hits == 0:
                return 0.0
            # Taiko accuracy: ( (greats * 1) + (goods * 0.5) ) / total_notes
            # Here, c300 are greats, c100 are goods.
            accuracy = ((c300 * 1 + c100 * 0.5) / total_hits) * 100
            return round(accuracy, 2)
        if mode == "fruits":
            total_hits = (
                c300 + c100 + c50 + cmiss + c_katu
            )  # c_katu are droplets caught by missing a fruit on slider
            # c300 = fruits, c100 = drops, c50 = droplets, cmiss = fruit misses
            # Need to be careful, API v2 might provide 'perfect' or 'large_tick_hit' for fruits.
            # The 'statistics' object for fruits is: count_300, count_100, count_50, count_miss, count_katu (droplets)
            # Let's assume c300=fruits, c100=drops, c50=tiny drops, cmiss=misses, katu=droplet misses?
            # osu-wiki: (fruits and drops and droplets caught) / (total fruits and drops and droplets)
            # Total "catchable" items: c300 (fruits) + c100 (drops) + c50 (tiny drops from spinners) + c_katu (droplets)
            # Caught items: c300 + c100 + c50
            # This seems to be the common formula from various sources.
            total_catchable = c300 + c100 + c50 + cmiss + c_katu  # all hittable objects
            if total_catchable == 0:
                return 0.0
            # For Catch, accuracy is the sum of all hit fruit (300s, 100s, 50s) divided by the total number of fruit (including misses and droplet misses).
            # This interpretation is tricky. The API v2 documentation for Score defines `accuracy` directly.
            # It's better to rely on `score_data.get('accuracy')` if available and correctly scaled.
            # If calculating manually:
            # Number of fruits caught = c300
            # Number of drops caught = c100
            # Number of tiny droplets caught = c50
            # Total fruits and drops = c300 + c100 + cmiss (fruit misses)
            # accuracy = (c300 + c100 + c50) / (c300 + c100 + c50 + cmiss + c_katu) * 100 based on ppy/osu-wiki
            # Let's verify with what API v2 provides for accuracy directly.
            # For now, returning a placeholder or relying on direct API accuracy field.
            return (
                statistics.get("accuracy", 0.0) * 100
                if statistics.get("accuracy") is not None
                else 0.0
            )  # API often provides 0.xxxx format
        if mode == "mania":
            # Mania accuracy is complex: ( (MAX*320 + 300*300 + 200*200 + 100*100 + 50*50) / (total_notes * 320) ) * 100
            # geki = MAX, katu = 300s in some contexts, but API stats are count_geki, count_300, count_katu, count_100, count_50, count_miss
            # For mania: count_geki (MAX/300g), count_300 (300), count_katu (200/!200), count_100 (100), count_50 (50), count_miss (Miss)
            total_score_points = (
                (c_geki * 320) + (c300 * 300) + (c_katu * 200) + (c100 * 100) + (c50 * 50)
            )
            total_possible_points = (c_geki + c300 + c_katu + c100 + c50 + cmiss) * 320
            if total_possible_points == 0:
                return 0.0
            accuracy = (total_score_points / total_possible_points) * 100
            return round(accuracy, 2)
        # If API v2 provides accuracy directly in the score object, prefer that.
        # score_data.get('accuracy') might be e.g. 0.9876, so multiply by 100.
        return (
            statistics.get("accuracy", 0.0) * 100 if statistics.get("accuracy") is not None else 0.0
        )

    async def get_score_v1(self, beatmap_id: int, user_id: int | str, mode: int = 0) -> dict | None:
        """
        從 osu! API v1 獲取指定 beatmap 和用戶的最高分數。
        API v1 端點: /get_scores
        https://github.com/ppy/osu-api/wiki#apiget_scores
        只獲取用戶在該圖上的最佳成績 (limit=1)。
        """
        if not self.api_v1_key:
            logger.warning("[get_score_v1] API v1 key is not configured. Skipping fallback.")
            return None

        endpoint = f"{OSU_API_V1_BASE_URL}/get_scores"
        params = {
            "k": self.api_v1_key,
            "b": beatmap_id,
            "u": user_id,
            "m": mode,  # Add mode parameter
            "limit": 1,
        }
        logger.debug(f"[get_score_v1] Requesting API v1 with params: {params}")
        try:
            async with self.session.get(endpoint, params=params) as response:
                response.raise_for_status()  # Will raise an exception for 4xx/5xx status
                data = await response.json()
                if data and isinstance(data, list):  # API v1 returns a list of scores
                    logger.info(
                        f"[get_score_v1] Successfully fetched score from API v1: {data[0]} for beatmap {beatmap_id}, user {user_id}, mode {mode}"
                    )
                    return data[0]  # Return the first (and only) score
                if isinstance(data, list) and not data:  # Successfully fetched an empty list
                    logger.info(
                        f"[get_score_v1] API v1 returned an empty list for beatmap {beatmap_id}, user {user_id}, mode {mode}. No score data found."
                    )
                    return None
                logger.warning(
                    f"[get_score_v1] No score found or unexpected response format from API v1: {data} for beatmap {beatmap_id}, user {user_id}, mode {mode}"
                )
                return None
        except aiohttp.ClientResponseError as e:
            logger.error(
                f"[get_score_v1] HTTP error during API v1 request: {e.status} {e.message} for URL {e.request_info.url}"
            )
            return None
        except aiohttp.ClientError as e:
            logger.error(f"[get_score_v1] Client error during API v1 request: {e}")
            return None
        except Exception as e:
            logger.error(
                f"[get_score_v1] Unexpected error during API v1 request: {e}", exc_info=True
            )
            return None


# Main bot.py or cog setup will need to instantiate OsuAPI with client_id and client_secret
# e.g., bot.osu_api_client = OsuAPI(client_id=config.OSU_API_V2_CLIENT_ID, client_secret=config.OSU_API_V2_CLIENT_SECRET)
