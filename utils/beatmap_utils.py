import asyncio
import aiohttp
import aiofiles
import os
import re
import time
from loguru import logger
# Placeholder for rosu_pp, assuming it's installed
# import rosu_pp_py as rosu_pp # Or the correct import name

OSU_BEATMAP_DOWNLOAD_URL = "https://osu.ppy.sh/osu/{beatmap_id}"
TEMP_OSU_DIR = "./temp"


# --- Custom Exceptions ---
class BeatmapProcessingError(Exception):
    """Base class for errors during beatmap processing."""

    pass


class BeatmapDownloadError(BeatmapProcessingError):
    """Raised when a .osu file download fails."""

    pass


class RosuPpCalculationError(BeatmapProcessingError):
    """Raised when rosu-pp calculation fails."""

    pass


# Mod bitmasks - Reference: https://github.com/ppy/osu-api/wiki/Display-Mods
# And common interpretations for PP calculators.
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

# Ensure temp directory exists (though ideally bot doesn't create dirs on the fly)
# os.makedirs(TEMP_OSU_DIR, exist_ok=True) # User should create this

BEATMAP_STATUS_EMOJIS = {
    "ranked": "<:ranked:1378350261323694221>",
    "qualified": "<:AorQ:1378350246647566346>",
    "approved": "<:AorQ:1378350246647566346>",
    "loved": "<:loved:1378350254805483560>",
    "pending": "<:WorP:1378351617253838938>",
    "wip": "<:WorP:1378351617253838938>",
    "graveyard": "<:WorP:1378351617253838938>",
    "unknown": "<:WorP:1378351617253838938>",  # Default emoji for unknown
}

BEATMAP_STATUS_API_MAP = {
    # API v2 `status` (string) and `ranked` (integer)
    # BeatmapCompact https://osu.ppy.sh/docs/index.html#beatmapcompact
    # BeatmapsetCompact https://osu.ppy.sh/docs/index.html#beatmapsetcompact
    "graveyard": "graveyard",  # -2
    "wip": "wip",  # -1 (Work in Progress)
    "pending": "pending",  # 0
    "ranked": "ranked",  # 1
    "approved": "approved",  # 2 (Note: osu! API v2 docs say "qualified" is 2, "approved" is 3. Check specific API responses)
    # However, common usage elsewhere seems to map `approved` string directly.
    # Let's assume string values from API are primary.
    "qualified": "qualified",  # 3 (API v2: status: "qualified", ranked: 3) -> This seems more consistent now.
    "loved": "loved",  # 4
    # Integer mapping (from `beatmap.status` or `beatmapset.status` if integer)
    # These integers align with `Beatmapset->status` or `Beatmap->status` when they are integers.
    # Often, the API might return `status` as a string like "ranked", "loved", etc.
    # And `ranked` as an integer (1 for ranked, 4 for loved, etc.)
    -2: "graveyard",
    -1: "wip",
    0: "pending",
    1: "ranked",
    2: "qualified",  # Mapping API int 2 to qualified
    3: "approved",  # Mapping API int 3 to approved
    4: "loved",
    # Fallback for older API versions or different fields if necessary
    "work-in-progress": "wip",  # from osu!direct or older API calls
}

# Mapping our internal status keys to the l10n keys for translations
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


def get_beatmap_status_display(status_input, user_id_for_l10n: int, lstr_func) -> str:
    """
    Returns the emoji and localized status string for a given beatmap status.
    status_input can be an integer (from API status field, e.g., beatmapset.ranked or beatmap.status (if int))
                 or a string (from API status field, e.g., beatmap.status or beatmapset.status (if str)).
    lstr_func is the localization function (e.g., from a cog: self.bot.l10n.get_lstr_value).
    """
    status_key = "unknown"  # Default

    if isinstance(status_input, str):
        normalized_status_str = status_input.lower().replace("_", "-").replace(" ", "-")
        if (
            normalized_status_str in BEATMAP_STATUS_API_MAP
        ):  # Direct match for string keys like "ranked"
            status_key = normalized_status_str
        elif (
            normalized_status_str == "approved"
        ):  # API v2 uses "approved" string, map it.
            status_key = (
                "approved"  # Ensure approved has its own key if distinct from qualified
            )
        elif normalized_status_str == "qualified":
            status_key = "qualified"
        # Add more explicit string mappings if needed
    elif isinstance(status_input, int):
        status_key = BEATMAP_STATUS_API_MAP.get(status_input, "unknown")

    # If status_key is still "unknown" but was a string, try to map it if it's a known status string key
    if (
        status_key == "unknown"
        and isinstance(status_input, str)
        and status_input.lower() in BEATMAP_STATUS_EMOJIS
    ):
        status_key = status_input.lower()

    emoji = BEATMAP_STATUS_EMOJIS.get(status_key, BEATMAP_STATUS_EMOJIS["unknown"])
    l10n_key_for_text = BEATMAP_STATUS_L10N_KEYS.get(
        status_key, BEATMAP_STATUS_L10N_KEYS["unknown"]
    )

    # The third argument to lstr_func is a fallback if the key is not found.
    # For "unknown", we might want a generic "Unknown Status" or just the status_key.
    status_text_localized = lstr_func(
        user_id_for_l10n, l10n_key_for_text, status_key.replace("-", " ").capitalize()
    )

    return f"{emoji} {status_text_localized}"


async def download_osu_file(
    beatmap_id: int, session: aiohttp.ClientSession
) -> str | None:
    """Downloads an .osu file for a given beatmap_id.
    Returns the path to the downloaded file.
    Raises BeatmapDownloadError if the download failed or temp directory doesn't exist.
    The file is saved in the TEMP_OSU_DIR.
    """
    if not os.path.exists(TEMP_OSU_DIR):
        err_msg = (
            f"Temporary directory {TEMP_OSU_DIR} does not exist. Please create it."
        )
        logger.error(f"[BeatmapUtils] Error: {err_msg}")
        raise BeatmapDownloadError(err_msg)

    file_name = f"{beatmap_id}_{int(time.time())}.osu"
    file_path = os.path.join(TEMP_OSU_DIR, file_name)
    url = OSU_BEATMAP_DOWNLOAD_URL.format(beatmap_id=beatmap_id)

    try:
        logger.debug(f"[BeatmapUtils] Downloading .osu file from: {url}")
        async with session.get(url) as response:
            if response.status == 200:
                async with aiofiles.open(file_path, "wb") as f:
                    await f.write(await response.read())
                logger.debug(f"[BeatmapUtils] Successfully downloaded {file_path}")
                return file_path
            else:
                error_detail = f"HTTP {response.status}"
                try:  # Try to get more error details from response
                    text_response = await response.text()
                    error_detail += (
                        f": {text_response[:200]}"  # Limit length of error message
                    )
                except Exception:
                    pass  # Ignore if cannot get text
                err_msg = f"Error downloading .osu file: {error_detail} for URL {url}"
                logger.error(f"[BeatmapUtils] {err_msg}")
                raise BeatmapDownloadError(err_msg)
    except aiohttp.ClientError as e:
        err_msg = f"ClientError during .osu download for {url}: {e}"
        logger.error(f"[BeatmapUtils] {err_msg}")
        raise BeatmapDownloadError(err_msg) from e
    except Exception as e:  # Catch any other unexpected errors
        err_msg = (
            f"Unexpected error during .osu download for {url}: {type(e).__name__} - {e}"
        )
        logger.error(f"[BeatmapUtils] {err_msg}")
        raise BeatmapDownloadError(err_msg) from e


def parse_osu_file_metadata(osu_file_path: str) -> dict:
    """Parses an .osu file to extract Title, Artist, and Version from the [Metadata] section."""
    metadata = {"title": None, "artist": None, "version": None}
    try:
        with open(osu_file_path, "r", encoding="utf-8") as f:
            in_metadata_section = False
            for line in f:
                line = line.strip()
                if line == "[Metadata]":
                    in_metadata_section = True
                    continue
                if in_metadata_section:
                    if (
                        line.startswith("Title:") and metadata["title"] is None
                    ):  # Prefer first Title found
                        metadata["title"] = line[len("Title:") :].strip()
                    elif (
                        line.startswith("TitleUnicode:") and metadata["title"] is None
                    ):  # Fallback to TitleUnicode
                        metadata["title"] = line[len("TitleUnicode:") :].strip()
                    elif line.startswith("Artist:") and metadata["artist"] is None:
                        metadata["artist"] = line[len("Artist:") :].strip()
                    elif (
                        line.startswith("ArtistUnicode:") and metadata["artist"] is None
                    ):
                        metadata["artist"] = line[len("ArtistUnicode:") :].strip()
                    elif line.startswith("Version:") and metadata["version"] is None:
                        metadata["version"] = line[len("Version:") :].strip()
                    elif line.startswith("[") and line.endswith(
                        "]"
                    ):  # Reached another section
                        break
            # If any metadata is still None, default them to avoid issues, or they can be handled upstream
            if metadata["title"] is None:
                metadata["title"] = "Unknown Title"
            if metadata["artist"] is None:
                metadata["artist"] = "Unknown Artist"
            if metadata["version"] is None:
                metadata["version"] = "Unknown Version"
        logger.debug(f"[BeatmapUtils] Parsed metadata: {metadata} from {osu_file_path}")
    except Exception as e:
        logger.error(
            f"[BeatmapUtils] Error parsing .osu file metadata for {osu_file_path}: {e}"
        )
        if metadata["title"] is None:
            metadata["title"] = "Error Parsing Title"
        if metadata["artist"] is None:
            metadata["artist"] = "Error Parsing Artist"
        if metadata["version"] is None:
            metadata["version"] = "Error Parsing Version"
    return metadata


def get_mods_bitmask_and_clock_rate(
    selected_mods: list[str],
) -> tuple[int, float | None]:
    """Converts a list of mod acronyms to a bitmask and determines clock rate."""
    bitmask = 0
    clock_rate = 1.0  # Default clock rate

    if not selected_mods:
        return 0, clock_rate

    # Make a copy to avoid modifying the original list if 'NC' needs 'DT'
    mods_for_processing = list(selected_mods)

    if "NC" in mods_for_processing and "DT" not in mods_for_processing:
        mods_for_processing.append("DT")  # Nightcore implies Double Time

    for mod in mods_for_processing:
        mod_upper = mod.upper()
        if mod_upper in MOD_ACRONYMS_TO_BITMASK:
            bitmask |= MOD_ACRONYMS_TO_BITMASK[mod_upper]

        if mod_upper == "DT" or mod_upper == "NC":
            clock_rate = 1.5
        elif mod_upper == "HT":
            clock_rate = 0.75

    # If both DT/NC and HT are somehow selected, which is unusual,
    # the last one processed in typical list order might take precedence for clock_rate.
    # Or, one might want to define specific behavior (e.g., error or default).
    # For simplicity, this implementation lets the last one set it.
    # A more robust way would be to disallow conflicting mods earlier or have rosu-pp handle it.

    return bitmask, clock_rate


async def calculate_pp_with_rosu(
    osu_file_path: str,
    selected_mods: list[str],
    accuracy: float = 100.0,
    combo: int | None = None,  # Max combo if None
    misses: int = 0,
) -> dict | None:
    """Calculates PP using rosu-pp-py.
    Returns a dict with 'pp', 'stars', and 'max_combo'.
    Raises RosuPpCalculationError if calculation failed or rosu-pp-py is not found.
    """
    try:
        try:
            from rosu_pp_py import (
                Beatmap,
                Difficulty,
                Performance,
            )  # Adjust import if needed
        except ImportError as e:
            err_msg = "rosu-pp-py library not found. Please install it."
            logger.error(f"[BeatmapUtils] Error: {err_msg}")
            raise RosuPpCalculationError(err_msg) from e

        logger.debug(
            f"[BeatmapUtils] Calculating PP for: {osu_file_path} with mods {selected_mods}, acc {accuracy}%"
        )

        beatmap_obj = Beatmap(path=osu_file_path)  # Load the beatmap

        mod_bitmask, clock_rate = get_mods_bitmask_and_clock_rate(selected_mods)

        # Calculate difficulty attributes first, as these are often useful and sometimes needed by Performance
        difficulty_calculator = Difficulty(mods=mod_bitmask)
        if (
            clock_rate != 1.0
        ):  # rosu-pp typically handles None clock_rate as 1.0, but explicit is fine
            difficulty_calculator.set_clock_rate(clock_rate)

        difficulty_attrs = difficulty_calculator.calculate(beatmap_obj)

        stars = difficulty_attrs.stars
        max_combo_from_calc = difficulty_attrs.max_combo

        # Determine the combo to use for PP calculation
        actual_combo = combo if combo is not None else max_combo_from_calc

        # Calculate performance attributes using the direct calculation method
        # This often involves creating a Performance object and then calling calculate on it
        # with the beatmap and score state.

        # Instantiate Performance. The TypeError suggested it takes no args, or specific named args.
        perf_calc = Performance()

        # Set attributes for performance calculation via methods if available,
        # or pass them to calculate() if that's the API.
        # Common pattern for rosu-pp-py is to chain or pass to calculate.

        # For many rosu-pp-py versions, you pass parameters to the calculate method of Performance.
        # The calculate method itself might need the beatmap object or its pre-calculated attributes.

        # Option 1: Pass everything to calculate (if Performance() is just a holder)
        # This is a common pattern if Performance() itself does not store state from constructor.
        # perf_attrs = perf_calc.calculate(
        #     beatmap_obj, # Pass the Beatmap object
        #     mods=mod_bitmask, # Redundant if difficulty_attrs is used and mods are baked in, but some APIs want it
        #     acc=accuracy,
        #     combo=actual_combo,
        #     misses=misses,
        #     # clock_rate might be passed here too if not handled by Difficulty effectively for Performance
        # )

        # Option 2: Chain methods (more typical for recent rosu-pp-py versions)
        # This relies on Performance() returning self to allow chaining.
        # We'll try chaining approach first as it's common.

        perf_setup = perf_calc  # Start with the base Performance object

        if mod_bitmask:  # Some versions of rosu-pp-py want mods on Performance too
            perf_setup.set_mods(mod_bitmask)
        if clock_rate and clock_rate != 1.0:
            perf_setup.set_clock_rate(clock_rate)  # If set_clock_rate exists

        perf_setup.set_accuracy(accuracy)
        perf_setup.set_misses(misses)  # Changed from set_n_misses
        if actual_combo is not None:
            perf_setup.set_combo(actual_combo)

        # And then calculate, passing the beatmap object.
        # Some versions might want `difficulty_attrs` passed here instead of re-calculating internally or needing beatmap_obj
        perf_attrs = perf_setup.calculate(
            beatmap_obj
        )  # or calculate(difficulty_attrs) if API expects that

        pp = perf_attrs.pp

        if pp is None or stars is None:
            err_msg = "rosu-pp calculation returned None for PP or Stars. Mode might not be fully supported for PP."
            logger.error(f"[BeatmapUtils] {err_msg} Path: {osu_file_path}")
            raise RosuPpCalculationError(err_msg)

        logger.debug(
            f"[BeatmapUtils] Calculated PP: {pp:.2f}, Stars: {stars:.2f}, Max Combo: {max_combo_from_calc}"
        )
        return {"pp": pp, "stars": stars, "max_combo": max_combo_from_calc}

    except TypeError as te:  # Catch the specific TypeError we saw
        err_msg = f"TypeError during rosu-pp setup/calculation (check API compatibility for Performance class): {te} for {osu_file_path}"
        logger.exception(f"[BeatmapUtils] {err_msg}")
        raise RosuPpCalculationError(err_msg) from te
    except Exception as e:
        err_msg = f"Error during rosu-pp calculation for {osu_file_path}: {type(e).__name__} - {e}"
        logger.exception(f"[BeatmapUtils] {err_msg}")
        raise RosuPpCalculationError(err_msg) from e


def delete_osu_file(osu_file_path: str):
    """Deletes the specified .osu file from the temp directory."""
    try:
        if (
            osu_file_path
            and os.path.exists(osu_file_path)
            and TEMP_OSU_DIR in osu_file_path
        ):  # Safety check
            os.remove(osu_file_path)
            logger.debug(f"[BeatmapUtils] Deleted temporary file: {osu_file_path}")
        else:
            logger.debug(
                f"[BeatmapUtils] File not deleted (not found or invalid path): {osu_file_path}"
            )
    except Exception as e:
        logger.error(
            f"[BeatmapUtils] Error deleting temporary file {osu_file_path}: {e}"
        )


# Example usage and if __name__ == "__main__" block will be removed.
