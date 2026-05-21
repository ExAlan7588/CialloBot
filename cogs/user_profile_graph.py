from __future__ import annotations

import io
from typing import Any

import matplotlib.pyplot as plt
from loguru import logger

from utils.localization import get_localized_string as lstr

DEFAULT_GRAPH_BACKGROUND = "#23272A"
GRAPH_SPINE_COLOR = "#99aab5"
GRAPH_RANK_LINE_COLOR = "#bfaaff"
GRAPH_DPI = 120
GRAPH_WIDTH_INCHES = 7
GRAPH_HEIGHT_INCHES = 4


def generate_profile_rank_graph(
    rank_history_full: dict[str, Any] | None, user_id_for_l10n: int
) -> tuple[io.BytesIO | None, bool]:
    rank_data = rank_history_full.get("data") if rank_history_full else None
    if not rank_data:
        logger.info("No rank history data available to generate graph.")
        return None, False
    if 0 in rank_data:
        logger.info("Rank history data contains 0, so graph will not be generated.")
        return None, False

    fig, ax_rank = plt.subplots(
        1, 1, figsize=(GRAPH_WIDTH_INCHES, GRAPH_HEIGHT_INCHES), dpi=GRAPH_DPI
    )
    fig.patch.set_facecolor(DEFAULT_GRAPH_BACKGROUND)
    _style_rank_axis(ax_rank, rank_data, user_id_for_l10n)
    fig.tight_layout(pad=2.0)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    buffer.seek(0)
    plt.close(fig)
    logger.info("Successfully generated profile rank graph.")
    return buffer, True


def _style_rank_axis(ax_rank: Any, rank_data: list[int], user_id_for_l10n: int) -> None:
    plt.style.use("seaborn-v0_8-darkgrid")
    title = lstr(user_id_for_l10n, "graph_title_rank_history", "Rank History (90 days)")
    ax_rank.plot(
        list(range(1, len(rank_data) + 1)), rank_data, color=GRAPH_RANK_LINE_COLOR, linewidth=2
    )
    ax_rank.set_title(title, fontsize=12, color="white", pad=10)
    ax_rank.set_ylabel(lstr(user_id_for_l10n, "graph_ylabel_rank", "Rank"), color="white")
    ax_rank.invert_yaxis()
    ax_rank.tick_params(axis="x", colors="white")
    ax_rank.tick_params(axis="y", colors="white")
    ax_rank.grid(alpha=0.3)
    ax_rank.set_xlabel(
        lstr(user_id_for_l10n, "graph_xlabel_days", "Days (Most Recent)"), color="white"
    )
    ax_rank.set_facecolor(DEFAULT_GRAPH_BACKGROUND)
    for spine in ax_rank.spines.values():
        spine.set_color(GRAPH_SPINE_COLOR)
