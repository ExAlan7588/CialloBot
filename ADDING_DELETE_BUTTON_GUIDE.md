# 為其他 Cogs 添加刪除按鈕指南

## 📋 概述

本指南說明如何為任何指令觸發的訊息添加刪除按鈕功能。

## 🎯 兩種刪除方式

### 方式 1：刪除按鈕（Button）
**適用於：** Slash Commands（應用程式指令）
**示例：** `/copypasta`、`/help` 等

**特點：**
- 訊息下方顯示「刪除」按鈕
- 觸發者或管理員可以點擊刪除
- 5 分鐘後按鈕自動失效

### 方式 2：右鍵菜單（Context Menu）
**適用於：** 訊息監聽器（Message Listener）
**示例：** 關鍵詞觸發的回覆

**特點：**
- 右鍵點擊訊息，選擇「刪除此回覆」
- 需要使用 `reply()` 來追蹤觸發者
- 顯示確認對話框

## 🔧 實現方式 1：添加刪除按鈕

### 步驟 1：導入 DeleteMessageView

```python
from utils.delete_view import DeleteMessageView
```

### 步驟 2：在發送訊息時添加視圖

**原始代碼：**
```python
await interaction.response.send_message("你的訊息內容")
```

**修改後：**
```python
# 創建刪除按鈕視圖
delete_view = DeleteMessageView(
    trigger_user_id=interaction.user.id,
    guild=interaction.guild
)

# 發送訊息並附加視圖
await interaction.response.send_message(
    "你的訊息內容",
    view=delete_view
)
```

### 完整示例

```python
from discord import app_commands
from discord.ext import commands
from utils.delete_view import DeleteMessageView

class YourCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="yourcommand", description="你的指令描述")
    async def your_command(self, interaction: discord.Interaction):
        # 你的指令邏輯
        result = "這是指令的回覆內容"
        
        # 創建刪除按鈕視圖
        delete_view = DeleteMessageView(
            trigger_user_id=interaction.user.id,
            guild=interaction.guild
        )
        
        # 發送訊息並附加刪除按鈕
        await interaction.response.send_message(result, view=delete_view)

async def setup(bot):
    await bot.add_cog(YourCog(bot))
```

## 🔧 實現方式 2：右鍵菜單（已在 KeywordCog 中實現）

如果你的功能使用訊息監聽器（`on_message`），請參考 `cogs/keyword_cog.py` 的實現。

**關鍵點：**
1. 使用 `message.reply()` 而非 `channel.send()`
2. 在 Cog 初始化時註冊 Context Menu
3. 實現權限檢查邏輯

## 📊 已實現刪除功能的 Cogs

| Cog | 刪除方式 | 狀態 |
|-----|---------|------|
| KeywordCog | Context Menu（右鍵） | ✅ 已實現 |
| CopypastaCog | Button（按鈕） | ✅ 已實現 |
| HelpCog | - | ⬜ 待實現 |
| OsuCog | - | ⬜ 待實現 |
| PPCog | - | ⬜ 待實現 |
| UserCog | - | ⬜ 待實現 |
| BeatmapCog | - | ⬜ 待實現 |
| UtilityCog | - | ⬜ 待實現 |

## 🎨 自定義選項

### 自定義超時時間

```python
# 默認 5 分鐘（300 秒）
delete_view = DeleteMessageView(
    trigger_user_id=interaction.user.id,
    guild=interaction.guild,
    timeout=600.0  # 10 分鐘
)
```

### 只允許觸發者刪除（不允許管理員）

如果你需要更嚴格的權限控制，可以創建自定義視圖：

```python
from utils.delete_view import DeleteMessageView

class StrictDeleteView(DeleteMessageView):
    """只允許觸發者刪除的視圖"""
    
    @discord.ui.button(label="刪除", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction, button):
        # 只檢查是否為觸發者
        if interaction.user.id != self.trigger_user_id:
            await interaction.response.send_message(
                "❌ 只有觸發此指令的用戶才能刪除此訊息！",
                ephemeral=True
            )
            return
        
        # 刪除邏輯（與原始實現相同）
        try:
            await interaction.message.delete()
            await interaction.response.send_message(
                "✅ 已成功刪除訊息！",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "❌ 刪除訊息時發生錯誤。",
                ephemeral=True
            )
```

## ⚠️ 注意事項

### 1. Ephemeral 訊息不需要刪除按鈕

如果你的訊息使用 `ephemeral=True`，不需要添加刪除按鈕：

```python
# 這種訊息只有用戶自己能看到，不需要刪除按鈕
await interaction.response.send_message(
    "這是私密訊息",
    ephemeral=True
)
```

### 2. 機器人權限

機器人需要「管理訊息」權限才能刪除訊息。如果沒有權限，會顯示錯誤訊息。

### 3. 按鈕超時

按鈕在超時後會自動禁用，但訊息不會被刪除。用戶仍然可以手動刪除訊息（如果有權限）。

### 4. 多個按鈕

如果你的訊息已經有其他按鈕，可以將 DeleteMessageView 與其他視圖結合：

```python
class MyView(discord.ui.View):
    def __init__(self, trigger_user_id, guild):
        super().__init__(timeout=300.0)
        self.trigger_user_id = trigger_user_id
        self.guild = guild
        
        # 添加你的自定義按鈕
        self.add_item(MyCustomButton())
        
        # 添加刪除按鈕（從 DeleteMessageView 複製）
        # 或者使用組合模式
```

## 🧪 測試檢查清單

為新添加的刪除功能進行測試：

- [ ] 觸發者可以成功刪除訊息
- [ ] 管理員可以成功刪除訊息
- [ ] 非權限用戶無法刪除（顯示錯誤訊息）
- [ ] 按鈕在超時後禁用
- [ ] 刪除後顯示確認訊息
- [ ] 錯誤處理正常工作
- [ ] 日誌記錄正確

## 📚 相關文件

- `utils/delete_view.py` - 通用刪除視圖實現
- `cogs/copypasta_cog.py` - 按鈕方式示例
- `cogs/keyword_cog.py` - 右鍵菜單方式示例
- `TESTING_DELETE_FEATURE.md` - 測試指南

## 💡 最佳實踐

1. **一致性**：在整個項目中使用相同的刪除方式
2. **用戶體驗**：確保刪除按鈕不會干擾其他功能
3. **權限控制**：始終驗證用戶權限
4. **錯誤處理**：提供清晰的錯誤訊息
5. **日誌記錄**：記錄所有刪除操作以便審計

## 🎯 下一步

1. 為其他 Cogs 添加刪除功能
2. 收集用戶反饋
3. 根據需要調整超時時間
4. 考慮添加批量刪除功能（管理員專用）

---

**更新日期：** 2025-12-07  
**版本：** 1.0.0
