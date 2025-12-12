# 日誌系統遷移指南

## 概述

已成功將日誌系統從標準 Python `logging` 模組遷移到 `loguru`，並實現了對所有第三方庫（包括 discord.py）日誌的統一管理。

## 變更內容

### 新增文件

1. **`utils/log_intercept.py`** - 日誌攔截器
   - 提供 `InterceptHandler` 類別
   - 將標準 logging 模組的日誌重定向到 loguru

2. **`utils/startup.py`** - 啟動工具模組
   - `setup_logging()` - 初始化 loguru 日誌系統
   - `wrap_task_factory()` - 為 asyncio 任務添加全域錯誤處理

3. **`utils/misc.py`** - 雜項工具函數
   - `should_ignore_error()` - 判斷是否應該忽略特定錯誤
   - `capture_exception()` - 捕獲並記錄異常

### 修改文件

1. **`bot.py`** - 完全重構
   - 使用 loguru 替代 print 語句
   - 創建 `OsuBot` 類別繼承 `commands.Bot`
   - 實現完整的錯誤處理和資源清理
   - 添加 `setup_hook()` 進行異步初始化

2. **`cogs/osu_cog.py`**
   - 移除舊的 `logger_config` 導入
   - 改用 `from loguru import logger`

3. **`requirements.txt`**
   - 添加 `loguru` 依賴

### 刪除文件

1. **`utils/logger_config.py`** - 已刪除（被新系統取代）

## 主要優勢

### 1. 統一的日誌管理
- 所有日誌（包括 discord.py 的內部日誌）都通過 loguru 處理
- 不再有混亂的 Discord.py DEBUG 日誌污染你的日誌文件

### 2. 更好的日誌格式
- 控制台輸出：彩色、易讀
- 文件輸出：結構化、易於解析

### 3. 自動日誌輪轉
- 文件大小達到 10 MB 自動輪轉
- 自動保留 7 天的日誌
- 不再需要手動管理 bot.log.1, bot.log.2 等文件

### 4. 更好的錯誤追蹤
- 自動捕獲 asyncio 背景任務的異常
- 完整的堆疊追蹤信息

## 使用方法

### 基本使用

```python
from loguru import logger

# 不同級別的日誌
logger.debug("調試信息")
logger.info("一般信息")
logger.warning("警告信息")
logger.error("錯誤信息")
logger.critical("嚴重錯誤")
logger.success("成功信息")  # loguru 特有

# 帶異常追蹤的日誌
try:
    1 / 0
except Exception as e:
    logger.exception("發生錯誤")  # 自動包含堆疊追蹤
```

### 配置日誌級別

在 `bot.py` 的 `main()` 函數中：

```python
# 設定為 INFO（推薦用於生產環境）
setup_logging(log_file="logs/bot.log", log_level="INFO")

# 設定為 DEBUG（用於開發調試）
setup_logging(log_file="logs/bot.log", log_level="DEBUG")
```

### 日誌級別說明

- **DEBUG**: 詳細的調試信息（包括 Discord.py 的內部事件）
- **INFO**: 一般信息（推薦用於生產環境）
- **WARNING**: 警告信息
- **ERROR**: 錯誤信息
- **CRITICAL**: 嚴重錯誤

## Discord.py 日誌處理

### 問題解決

**之前的問題：**
- Discord.py 在 DEBUG 級別會記錄所有 WebSocket 事件
- 包括每條訊息、每個打字事件、成員列表更新等
- 導致日誌文件巨大且難以閱讀

**現在的解決方案：**
- 使用 `InterceptHandler` 攔截所有標準 logging 日誌
- Discord.py 的日誌通過 loguru 統一處理
- 可以通過設定日誌級別為 INFO 來過濾掉 DEBUG 日誌
- 即使設定為 DEBUG，日誌格式也更清晰易讀

### 日誌輸出示例

**控制台輸出（彩色）：**
```
2025-12-07 17:38:31 | INFO     | bot:on_ready:89 - == Bot Ready ==
2025-12-07 17:38:31 | INFO     | bot:on_ready:90 - Logged in as: MyBot (ID: 123456789)
```

**文件輸出（logs/bot.log）：**
```
2025-12-07 17:38:31 | INFO     | bot:on_ready:89 - == Bot Ready ==
2025-12-07 17:38:31 | INFO     | bot:on_ready:90 - Logged in as: MyBot (ID: 123456789)
```

## 測試

已創建 `test_logging.py` 用於測試日誌系統：

```bash
python test_logging.py
```

測試內容：
- ✅ loguru 日誌輸出
- ✅ 標準 logging 模組的攔截
- ✅ Discord.py 日誌的攔截
- ✅ 文件日誌輸出

## 遷移檢查清單

- [x] 安裝 loguru 依賴
- [x] 創建新的日誌模組
- [x] 重構 bot.py
- [x] 更新所有 cogs 的 logger 導入
- [x] 刪除舊的 logger_config.py
- [x] 測試日誌系統
- [x] 創建文檔

## 注意事項

1. **日誌文件位置**: `logs/bot.log`
2. **日誌輪轉**: 每 10 MB 自動輪轉
3. **日誌保留**: 保留 7 天
4. **推薦級別**: 生產環境使用 INFO，開發環境使用 DEBUG

## 故障排除

### 問題：日誌文件太大

**解決方案：**
- 將日誌級別從 DEBUG 改為 INFO
- 調整 `setup_logging()` 中的 `rotation` 參數（預設 10 MB）

### 問題：看不到 Discord.py 的日誌

**解決方案：**
- 確認日誌級別設定為 DEBUG
- 檢查 `InterceptHandler` 是否正確配置

### 問題：日誌沒有顏色

**解決方案：**
- 確認終端支援 ANSI 顏色碼
- Windows 用戶：使用 Windows Terminal 或 PowerShell 7+

## 參考資料

- [Loguru 官方文檔](https://loguru.readthedocs.io/)
- [Discord.py 日誌文檔](https://discordpy.readthedocs.io/en/stable/logging.html)
