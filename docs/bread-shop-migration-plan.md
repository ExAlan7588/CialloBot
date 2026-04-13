# Bread-Shop 移植與底層翻新規劃

> 本文件是 2026-04-12 依據 `Bread-Shop` 與目前 `CialloBot` 源碼做的調查與設計整理。
> 目前僅完成調查，尚未實作，也尚未驗證任何 PostgreSQL / Discord 互動流程。

## 1. 目標

把 `https://gitee.com/Tloml-Starry/Bread-Shop` 的玩法移植到本專案的 Discord Bot，並同步完成以下底層翻新：

1. 導入 PostgreSQL 持久化，淘汰 JSON 檔型玩家資料。
2. 導入統一錯誤處理，區分業務錯誤與系統錯誤。
3. 導入統一 `BaseView`，收斂按鈕/選單互動行為。
4. 玩法與 UI 要符合 Discord slash command / View 的使用方式，不直接照搬 Yunzai 的文字觸發模型。

## 2. 來源專案事實

### 2.1 Bread-Shop 是什麼

- `README.md:1-25` 明確寫出這是給 `Yunzai-Bot V3` 用的插件，不是 Discord 專案。
- 插件入口 `index.js:1-24` 會自動載入 `apps/*.js`。
- 玩家資料與配置都落在插件目錄下，沒有資料庫。

### 2.2 上游資料模型

核心檔案是 `function/function.js:10-75`：

- `getPlayerData()` 直接讀 `data/player/<group_id>/<user_id>.json`
- `storagePlayerData()` 直接覆寫玩家 JSON
- `readConfiguration()` 直接讀 `config.yaml`
- `getGroupPlayerList()` / `getGroupList()` 直接列檔案系統

這代表它的核心模型是：

1. 每個群一個資料夾。
2. 每個玩家一個 JSON。
3. 全局配置一份 YAML。
4. 排行榜靠掃整個資料夾拼出來。

### 2.3 上游玩法清單

幫助頁 `resources/html/help/index.html:11-60` 已經列出完整玩法面：

| 玩法 | 上游觸發 | 作用 |
| --- | --- | --- |
| 買 | `#買面包` | 隨機增加物品 |
| 吃 | `#吃面包` | 隨機消耗物品，累積經驗與等級 |
| 搶 | `#搶面包` | 搶別人或隨機搶群友 |
| 送 | `#送面包` | 送別人或隨機送群友 |
| 賭 | `#賭面包剪刀/石頭/布` | 猜拳，贏/輸/平局 |
| 查看 | `#查看面包` | 查自己或別人的數量與等級 |
| 記錄 | `#面包記錄` | 查操作次數或某類操作最多的人 |
| 排行榜 | `#面包排行榜` | 群內榜 |
| 全局排行榜 | `#面包全局排行榜` | 所有群總榜 |
| 設定暱稱 | `#設置面包店暱稱xxx` | 自訂玩家顯示名 |
| 自訂物品 | `#設置本群自定義物品xxx` | 群專屬物品名 |

### 2.4 上游配置

`config.yaml:2-33` 定義：

- 基礎物品名：`bread_thing`
- 升級門檻：`level_bread_num`
- 五類 cooldown：`cd_buy / cd_eat / cd_rob / cd_give / cd_bet`
- 五類亂數範圍：`min_* / max_*`
- `is_random_robbed`、`is_random_given`

## 3. 玩法細節拆解

### 3.1 買

`apps/buy.js:27-117`

- 每次隨機取得 `min_buy ~ max_buy`
- 有額外事件：
  - 壞掉，變成負數
  - 黃金面包，額外 +20
  - 太窮補助，多送
  - 太多就不賣

### 3.2 吃

`apps/eat.js:27-145`

- 每次隨機消耗 `min_eat ~ max_eat`
- `xp += eatNumber`，滿 `level_bread_num` 升 1 級
- 有額外事件：
  - 直接加等 / 減等
  - 重置所有 cooldown
  - 刷新搶的 cooldown
  - 再吃一次

### 3.3 搶

`apps/rob.js:28-187`

- 可以指定目標，也可以在群內隨機搶
- 隨機事件包含：
  - 被抓罰款
  - 搶劫大成功翻倍
  - 反擊導致倒扣
  - 刷新吃的 cooldown
  - 再搶一次

### 3.4 送

`apps/give.js:28-162`

- 可以指定對象，也可以隨機送
- 隨機事件包含：
  - 系統額外幫送
  - 送雙份
  - 不損失自己的物品

### 3.5 賭

`apps/bet.js:27-146`

- 玩家選 `剪刀 / 石頭 / 布`
- 系統隨機出拳
- 平局歸還，不進損益
- 額外事件包含：
  - 翻倍
  - 警察事件
  - 再來一把

### 3.6 查詢與展示

- `apps/viewBread.js:23-80`：查數量、等級、距離下次升級還差多少。
- `apps/breadRecord.js:24-134`：查自己/別人操作次數，或統計群內某操作最多者。
- `apps/breadRankingList.js:71-194`：排行榜先排序，再用 puppeteer 輸出成圖片。

## 4. 上游不要照抄的問題

### 4.1 明顯邏輯 bug

1. `apps/buy.js:90-97`
   `if (RANDOM_NUMBER < 0.025)` 先成立後，`else if (RANDOM_NUMBER < 0.01)` 永遠不會進。
   黃金面包事件目前是死分支。

2. `apps/eat.js:116-120`
   文案說「下次吃多等 30 分鐘」，但實際改的是 `max_eat`，不是 `cd_eat`。

3. `apps/bet.js:119-127`
   「我出三隻手」分支只改文案，沒有完整同步實際結算語義。

4. `apps/viewBread.js:70-75`
   查別人資料前的存在性檢查寫成 `isPlayerExist(ID[0], ID[1])`，檢查的是自己不是目標。

5. `apps/breadRecord.js:79-84`
   看別人記錄時有同樣問題，先檢查了自己。

### 4.2 資料一致性風險

1. `apps/rob.js:169-183`
   反擊與罰款事件下，搶劫方可能被扣到負數，沒有最低餘額保護。

2. `apps/rob.js:108-138`
   隨機搶是掃整個群目錄逐個找可搶對象，之後若搬到資料庫，不能再用這種 O(n) 掃描硬寫在 hot path。

3. `apps/breadRankingList.js:147-194`
   全局榜會把不同群的同一個人當不同列，也沒有處理「不同群自訂物品名不同」的語義衝突。

## 5. 目前 CialloBot 現況

### 5.1 Bot 啟動與指令模型

`bot.py:22-164`

- `OsuBot` 只負責：
  - 初始化 osu API
  - 掃 `cogs/*.py`
  - `tree.sync()`
- 目前 bot 已開 `message_content`，但主要互動已偏向 slash command。

### 5.2 現有持久化很薄

`utils/user_data_manager.py:10-59`

- 目前只有 `private/user_bindings.json`
- 仍是 file-based JSON
- 沒有 repository / service / transaction / migration 概念

### 5.3 現有 View 尚未統一

- `utils/delete_view.py:17-130` 有自己的權限判斷與 timeout 寫法
- `cogs/osu_cog.py:211-279`、`cogs/pp_cog.py:66-170` 也各自維護 View
- repo 內目前沒有：
  - `BusinessError`
  - `DatabaseOperationError`
  - `handle_interaction_error`
  - `absolute_edit`
  - `absolute_send`
  - `asyncpg.create_pool`

這表示如果直接塞 Bread-Shop 功能，錯誤處理與互動會更散。

## 6. 可參考的 DICKPK V2 寫法

### 6.1 BaseView

`D:\DICKPK\utils\base_view.py:21-97`

可直接借鑑的點：

1. `interaction_check()` 統一做權限/作者檢查
2. `on_error()` 統一把互動錯誤導向 `handle_interaction_error()`
3. `absolute_send()` / `absolute_edit()` 處理 response/followup 差異
4. `disable_items()` / `enable_items()` 統一控管元件狀態

### 6.2 例外階層

`D:\DICKPK\utils\exceptions.py:6-137`

建議至少導入這一層概念：

- `BusinessError`
- `DatabaseOperationError`
- `OnCooldownError`
- `InsufficientBalanceError`
- 領域型錯誤，例如 `InvalidQuantityError`

### 6.3 統一互動錯誤處理

`D:\DICKPK\utils\error_handler.py:117-257`

重點：

1. `BusinessError` 對使用者顯示可理解訊息
2. `DatabaseOperationError` 對前台顯示泛化失敗文案，但後台保留真實例外
3. 未識別錯誤會 `capture_exception()`
4. 統一處理 `interaction.response.is_done()` 的 followup 差異

### 6.4 PostgreSQL 連線池

`D:\DICKPK\database\postgresql\async_manager.py:24-169`

可借鑑：

1. 啟動時建立 `asyncpg.create_pool()`
2. `json / jsonb / uuid` codec 初始化
3. `get_pool()` fail-fast，未初始化就直接報錯
4. 關閉時集中釋放資源

另外 DB URL 組裝策略可看 `D:\DICKPK\config\settings.py:227-246`。

## 7. Discord 版呈現方案

### 7.1 指令面建議

不要沿用純文字觸發，建議改成 slash group：

```text
/bread buy
/bread eat
/bread rob
/bread give
/bread bet
/bread profile
/bread record
/bread rank
/bread config nickname
/bread config item-name
```

### 7.2 每個玩法的 Discord 呈現

| 指令 | 輸入 | 建議輸出 |
| --- | --- | --- |
| `/bread buy` | 無或數量擴充 | 公開 embed |
| `/bread eat` | 無或數量擴充 | 公開 embed |
| `/bread rob` | `member` | 公開 embed，必要時可加確認按鈕 |
| `/bread give` | `member` | 公開 embed |
| `/bread bet` | `gesture` | 公開 embed，可用按鈕或 choice |
| `/bread profile` | `member?` | 預設 ephemeral embed |
| `/bread record` | `member?`、`action?` | 預設 ephemeral + 可翻頁 |
| `/bread rank` | `scope=group/global` | Embed 分頁；第二階段可做圖片榜 |
| `/bread config nickname` | 字串 | ephemeral |
| `/bread config item-name` | 字串 | 僅管理員，ephemeral |

### 7.3 第一階段不要硬做的東西

1. 不要一開始就複製 puppeteer 圖片榜。
2. 不要先做過多按鈕 mini-game。
3. 不要延續 Yunzai 的 regex 文字解析。

第一階段先做到「可玩、資料正確、錯誤統一」比較重要。

## 8. PostgreSQL 設計建議

### 8.1 最小 schema

建議先做三張表：

#### `bread_guild_configs`

- `guild_id bigint primary key`
- `item_name text not null`
- `allow_random_rob boolean not null`
- `allow_random_give boolean not null`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

#### `bread_players`

- `guild_id bigint not null`
- `user_id bigint not null`
- `nickname text not null`
- `level integer not null`
- `xp integer not null`
- `item_count integer not null`
- `buy_cooldown_until timestamptz not null`
- `eat_cooldown_until timestamptz not null`
- `rob_cooldown_until timestamptz not null`
- `give_cooldown_until timestamptz not null`
- `bet_cooldown_until timestamptz not null`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`
- primary key: `(guild_id, user_id)`

#### `bread_action_logs`

- `id bigserial primary key`
- `guild_id bigint not null`
- `actor_user_id bigint not null`
- `target_user_id bigint null`
- `action_type text not null`
- `delta integer not null`
- `result_text text not null`
- `extra_data jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null`

### 8.2 為什麼先只做三張

1. 冷卻欄位直接掛在 `bread_players` 就夠用。
2. 記錄與統計先靠 `bread_action_logs` 撐住。
3. 這樣可以先上線，再看要不要拆報表表或 materialized view。

## 9. 建議的程式結構

依照目前 repo 體量，先不要做太厚重的框架；建議最小結構：

```text
config/
  settings.py
database/
  postgresql/
    async_manager.py
    migrations/
bread/
  repositories/
  services/
  views/
  models/
  constants.py
utils/
  exceptions.py
  error_handler.py
  base_view.py
  base_modal.py
  response_embeds.py
cogs/
  bread_cog.py
```

如果想更保守，也可以先不拆 `bread/models/`，但 `repositories / services / views` 至少要分。

## 10. 實作順序

### Phase 1：底座先行

- [x] 補 `.env` / `settings` / PostgreSQL DSN 解析
- [x] 補 `database/postgresql/async_manager.py`
- [x] Bot 啟動時初始化 pool，關閉時釋放
- [x] 補 `utils/exceptions.py`
- [x] 補 `utils/error_handler.py`
- [x] 補 `utils/base_view.py` / `utils/base_modal.py`

### Phase 2：先做查詢面

- [x] `/bread profile`
- [x] `/bread record`
- [x] `/bread rank`

原因：這三條最適合先驗證 DB、查詢與 View 骨架。

### Phase 3：再做動作面

- [x] `/bread buy`
- [x] `/bread eat`
- [x] `/bread give`
- [x] `/bread rob`
- [x] `/bread bet`

### Phase 4：管理面

- [x] `/bread nickname`
- [x] `/bread itemname`
- [x] 管理員權限檢查

### Phase 5：第二階段視覺強化

- [ ] 圖片排行榜
- [ ] richer embeds
- [ ] 特殊事件視覺化

## 11. 測試清單

### 11.1 單元測試

- [ ] cooldown 正常與未到期分支
- [ ] 餘額不足
- [ ] 搶/送指定對象不存在
- [ ] 搶/送隨機對象選擇
- [ ] 等級升級
- [ ] 排行榜排序
- [ ] `BusinessError` 前台訊息
- [ ] `DatabaseOperationError` 前台訊息與後台記錄
- [x] 猜拳勝負純邏輯
- [x] 吃麵包事件分支中的代表案例
- [x] help surface 會展開 group 指令
- [x] 記錄頁 action label / preview 純邏輯

### 11.2 互動測試

- [ ] slash command 能正常回應
- [ ] `BaseView` timeout 後按鈕狀態正確
- [ ] `absolute_edit()` 在 response done / 未 done 都正確
- [ ] ephemeral / public 訊息邊界正確

## 12. 開工建議

這個工程的正確順序不是先寫玩法，而是：

1. 先補 PostgreSQL、錯誤處理、BaseView。
2. 先做 `/bread profile` 當 smoke path。
3. 確認整條資料與互動鏈打通後，再做 `buy/eat/give/rob/bet`。

如果一開始就直接寫玩法，後面一定還要回頭拆一次底層。

## 13. 下一步

目前已完成到：

1. `settings + async_manager + exceptions + error_handler + base_view`
2. `/bread profile / rank / record`
3. `/bread buy / eat / give / rob / bet`
4. `/bread nickname / itemname`
5. `/help` 已能展開 Bread group 子指令
6. `unittest` 已補純邏輯與 help 展開測試

下一輪建議直接做：

1. 真實 PostgreSQL smoke test
2. Discord live slash command smoke test
3. 補更多單元測試與必要索引/查詢優化
4. 收斂 help / 文檔 / 互動細節
