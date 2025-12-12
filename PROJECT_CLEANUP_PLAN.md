# 項目整理計劃

## 📋 當前狀態分析

### 根目錄文件（過多）
```
✅ 保留 - 核心文件
- bot.py
- config.py
- requirements.txt
- StartUp.cmd
- *.json (配置文件)

📁 需要整理 - 文檔文件
- ADDING_DELETE_BUTTON_GUIDE.md
- CHANGELOG_DELETE_FEATURE.md
- FINAL_UPDATE_SUMMARY.md
- IMPLEMENTATION_SUMMARY.md
- KEYWORD_SYSTEM.md
- LOGGING_MIGRATION.md
- PRINT_TO_LOGURU_MIGRATION.md
- PRIVACY_POLICY.md
- QUICK_START_DELETE_FEATURE.md
- QUICK_START_KEYWORD.md
- QUICK_START.md
- TERMS_OF_SERVICE.md
- TESTING_DELETE_FEATURE.md
- UPDATE_SUMMARY_v2.md
```

## 🎯 建議的目錄結構

```
project/
├── bot.py                          # 主程式
├── config.py                       # 配置
├── requirements.txt                # 依賴
├── StartUp.cmd                     # 啟動腳本
├── *.json                          # 配置文件
│
├── cogs/                           # 功能模組
│   ├── keyword_cog.py
│   ├── copypasta_cog.py
│   └── ...
│
├── utils/                          # 工具模組
│   ├── message_tracker.py
│   ├── delete_view.py
│   └── ...
│
├── docs/                           # 📁 新建：文檔目錄
│   ├── README.md                   # 主文檔（整合 QUICK_START.md）
│   ├── KEYWORD_SYSTEM.md           # 關鍵詞系統文檔
│   ├── PRIVACY_POLICY.md           # 隱私政策
│   ├── TERMS_OF_SERVICE.md         # 服務條款
│   │
│   ├── guides/                     # 使用指南
│   │   ├── quick-start.md
│   │   └── keyword-quick-start.md
│   │
│   ├── development/                # 開發文檔
│   │   ├── adding-delete-button.md
│   │   ├── testing-guide.md
│   │   └── migration-guides/
│   │       ├── logging-migration.md
│   │       └── print-to-loguru.md
│   │
│   └── changelog/                  # 更新日誌
│       └── v3.0-delete-feature.md
│
├── logs/                           # 日誌文件
├── locales/                        # 語言文件
└── temp/                           # 臨時文件
```

## 📝 整理步驟

### 步驟 1：創建文檔目錄結構
```bash
mkdir docs
mkdir docs\guides
mkdir docs\development
mkdir docs\development\migration-guides
mkdir docs\changelog
```

### 步驟 2：移動和重命名文件

#### 用戶文檔 → docs/
- KEYWORD_SYSTEM.md → docs/KEYWORD_SYSTEM.md
- PRIVACY_POLICY.md → docs/PRIVACY_POLICY.md
- TERMS_OF_SERVICE.md → docs/TERMS_OF_SERVICE.md

#### 使用指南 → docs/guides/
- QUICK_START.md → docs/guides/quick-start.md
- QUICK_START_KEYWORD.md → docs/guides/keyword-quick-start.md

#### 開發文檔 → docs/development/
- ADDING_DELETE_BUTTON_GUIDE.md → docs/development/adding-delete-button.md
- TESTING_DELETE_FEATURE.md → docs/development/testing-guide.md

#### 遷移指南 → docs/development/migration-guides/
- LOGGING_MIGRATION.md → docs/development/migration-guides/logging-migration.md
- PRINT_TO_LOGURU_MIGRATION.md → docs/development/migration-guides/print-to-loguru.md

#### 更新日誌 → docs/changelog/
- 合併以下文件為一個：
  - CHANGELOG_DELETE_FEATURE.md
  - FINAL_UPDATE_SUMMARY.md
  - UPDATE_SUMMARY_v2.md
  - IMPLEMENTATION_SUMMARY.md
- 輸出：docs/changelog/v3.0-delete-feature.md

### 步驟 3：刪除重複文件

以下文件可以刪除（內容已整合）：
- QUICK_START_DELETE_FEATURE.md（整合到主文檔）
- CHANGELOG_DELETE_FEATURE.md（整合到 changelog）
- UPDATE_SUMMARY_v2.md（整合到 changelog）
- IMPLEMENTATION_SUMMARY.md（整合到 changelog）

### 步驟 4：創建主 README

創建 `docs/README.md` 作為文檔入口：
- 項目簡介
- 快速開始
- 功能列表
- 文檔索引

## ✅ 整理後的優點

1. **清晰的結構**：文檔按類型分類
2. **易於維護**：相關文檔集中管理
3. **更好的導航**：清晰的目錄層次
4. **減少混亂**：根目錄只保留核心文件

## ⚠️ 注意事項

1. **備份**：整理前先備份整個項目
2. **Git**：如果使用 Git，用 `git mv` 移動文件保留歷史
3. **鏈接**：檢查文檔中的相對鏈接是否需要更新
4. **README**：更新根目錄 README（如果有）

## 🚀 執行整理

你想要我：
1. **自動執行整理**（我會創建目錄並移動文件）
2. **只提供命令**（你手動執行）
3. **先看詳細計劃**（我提供更詳細的步驟）

請選擇一個選項，我會協助你完成整理！
