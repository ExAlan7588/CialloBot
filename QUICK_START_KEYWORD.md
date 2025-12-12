# 關鍵詞系統快速開始

## ✅ 系統已就緒

關鍵詞觸發系統已成功安裝並測試完成！

## 🚀 立即開始

### 1. 啟動機器人

```bash
python bot.py
```

### 2. 在 Discord 中使用

#### 添加關鍵詞（僅管理員）

```
/keyword add keyword:你好 response:你好！歡迎來到我們的伺服器！
```

#### 測試觸發

在聊天頻道中發送：
```
你好
```

機器人會自動回覆：
```
你好！歡迎來到我們的伺服器！
```

#### 查看所有關鍵詞

```
/keyword list
```

#### 刪除關鍵詞

```
/keyword remove keyword:你好
```

## 👑 誰可以管理關鍵詞？

- ✅ 伺服器擁有者（Server Owner）
- ✅ 擁有「管理員」權限的成員

## 📝 常用示例

### 歡迎新成員

```
/keyword add keyword:新人報到 response:歡迎新朋友！請先閱讀規則，然後到自我介紹頻道介紹自己吧！
```

### 常見問題

```
/keyword add keyword:如何加入語音? response:點擊左側的語音頻道即可加入！
/keyword add keyword:機器人指令 response:使用 /help 查看所有可用指令
```

### 有趣互動

```
/keyword add keyword:早安 response:早安！今天也要元氣滿滿哦！☀️
/keyword add keyword:晚安 response:晚安～做個好夢！🌙
```

## 🎯 重要提示

1. **完全匹配**：關鍵詞必須完全匹配才會觸發
   - ✅ 關鍵詞「你好」→ 發送「你好」會觸發
   - ❌ 關鍵詞「你好」→ 發送「你好啊」不會觸發

2. **伺服器獨立**：每個伺服器的關鍵詞互不影響

3. **即時生效**：添加後立即可用，無需重啟

## 📚 完整文檔

詳細使用說明請查看：[KEYWORD_SYSTEM.md](KEYWORD_SYSTEM.md)

## 🎉 開始使用

現在你可以啟動機器人並開始添加關鍵詞了！

```bash
python bot.py
```

祝你使用愉快！🎊
