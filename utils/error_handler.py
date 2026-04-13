from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from utils.exceptions import BusinessError, DatabaseOperationError, OnCooldownError
from utils.misc import capture_exception
from utils.response_embeds import ErrorEmbed, WarningEmbed

if TYPE_CHECKING:
    from discord.ext.commands import Context


def _build_unknown_error_embed() -> discord.Embed:
    return ErrorEmbed(
        author_name="發生未知錯誤",
        description="發生了一個未知錯誤，我們已經記錄下來，請稍後再試。",
    )


def _build_permission_embed(
    *,
    author_name: str,
    missing_permissions: list[str],
    subject: str,
) -> discord.Embed:
    permissions_text = "、".join(missing_permissions)
    description = (
        f"{subject}「{permissions_text}」權限才能執行此操作。"
        if permissions_text
        else "缺少必要權限，無法執行此操作。"
    )
    return ErrorEmbed(author_name=author_name, description=description)


def get_error_embed(error: Exception) -> tuple[discord.Embed | None, bool]:
    if isinstance(error, (app_commands.CommandInvokeError, commands.CommandInvokeError)):
        original_error = getattr(error, "original", None)
        if isinstance(original_error, Exception):
            error = original_error

    recognized = True

    if isinstance(error, (app_commands.CommandOnCooldown, commands.CommandOnCooldown)):
        retry_after = getattr(error, "retry_after", None)
        description = (
            f"此操作正在冷卻中，請在 `{retry_after:.1f}` 秒後再試。"
            if retry_after is not None
            else "此操作正在冷卻中，請稍後再試。"
        )
        embed = WarningEmbed(author_name="冷卻中", description=description)
    elif isinstance(error, commands.MaxConcurrencyReached):
        embed = WarningEmbed(
            author_name="操作繁忙",
            description=f"此操作目前已達最大同時執行數 ({error.number})，請稍後再試。",
        )
    elif isinstance(error, DatabaseOperationError):
        recognized = False
        embed = ErrorEmbed(
            author_name=error.author_name,
            description="資料庫暫時無法處理你的請求，請稍後再試。",
        )
    elif isinstance(error, OnCooldownError) and not error.show_user:
        return None, True
    elif isinstance(error, BusinessError):
        embed = WarningEmbed(
            author_name=error.author_name,
            description=error.description,
        )
    elif isinstance(
        error, (app_commands.errors.MissingPermissions, commands.MissingPermissions)
    ):
        embed = _build_permission_embed(
            author_name="權限不足",
            missing_permissions=list(error.missing_permissions),
            subject="你需要",
        )
    elif isinstance(
        error,
        (
            app_commands.errors.BotMissingPermissions,
            commands.BotMissingPermissions,
        ),
    ):
        embed = _build_permission_embed(
            author_name="機器人權限不足",
            missing_permissions=list(error.missing_permissions),
            subject="我需要",
        )
    elif isinstance(error, commands.NoPrivateMessage):
        embed = WarningEmbed(
            author_name="無法在私訊使用",
            description="此操作無法在私訊中使用，請到伺服器頻道操作。",
        )
    elif isinstance(error, commands.CheckFailure):
        embed = ErrorEmbed(
            author_name="檢查失敗",
            description="你不符合執行此操作的條件。",
        )
    elif isinstance(error, discord.NotFound) or (
        isinstance(error, discord.HTTPException) and error.code == 50027
    ):
        return None, True
    elif isinstance(error, discord.Forbidden):
        embed = ErrorEmbed(
            author_name="權限不足",
            description="機器人在此頻道缺少必要權限，無法完成這個操作。",
        )
    else:
        recognized = False
        embed = _build_unknown_error_embed()

    return embed, recognized


async def _send_interaction_response(
    interaction: discord.Interaction,
    *,
    embed: discord.Embed | None,
    ephemeral: bool = True,
) -> None:
    if embed is None:
        return

    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
    except discord.NotFound as exc:
        logger.debug("互動已過期，無法發送錯誤訊息: {error}", error=exc)
    except discord.HTTPException as exc:
        capture_exception(exc, context="發送互動錯誤訊息失敗", level="warning")


async def handle_interaction_error(
    interaction: discord.Interaction,
    error: Exception,
    _bot: commands.Bot,
) -> None:
    embed, recognized = get_error_embed(error)

    if not recognized:
        if isinstance(error, DatabaseOperationError) and error.original_exception:
            capture_exception(error.original_exception, context="資料庫互動錯誤")
        else:
            capture_exception(error, context="互動處理失敗")

    await _send_interaction_response(interaction, embed=embed)


async def handle_prefix_command_error(
    ctx: Context[commands.Bot],
    error: Exception,
) -> None:
    embed, recognized = get_error_embed(error)

    if not recognized:
        if isinstance(error, DatabaseOperationError) and error.original_exception:
            capture_exception(error.original_exception, context="前綴指令資料庫錯誤")
        else:
            capture_exception(error, context="前綴指令處理失敗")

    if embed is None:
        return

    try:
        await ctx.reply(embed=embed, mention_author=False)
    except discord.HTTPException as exc:
        capture_exception(exc, context="發送前綴指令錯誤訊息失敗", level="warning")
