"""Era TW Sprite Sheet 處理與上傳腳本

功能：
1. 解析 CSV 定義檔（立ち絵.csv, 顔.csv）
2. 從 Sprite Sheet 裁剪出獨立圖片
3. 上傳到 Discord CDN
4. 記錄 URL 對照表

使用方式：
    uv run python scripts/upload_era_sprites.py
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
import io
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict, field
from typing import Literal

from PIL import Image
import discord
from discord.ext import commands
from loguru import logger

# 設定
UPLOAD_CHANNEL_ID = 1449026667774476379
RESOURCES_PATH = Path("eraTW/resources")
RECORD_FILE = Path("private/era_sprite_urls.json")
CSV_FILES = {"立绘": RESOURCES_PATH / "立ち絵.csv", "颜绘": RESOURCES_PATH / "顔.csv"}

# 批次設定
BATCH_SIZE = 5  # 每批上傳數量（裁剪後的圖片較小）
DELAY_BETWEEN_BATCHES = 1.5  # 批次間隔（秒）


@dataclass
class SpriteDefinition:
    """Sprite 定義"""

    name: str  # 資源名稱，如 "立绘_服_通常_1"
    filename: str  # 原始檔案名，如 "1.webp"
    x: int  # X 座標
    y: int  # Y 座標
    width: int  # 寬度
    height: int  # 高度
    category: str  # 類別（立绘/颜绘）


@dataclass
class UploadRecord:
    """上傳記錄"""

    sprite_name: str
    url: str
    status: Literal["success", "failed", "skipped"]
    error: str | None = None
    uploaded_at: str | None = None
    original_file: str = ""
    crop_rect: tuple[int, int, int, int] = field(default_factory=tuple)


class SpriteManager:
    """Sprite 管理器"""

    def __init__(self, resources_path: Path):
        self.resources_path = resources_path
        self.sprites: dict[str, SpriteDefinition] = {}
        self.records: dict[str, UploadRecord] = {}
        self._load_records()

    def _load_records(self):
        """載入已上傳記錄"""
        if RECORD_FILE.exists():
            try:
                with open(RECORD_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for name, record_data in data.items():
                        # 處理 tuple 轉換
                        if "crop_rect" in record_data and isinstance(
                            record_data["crop_rect"], list
                        ):
                            record_data["crop_rect"] = tuple(record_data["crop_rect"])
                        self.records[name] = UploadRecord(**record_data)
                logger.info(f"已載入 {len(self.records)} 筆上傳記錄")
            except Exception as e:
                logger.error(f"載入記錄失敗: {e}")

    def save_records(self):
        """儲存記錄"""
        RECORD_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(RECORD_FILE, "w", encoding="utf-8") as f:
            data = {}
            for name, record in self.records.items():
                d = asdict(record)
                # tuple 轉 list 以便 JSON 序列化
                d["crop_rect"] = list(d["crop_rect"])
                data[name] = d
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"已儲存 {len(self.records)} 筆記錄")

    def parse_csv(self, csv_path: Path, category: str) -> int:
        """解析 CSV 定義檔

        Args:
            csv_path: CSV 檔案路徑
            category: 類別（立绘/颜绘）

        Returns:
            解析的 sprite 數量
        """
        count = 0

        with open(csv_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()

                # 跳過註解和空行
                if not line or line.startswith(";"):
                    continue

                parts = line.split(",")
                if len(parts) < 6:
                    continue

                try:
                    name = parts[0].strip()
                    filename = parts[1].strip()
                    x = int(parts[2].strip())
                    y = int(parts[3].strip())
                    width = int(parts[4].strip())
                    height = int(parts[5].strip())

                    # 跳過 dummy
                    if "ダミー" in filename:
                        continue

                    sprite = SpriteDefinition(
                        name=name,
                        filename=filename,
                        x=x,
                        y=y,
                        width=width,
                        height=height,
                        category=category,
                    )
                    self.sprites[name] = sprite
                    count += 1

                except (ValueError, IndexError) as e:
                    logger.debug(f"跳過無效行: {line[:50]}...")

        return count

    def load_all_definitions(self) -> dict[str, int]:
        """載入所有 CSV 定義"""
        stats = {}

        for category, csv_path in CSV_FILES.items():
            if csv_path.exists():
                count = self.parse_csv(csv_path, category)
                stats[category] = count
                logger.info(f"從 {csv_path.name} 載入 {count} 個 sprite 定義")
            else:
                logger.warning(f"找不到 {csv_path}")
                stats[category] = 0

        return stats

    def crop_sprite(self, sprite: SpriteDefinition) -> bytes | None:
        """從 Sprite Sheet 裁剪出圖片

        Args:
            sprite: Sprite 定義

        Returns:
            PNG 格式的圖片位元組，失敗返回 None
        """
        image_path = self.resources_path / sprite.filename

        if not image_path.exists():
            logger.warning(f"找不到圖片: {sprite.filename}")
            return None

        try:
            with Image.open(image_path) as img:
                # 計算裁剪區域
                left = sprite.x
                top = sprite.y
                right = sprite.x + sprite.width
                bottom = sprite.y + sprite.height

                # 檢查邊界
                if right > img.width or bottom > img.height:
                    logger.warning(
                        f"裁剪區域超出圖片邊界: {sprite.name} "
                        f"({right}x{bottom} > {img.width}x{img.height})"
                    )
                    return None

                # 裁剪
                cropped = img.crop((left, top, right, bottom))

                # 轉換為 PNG 位元組
                buffer = io.BytesIO()
                cropped.save(buffer, format="PNG")
                buffer.seek(0)

                return buffer.getvalue()

        except Exception as e:
            logger.error(f"裁剪失敗 {sprite.name}: {e}")
            return None

    def is_uploaded(self, sprite_name: str) -> bool:
        """檢查是否已上傳"""
        record = self.records.get(sprite_name)
        return record is not None and record.status == "success"

    def get_pending_sprites(self) -> list[SpriteDefinition]:
        """取得待上傳的 sprites"""
        pending = []
        for name, sprite in self.sprites.items():
            if not self.is_uploaded(name):
                pending.append(sprite)
        return pending

    def get_url(self, sprite_name: str) -> str | None:
        """取得已上傳的 URL"""
        record = self.records.get(sprite_name)
        if record and record.status == "success":
            return record.url
        return None


async def upload_sprites(
    manager: SpriteManager, bot_token: str, channel_id: int, limit: int | None = None
):
    """上傳 sprites 到 Discord"""

    pending = manager.get_pending_sprites()

    if limit:
        pending = pending[:limit]

    if not pending:
        logger.info("沒有待上傳的 sprites")
        return

    logger.info(f"準備上傳 {len(pending)} 個 sprites")

    # 統計
    stats = {"uploaded": 0, "failed": 0, "skipped": 0}

    # 建立 Bot
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        logger.info(f"已登入: {bot.user}")

        channel = bot.get_channel(channel_id)
        if not channel:
            logger.error(f"找不到頻道: {channel_id}")
            await bot.close()
            return

        logger.info(f"目標頻道: {channel.name}")

        # 分批上傳
        for i in range(0, len(pending), BATCH_SIZE):
            batch = pending[i : i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            total_batches = (len(pending) + BATCH_SIZE - 1) // BATCH_SIZE

            logger.info(f"批次 {batch_num}/{total_batches} ({len(batch)} 個)")

            for sprite in batch:
                try:
                    # 裁剪圖片
                    image_data = manager.crop_sprite(sprite)

                    if not image_data:
                        stats["failed"] += 1
                        manager.records[sprite.name] = UploadRecord(
                            sprite_name=sprite.name,
                            url="",
                            status="failed",
                            error="裁剪失敗",
                            original_file=sprite.filename,
                        )
                        continue

                    # 上傳
                    file = discord.File(io.BytesIO(image_data), filename=f"{sprite.name}.png")

                    message = await channel.send(content=f"`{sprite.name}`", file=file)

                    if message.attachments:
                        url = message.attachments[0].url

                        manager.records[sprite.name] = UploadRecord(
                            sprite_name=sprite.name,
                            url=url,
                            status="success",
                            uploaded_at=datetime.now().isoformat(),
                            original_file=sprite.filename,
                            crop_rect=(sprite.x, sprite.y, sprite.width, sprite.height),
                        )
                        stats["uploaded"] += 1
                        logger.info(f"✅ {sprite.name}")
                    else:
                        raise Exception("訊息沒有附件")

                except Exception as e:
                    logger.error(f"❌ {sprite.name}: {e}")
                    stats["failed"] += 1
                    manager.records[sprite.name] = UploadRecord(
                        sprite_name=sprite.name,
                        url="",
                        status="failed",
                        error=str(e),
                        original_file=sprite.filename,
                    )

            # 每批次儲存
            manager.save_records()

            # 延遲
            if i + BATCH_SIZE < len(pending):
                await asyncio.sleep(DELAY_BETWEEN_BATCHES)

        # 完成
        logger.info("=" * 50)
        logger.info("上傳完成！")
        logger.info(f"  成功: {stats['uploaded']}")
        logger.info(f"  失敗: {stats['failed']}")
        logger.info("=" * 50)

        await bot.close()

    await bot.start(bot_token)


def export_url_map(manager: SpriteManager):
    """匯出 URL 對照表"""
    output_file = Path("private/era_sprite_map.json")

    url_map = {}
    for name, record in manager.records.items():
        if record.status == "success":
            url_map[name] = {"url": record.url, "original": record.original_file}

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(url_map, f, ensure_ascii=False, indent=2)

    logger.info(f"已匯出 {len(url_map)} 個 URL 到 {output_file}")


def filter_by_character(manager: SpriteManager, char_ids: list[int]) -> list[str]:
    """篩選特定角色的 sprites"""
    result = []
    for name in manager.sprites.keys():
        for cid in char_ids:
            if name.endswith(f"_{cid}") or f"_{cid}_" in name:
                result.append(name)
                break
    return result


async def main():
    """主程式"""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from private import config

    manager = SpriteManager(RESOURCES_PATH)

    print("\n" + "=" * 60)
    print("Era TW Sprite 上傳工具")
    print("=" * 60)

    # 載入定義
    stats = manager.load_all_definitions()
    print(f"\n已載入定義:")
    for cat, count in stats.items():
        print(f"  {cat}: {count} 個")

    # 統計
    total = len(manager.sprites)
    uploaded = sum(1 for r in manager.records.values() if r.status == "success")
    failed = sum(1 for r in manager.records.values() if r.status == "failed")
    pending = total - uploaded

    print(f"\n狀態:")
    print(f"  總計: {total}")
    print(f"  已上傳: {uploaded}")
    print(f"  失敗: {failed}")
    print(f"  待上傳: {pending}")

    print("\n選擇操作:")
    print("  1. 上傳 MVP 角色 (1,11,15,16,50,26,23,31,38,54)")
    print("  2. 上傳全部待上傳")
    print("  3. 上傳指定數量")
    print("  4. 重試失敗的")
    print("  5. 匯出 URL 對照表")
    print("  6. 查看特定角色 URL")
    print("  0. 離開")
    print()

    choice = input("請選擇 (0-6): ").strip()

    if choice == "1":
        # MVP 角色
        mvp_ids = [1, 11, 15, 16, 50, 26, 23, 31, 38, 54]
        mvp_sprites = filter_by_character(manager, mvp_ids)

        # 只保留待上傳的
        to_upload = [s for s in mvp_sprites if not manager.is_uploaded(s)]
        print(f"\nMVP 角色共 {len(mvp_sprites)} 個 sprites，待上傳 {len(to_upload)} 個")

        if to_upload and input("確認上傳？(y/n): ").lower() == "y":
            # 暫時只保留 MVP sprites
            original_sprites = manager.sprites.copy()
            manager.sprites = {k: v for k, v in manager.sprites.items() if k in mvp_sprites}

            await upload_sprites(manager, config.DISCORD_BOT_TOKEN, UPLOAD_CHANNEL_ID)

            manager.sprites = original_sprites

    elif choice == "2":
        if pending > 0 and input(f"確認上傳 {pending} 個？(y/n): ").lower() == "y":
            await upload_sprites(manager, config.DISCORD_BOT_TOKEN, UPLOAD_CHANNEL_ID)

    elif choice == "3":
        try:
            limit = int(input("輸入數量: "))
            if limit > 0:
                await upload_sprites(manager, config.DISCORD_BOT_TOKEN, UPLOAD_CHANNEL_ID, limit)
        except ValueError:
            print("無效數字")

    elif choice == "4":
        # 重試失敗
        failed_names = [n for n, r in manager.records.items() if r.status == "failed"]
        if failed_names:
            for name in failed_names:
                del manager.records[name]
            manager.save_records()
            print(f"已重置 {len(failed_names)} 個失敗記錄")
            await upload_sprites(manager, config.DISCORD_BOT_TOKEN, UPLOAD_CHANNEL_ID)
        else:
            print("沒有失敗記錄")

    elif choice == "5":
        export_url_map(manager)

    elif choice == "6":
        char_id = input("輸入角色 ID: ").strip()
        if char_id:
            for name, record in manager.records.items():
                if name.endswith(f"_{char_id}") or f"_{char_id}_" in name:
                    if record.status == "success":
                        print(f"  {name}: {record.url[:60]}...")

    elif choice == "0":
        print("再見！")


if __name__ == "__main__":
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO",
    )
    logger.add("logs/era_sprite_upload.log", rotation="10 MB", level="DEBUG")

    asyncio.run(main())
