"""Era TW 圖片上傳腳本

將 eraTW/resources 資料夾中的圖片上傳到 Discord 作為 CDN 使用。
記錄上傳狀態，避免重複上傳。

使用方式：
    uv run python scripts/upload_era_images.py

注意：需要在 private/config.py 中設定 DISCORD_BOT_TOKEN
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Literal

import discord
from discord.ext import commands
from loguru import logger

# 設定
UPLOAD_CHANNEL_ID = 1449023468522831923
RESOURCES_PATH = Path("eraTW/resources")
RECORD_FILE = Path("private/era_image_urls.json")
MAX_FILE_SIZE = 8 * 1024 * 1024  # 8MB Discord 限制
SUPPORTED_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg", ".gif"}

# 批次設定
BATCH_SIZE = 10  # 每批上傳數量
DELAY_BETWEEN_BATCHES = 2.0  # 批次間隔（秒）


@dataclass
class ImageRecord:
    """圖片記錄"""

    filename: str
    url: str
    status: Literal["success", "failed", "skipped"]
    error: str | None = None
    uploaded_at: str | None = None
    file_size: int = 0


class ImageUploadRecord:
    """圖片上傳記錄管理"""

    def __init__(self, record_file: Path):
        self.record_file = record_file
        self.records: dict[str, ImageRecord] = {}
        self._load()

    def _load(self):
        """載入記錄"""
        if self.record_file.exists():
            try:
                with open(self.record_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for filename, record_data in data.items():
                        self.records[filename] = ImageRecord(**record_data)
                logger.info(f"已載入 {len(self.records)} 筆上傳記錄")
            except Exception as e:
                logger.error(f"載入記錄失敗: {e}")
                self.records = {}
        else:
            logger.info("無現有記錄，將建立新檔案")

    def save(self):
        """儲存記錄"""
        self.record_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.record_file, "w", encoding="utf-8") as f:
            data = {k: asdict(v) for k, v in self.records.items()}
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"已儲存 {len(self.records)} 筆記錄到 {self.record_file}")

    def is_uploaded(self, filename: str) -> bool:
        """檢查是否已成功上傳"""
        record = self.records.get(filename)
        return record is not None and record.status == "success"

    def add_record(self, record: ImageRecord):
        """新增記錄"""
        self.records[record.filename] = record

    def get_url(self, filename: str) -> str | None:
        """取得圖片 URL"""
        record = self.records.get(filename)
        if record and record.status == "success":
            return record.url
        return None

    def get_stats(self) -> dict[str, int]:
        """取得統計"""
        stats = {"success": 0, "failed": 0, "skipped": 0, "total": len(self.records)}
        for record in self.records.values():
            if record.status in stats:
                stats[record.status] += 1
        return stats


class ImageUploader:
    """圖片上傳器"""

    def __init__(
        self, bot_token: str, channel_id: int, resources_path: Path, record: ImageUploadRecord
    ):
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.resources_path = resources_path
        self.record = record

        # 統計
        self.stats = {"uploaded": 0, "skipped": 0, "failed": 0, "total": 0}

    def get_all_images(self, recursive: bool = True) -> list[Path]:
        """取得所有圖片檔案"""
        images = []

        if recursive:
            for ext in SUPPORTED_EXTENSIONS:
                images.extend(self.resources_path.rglob(f"*{ext}"))
        else:
            for ext in SUPPORTED_EXTENSIONS:
                images.extend(self.resources_path.glob(f"*{ext}"))

        # 過濾大於限制的檔案
        valid_images = []
        for img in images:
            if img.stat().st_size <= MAX_FILE_SIZE:
                valid_images.append(img)
            else:
                logger.warning(
                    f"跳過過大的檔案: {img.name} ({img.stat().st_size / 1024 / 1024:.2f}MB)"
                )

        return sorted(valid_images)

    async def upload_all(self, recursive: bool = False):
        """上傳所有圖片"""
        images = self.get_all_images(recursive=recursive)
        self.stats["total"] = len(images)

        logger.info(f"找到 {len(images)} 個圖片檔案")

        # 過濾已上傳的
        to_upload = []
        for img in images:
            relative_path = str(img.relative_to(self.resources_path))
            if self.record.is_uploaded(relative_path):
                self.stats["skipped"] += 1
            else:
                to_upload.append(img)

        logger.info(f"需要上傳: {len(to_upload)} 個 (跳過已上傳: {self.stats['skipped']} 個)")

        if not to_upload:
            logger.info("沒有需要上傳的圖片")
            return

        # 建立 Bot
        intents = discord.Intents.default()
        bot = commands.Bot(command_prefix="!", intents=intents)

        @bot.event
        async def on_ready():
            logger.info(f"已登入: {bot.user}")

            channel = bot.get_channel(self.channel_id)
            if not channel:
                logger.error(f"找不到頻道: {self.channel_id}")
                await bot.close()
                return

            logger.info(f"目標頻道: {channel.name}")

            # 分批上傳
            for i in range(0, len(to_upload), BATCH_SIZE):
                batch = to_upload[i : i + BATCH_SIZE]
                batch_num = i // BATCH_SIZE + 1
                total_batches = (len(to_upload) + BATCH_SIZE - 1) // BATCH_SIZE

                logger.info(f"正在上傳批次 {batch_num}/{total_batches} ({len(batch)} 個檔案)")

                for img_path in batch:
                    relative_path = str(img_path.relative_to(self.resources_path))

                    try:
                        file = discord.File(img_path, filename=img_path.name)
                        message = await channel.send(content=f"`{relative_path}`", file=file)

                        # 取得上傳後的 URL
                        if message.attachments:
                            url = message.attachments[0].url

                            record = ImageRecord(
                                filename=relative_path,
                                url=url,
                                status="success",
                                uploaded_at=datetime.now().isoformat(),
                                file_size=img_path.stat().st_size,
                            )
                            self.record.add_record(record)
                            self.stats["uploaded"] += 1

                            logger.info(f"✅ 上傳成功: {relative_path}")
                        else:
                            raise Exception("訊息沒有附件")

                    except Exception as e:
                        logger.error(f"❌ 上傳失敗: {relative_path} - {e}")

                        record = ImageRecord(
                            filename=relative_path, url="", status="failed", error=str(e)
                        )
                        self.record.add_record(record)
                        self.stats["failed"] += 1

                # 每批次後儲存一次
                self.record.save()

                # 批次間延遲
                if i + BATCH_SIZE < len(to_upload):
                    await asyncio.sleep(DELAY_BETWEEN_BATCHES)

            # 完成
            logger.info("=" * 50)
            logger.info("上傳完成！")
            logger.info(f"  成功: {self.stats['uploaded']}")
            logger.info(f"  跳過: {self.stats['skipped']}")
            logger.info(f"  失敗: {self.stats['failed']}")
            logger.info(f"  總計: {self.stats['total']}")
            logger.info("=" * 50)

            await bot.close()

        await bot.start(self.bot_token)

    async def retry_failed(self):
        """重試失敗的上傳"""
        failed = [r for r in self.record.records.values() if r.status == "failed"]

        if not failed:
            logger.info("沒有失敗的上傳")
            return

        logger.info(f"將重試 {len(failed)} 個失敗的上傳")

        # 重置失敗的記錄
        for r in failed:
            del self.record.records[r.filename]

        self.record.save()

        # 重新上傳
        await self.upload_all()


async def main():
    """主程式"""
    # 載入 config
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from private import config

    # 初始化
    record = ImageUploadRecord(RECORD_FILE)
    uploader = ImageUploader(
        bot_token=config.DISCORD_BOT_TOKEN,
        channel_id=UPLOAD_CHANNEL_ID,
        resources_path=RESOURCES_PATH,
        record=record,
    )

    # 顯示選項
    print("\n" + "=" * 50)
    print("Era TW 圖片上傳工具")
    print("=" * 50)
    print(f"圖片來源: {RESOURCES_PATH}")
    print(f"記錄檔案: {RECORD_FILE}")
    print(f"目標頻道: {UPLOAD_CHANNEL_ID}")
    print()

    # 顯示現有統計
    stats = record.get_stats()
    print(f"現有記錄: 成功 {stats['success']} / 失敗 {stats['failed']} / 跳過 {stats['skipped']}")
    print()

    print("選擇操作:")
    print("  1. 上傳新圖片（僅根目錄）")
    print("  2. 上傳新圖片（包含子目錄）")
    print("  3. 重試失敗的上傳")
    print("  4. 顯示統計")
    print("  5. 匯出 URL 對照表")
    print("  0. 離開")
    print()

    choice = input("請選擇 (0-5): ").strip()

    if choice == "1":
        await uploader.upload_all(recursive=False)
    elif choice == "2":
        await uploader.upload_all(recursive=True)
    elif choice == "3":
        await uploader.retry_failed()
    elif choice == "4":
        stats = record.get_stats()
        print(f"\n統計:")
        print(f"  成功: {stats['success']}")
        print(f"  失敗: {stats['failed']}")
        print(f"  跳過: {stats['skipped']}")
        print(f"  總計: {stats['total']}")
    elif choice == "5":
        # 匯出 URL 對照表
        output_file = Path("private/era_image_map.json")
        url_map = {r.filename: r.url for r in record.records.values() if r.status == "success"}
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(url_map, f, ensure_ascii=False, indent=2)
        print(f"\n已匯出 {len(url_map)} 個 URL 到 {output_file}")
    elif choice == "0":
        print("再見！")
    else:
        print("無效選項")


if __name__ == "__main__":
    # 設定 logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO",
    )
    logger.add("logs/era_upload.log", rotation="10 MB", retention="7 days", level="DEBUG")

    asyncio.run(main())
