from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeAlias, TypedDict

import aiofiles
import aiofiles.os
import aiohttp
from loguru import logger
from rosu_pp_py import Beatmap, Difficulty, DifficultyAttributes, Performance, PerformanceAttributes

OSU_BEATMAP_DOWNLOAD_URL = "https://osu.ppy.sh/osu/{beatmap_id}"
TEMP_OSU_DIR = Path("temp")
DEFAULT_CLOCK_RATE = 1.0
CLOCK_RATE_TOLERANCE = 1e-9
ERROR_DETAIL_LIMIT = 200

BeatmapStatusInput: TypeAlias = int | str | None
LocalizedStringGetter: TypeAlias = Callable[[int, str, str], str]


class BeatmapMetadata(TypedDict):
    title: str
    artist: str
    version: str


class RosuPpResult(TypedDict):
    pp: float
    stars: float
    max_combo: int


class BeatmapProcessingError(Exception):
    """Base class for errors during beatmap processing."""


class BeatmapDownloadError(BeatmapProcessingError):
    """Raised when a .osu file download fails."""


class RosuPpCalculationError(BeatmapProcessingError):
    """Raised when rosu-pp calculation fails."""


MOD_ACRONYMS_TO_BITMASK = {
    "NF": 1,
    "EZ": 2,
    "HD": 8,
    "HR": 16,
    "SD": 32,
    "DT": 64,
    "RX": 128,
    "HT": 256,
    "NC": 512,
    "FL": 1024,
    "SO": 4096,
    "PF": 16384,
}

BEATMAP_STATUS_EMOJIS = {
    "ranked": "<:ranked:1378350261323694221>",
    "qualified": "<:AorQ:1378350246647566346>",
    "approved": "<:AorQ:1378350246647566346>",
    "loved": "<:loved:1378350254805483560>",
    "pending": "<:WorP:1378351617253838938>",
    "wip": "<:WorP:1378351617253838938>",
    "graveyard": "<:WorP:1378351617253838938>",
    "unknown": "<:WorP:1378351617253838938>",
}

BEATMAP_STATUS_API_MAP = {
    "graveyard": "graveyard",
    "wip": "wip",
    "pending": "pending",
    "ranked": "ranked",
    "approved": "approved",
    "qualified": "qualified",
    "loved": "loved",
    -2: "graveyard",
    -1: "wip",
    0: "pending",
    1: "ranked",
    2: "qualified",
    3: "approved",
    4: "loved",
    "work-in-progress": "wip",
}

BEATMAP_STATUS_L10N_KEYS = {
    "ranked": "beatmap_status_ranked_emoji",
    "qualified": "beatmap_status_qualified_emoji",
    "approved": "beatmap_status_approved_emoji",
    "loved": "beatmap_status_loved_emoji",
    "pending": "beatmap_status_pending_emoji",
    "wip": "beatmap_status_wip_emoji",
    "graveyard": "beatmap_status_graveyard_emoji",
    "unknown": "beatmap_status_unknown_emoji",
}


def get_beatmap_status_display(
    status_input: BeatmapStatusInput, user_id_for_l10n: int, lstr_func: LocalizedStringGetter
) -> str:
    """Return the emoji and localized label for a beatmap status."""
    status_key = _normalize_status_key(status_input)
    emoji = BEATMAP_STATUS_EMOJIS.get(status_key, BEATMAP_STATUS_EMOJIS["unknown"])
    l10n_key = BEATMAP_STATUS_L10N_KEYS.get(status_key, BEATMAP_STATUS_L10N_KEYS["unknown"])
    fallback = status_key.replace("-", " ").capitalize()
    status_text = lstr_func(user_id_for_l10n, l10n_key, fallback)
    return f"{emoji} {status_text}"


def _normalize_status_key(status_input: BeatmapStatusInput) -> str:
    if isinstance(status_input, int):
        return BEATMAP_STATUS_API_MAP.get(status_input, "unknown")
    if not isinstance(status_input, str):
        return "unknown"

    normalized = status_input.lower().replace("_", "-").replace(" ", "-")
    mapped_status = BEATMAP_STATUS_API_MAP.get(normalized)
    if isinstance(mapped_status, str):
        return mapped_status
    if normalized in BEATMAP_STATUS_EMOJIS:
        return normalized
    return "unknown"


async def download_osu_file(beatmap_id: int, session: aiohttp.ClientSession) -> str:
    """Download an .osu file and return the local file path."""
    if not await aiofiles.os.path.exists(TEMP_OSU_DIR):
        msg = f"Temporary directory {TEMP_OSU_DIR} does not exist"
        raise BeatmapDownloadError(msg)

    url = OSU_BEATMAP_DOWNLOAD_URL.format(beatmap_id=beatmap_id)
    file_path = TEMP_OSU_DIR / f"{beatmap_id}_{int(time.time())}.osu"

    try:
        async with session.get(url) as response:
            if response.status != 200:
                await _raise_download_error(response, url)
            await _write_response_body(file_path, response)
    except aiohttp.ClientError as exc:
        msg = f"Client error during .osu download for {url}: {exc}"
        raise BeatmapDownloadError(msg) from exc

    logger.debug(f"[BeatmapUtils] Successfully downloaded {file_path}")
    return str(file_path)


async def _raise_download_error(response: aiohttp.ClientResponse, url: str) -> None:
    error_detail = f"HTTP {response.status}"
    try:
        text_response = await response.text()
    except aiohttp.ClientError as exc:
        logger.warning(f"[BeatmapUtils] Failed to read download error body: {exc}")
    else:
        error_detail = f"{error_detail}: {text_response[:ERROR_DETAIL_LIMIT]}"

    msg = f"Error downloading .osu file: {error_detail} for URL {url}"
    raise BeatmapDownloadError(msg)


async def _write_response_body(file_path: Path, response: aiohttp.ClientResponse) -> None:
    async with aiofiles.open(file_path, "wb") as osu_file:
        await osu_file.write(await response.read())


def parse_osu_file_metadata(osu_file_path: str) -> BeatmapMetadata:
    """Parse title, artist, and version from an .osu file metadata section."""
    metadata: dict[str, str | None] = {"title": None, "artist": None, "version": None}
    in_metadata_section = False

    with Path(osu_file_path).open("r", encoding="utf-8") as osu_file:
        for raw_line in osu_file:
            stripped_line = raw_line.strip()
            if stripped_line == "[Metadata]":
                in_metadata_section = True
                continue
            if in_metadata_section and _metadata_section_finished(stripped_line):
                break
            if in_metadata_section:
                _apply_metadata_line(metadata, stripped_line)

    parsed_metadata = _metadata_with_defaults(metadata)
    logger.debug(f"[BeatmapUtils] Parsed metadata: {parsed_metadata} from {osu_file_path}")
    return parsed_metadata


def _metadata_section_finished(line: str) -> bool:
    return line.startswith("[") and line.endswith("]")


def _apply_metadata_line(metadata: dict[str, str | None], line: str) -> None:
    metadata_fields = {
        "title": ("Title:", "TitleUnicode:"),
        "artist": ("Artist:", "ArtistUnicode:"),
        "version": ("Version:",),
    }
    for field, prefixes in metadata_fields.items():
        if metadata[field] is not None:
            continue
        for prefix in prefixes:
            if line.startswith(prefix):
                metadata[field] = line[len(prefix) :].strip()
                return


def _metadata_with_defaults(metadata: dict[str, str | None]) -> BeatmapMetadata:
    return {
        "title": metadata["title"] or "Unknown Title",
        "artist": metadata["artist"] or "Unknown Artist",
        "version": metadata["version"] or "Unknown Version",
    }


def get_mods_bitmask_and_clock_rate(selected_mods: list[str]) -> tuple[int, float]:
    """Convert mod acronyms to a bitmask and clock rate."""
    bitmask = 0
    clock_rate = DEFAULT_CLOCK_RATE
    mods_for_processing = list(selected_mods)

    if "NC" in mods_for_processing and "DT" not in mods_for_processing:
        mods_for_processing.append("DT")

    for mod in mods_for_processing:
        mod_upper = mod.upper()
        bitmask |= MOD_ACRONYMS_TO_BITMASK.get(mod_upper, 0)
        if mod_upper in {"DT", "NC"}:
            clock_rate = 1.5
        elif mod_upper == "HT":
            clock_rate = 0.75

    return bitmask, clock_rate


async def calculate_pp_with_rosu(
    osu_file_path: str,
    selected_mods: list[str],
    *,
    accuracy: float = 100.0,
    combo: int | None = None,
    misses: int = 0,
) -> RosuPpResult:
    """Calculate PP using rosu-pp-py without blocking the event loop."""
    return await asyncio.to_thread(
        _calculate_pp_with_rosu_sync,
        osu_file_path,
        selected_mods,
        accuracy=accuracy,
        combo=combo,
        misses=misses,
    )


def _calculate_pp_with_rosu_sync(
    osu_file_path: str, selected_mods: list[str], *, accuracy: float, combo: int | None, misses: int
) -> RosuPpResult:
    try:
        return _run_rosu_pp_calculation(
            osu_file_path, selected_mods, accuracy=accuracy, combo=combo, misses=misses
        )
    except TypeError as exc:
        msg = f"rosu-pp API compatibility error for {osu_file_path}: {exc}"
        raise RosuPpCalculationError(msg) from exc
    except Exception as exc:
        msg = f"rosu-pp calculation failed for {osu_file_path}: {type(exc).__name__} - {exc}"
        raise RosuPpCalculationError(msg) from exc


def _run_rosu_pp_calculation(
    osu_file_path: str, selected_mods: list[str], *, accuracy: float, combo: int | None, misses: int
) -> RosuPpResult:
    beatmap = Beatmap(path=osu_file_path)
    mod_bitmask, clock_rate = get_mods_bitmask_and_clock_rate(selected_mods)
    difficulty_attrs = _calculate_difficulty(beatmap, mod_bitmask, clock_rate)
    actual_combo = combo if combo is not None else difficulty_attrs.max_combo
    performance_attrs = _calculate_performance(
        beatmap, mod_bitmask, clock_rate, accuracy=accuracy, combo=actual_combo, misses=misses
    )
    return _build_rosu_result(
        performance_attrs.pp, difficulty_attrs.stars, difficulty_attrs.max_combo
    )


def _calculate_difficulty(
    beatmap: Beatmap, mod_bitmask: int, clock_rate: float
) -> DifficultyAttributes:
    difficulty = Difficulty(mods=mod_bitmask)
    if not _is_default_clock_rate(clock_rate):
        difficulty.set_clock_rate(clock_rate)
    return difficulty.calculate(beatmap)


def _calculate_performance(
    beatmap: Beatmap,
    mod_bitmask: int,
    clock_rate: float,
    *,
    accuracy: float,
    combo: int | None,
    misses: int,
) -> PerformanceAttributes:
    performance = Performance()
    if mod_bitmask:
        performance.set_mods(mod_bitmask)
    if not _is_default_clock_rate(clock_rate):
        performance.set_clock_rate(clock_rate)
    performance.set_accuracy(accuracy)
    performance.set_misses(misses)
    if combo is not None:
        performance.set_combo(combo)
    return performance.calculate(beatmap)


def _build_rosu_result(pp: float | None, stars: float | None, max_combo: int) -> RosuPpResult:
    if pp is None or stars is None:
        msg = "rosu-pp returned None for PP or stars"
        raise RosuPpCalculationError(msg)

    logger.debug(f"[BeatmapUtils] Calculated PP: {pp:.2f}, Stars: {stars:.2f}")
    return {"pp": pp, "stars": stars, "max_combo": max_combo}


def _is_default_clock_rate(clock_rate: float) -> bool:
    return math.isclose(clock_rate, DEFAULT_CLOCK_RATE, rel_tol=0.0, abs_tol=CLOCK_RATE_TOLERANCE)


def delete_osu_file(osu_file_path: str) -> None:
    """Delete a temporary .osu file if it lives in the configured temp directory."""
    file_path = Path(osu_file_path)
    if not _is_temp_osu_file(file_path):
        logger.debug(f"[BeatmapUtils] File not deleted, invalid temp path: {osu_file_path}")
        return
    if not file_path.exists():
        logger.debug(f"[BeatmapUtils] File not deleted, missing path: {osu_file_path}")
        return

    file_path.unlink()
    logger.debug(f"[BeatmapUtils] Deleted temporary file: {osu_file_path}")


def _is_temp_osu_file(file_path: Path) -> bool:
    temp_dir = TEMP_OSU_DIR.resolve()
    resolved_file = file_path.resolve()
    return resolved_file.suffix == ".osu" and temp_dir in resolved_file.parents
