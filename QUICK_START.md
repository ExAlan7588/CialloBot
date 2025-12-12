# 快速啟動指南

## ✅ 環境已就緒

所有依賴已成功安裝，日誌系統已重構完成！

## 🚀 啟動 Bot

```bash
python bot.py
```

## 📊 日誌配置

### 當前配置
- **日誌文件**: `logs/bot.log`
- **日誌級別**: `INFO`（推薦用於生產環境）
- **日誌輪轉**: 每 10 MB 自動輪轉
- **日誌保留**: 保留 7 天

### 調整日誌級別

編輯 `bot.py` 中的 `main()` 函數：

```python
# 生產環境（推薦）- 只記錄重要信息
setup_logging(log_file="logs/bot.log", log_level="INFO")

# 開發環境 - 記錄詳細調試信息
setup_logging(log_file="logs/bot.log", log_level="DEBUG")
```

## 🎯 主要改進

### 1. Discord.py 日誌問題已解決
- ✅ 不再有混亂的 DEBUG 日誌污染
- ✅ 所有日誌統一通過 loguru 管理
- ✅ 自動攔截標準 logging 模組

### 2. 更好的日誌格式
**控制台輸出（彩色）：**
```
2025-12-07 17:43:05 | INFO     | bot:on_ready:89 - == Bot Ready ==
2025-12-07 17:43:05 | INFO     | bot:on_ready:90 - Logged in as: MyBot
```

**文件輸出（結構化）：**
```
2025-12-07 17:43:05 | INFO     | bot:on_ready:89 - == Bot Ready ==
2025-12-07 17:43:05 | INFO     | bot:on_ready:90 - Logged in as: MyBot
```

### 3. 自動日誌管理
- 文件大小達到 10 MB 自動輪轉
- 自動保留 7 天的日誌
- 不再需要手動管理 bot.log.1, bot.log.2 等

## 📝 在代碼中使用日誌

```python
from loguru import logger

# 不同級別的日誌
logger.debug("調試信息")
logger.info("一般信息")
logger.warning("警告信息")
logger.error("錯誤信息")
logger.success("成功信息")  # loguru 特有

# 帶異常追蹤的日誌
try:
    # 你的代碼
    pass
except Exception as e:
    logger.exception("發生錯誤")  # 自動包含完整堆疊追蹤
```

## 🔧 故障排除

### 問題：日誌文件太大
**解決方案：** 將日誌級別從 DEBUG 改為 INFO

### 問題：看不到某些日誌
**解決方案：** 檢查日誌級別設定，確認是否設為 DEBUG

### 問題：日誌沒有顏色
**解決方案：** 使用支援 ANSI 顏色的終端（Windows Terminal 或 PowerShell 7+）

## 📚 更多資訊

詳細的遷移文檔請參閱：[LOGGING_MIGRATION.md](LOGGING_MIGRATION.md)

## ✨ 測試結果

```
✅ Python 3.13.11 已安裝
✅ loguru 已安裝並正常工作
✅ discord.py 2.6.4 已安裝
✅ 所有依賴已安裝
✅ 日誌系統已測試並正常工作
```

現在你可以直接啟動 Bot 了！🎉
