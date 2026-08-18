# astrbot_plugin_xun_sky_tools

光遇（Sky: Children of the Light）查询工具 AstrBot 插件。由 MaiBot 插件 [`xun_sky_tools_plugin`](https://github.com/xc94188/sky_tools_plugin) 迁移而来，已按 [AstrBot 插件模板](https://github.com/Soulter/helloworld) 重写。

> 原插件作者：寻 (xc94188)。本仓库为迁移版本，命令触发方式遵循 AstrBot 约定（默认前缀 `/`）。

## 功能

| 命令 | 别名 | 说明 |
| --- | --- | --- |
| `/skytools` | `help` | 帮助 / 命令总览 |
| `/height` | `身高` | 身高查询（mango / 独角兽 / 应天 多平台） |
| `/task` | `rw` `任务` `每日任务` | 每日任务图片 |
| `/candle` | `dl` `大蜡` `大蜡烛` | 大蜡烛位置图片 |
| `/season_candle` | `scandel` `jl` `季蜡` `季节蜡烛` `季蜡位置` | 季蜡位置图片 |
| `/ancestor` | `fk` `复刻` `先祖` `复刻先祖` | 复刻先祖（图片 + 文字） |
| `/magic` | `mf` `魔法` `每日魔法` | 每日魔法图片 |
| `/calendar` | `rl` `日历` `活动日历` | 活动日历图片 |
| `/redstone` | `hs` `红石` `红石位置` | 红石位置图片 |
| `/skytest` | `服务器状态` | 服务器状态 |
| `/all` | `每日` `日常` `rc` `mr` | 一键汇总所有已启用功能 |
| `/season_progress` | `季节进度` `当前季节` | 当前季节进度与剩余时间 |
| `/debris_info` | `碎石信息` `碎石` | 今日碎石（黑石/红石）位置 |
| `/debris_calendar` | `碎石日历` | 某月光遇碎石日历（`/碎石日历 8` 或 `/碎石日历 8 2026`） |
| `/grandma` | `老奶奶时间` `老奶奶` `奶奶` | 雨林老奶奶用餐时间 |
| `/sacrifice` | `献祭信息` `献祭` `伊甸` | 献祭（伊甸之眼）信息 |
| `/光翼查询` | `wing_query` `光翼` | 个人光翼收集进度（需绑定/提供ID） |
| `/光翼统计` | `wing_stats` `全图光翼` | 全图光翼统计 |
| `/光遇绑定` / `/光遇切换` / `/光遇删除` / `/光遇ID列表` | — | 光遇ID绑定管理（用于光翼查询） |

> 合并转发（Napcat）相关逻辑在原插件中依赖 MaiBot + QQ(Napcat) 环境，本插件已移除，改为 AstrBot 原生消息发送（图片使用 `Image.fromBase64`，文字使用 `plain_result`）。`/all` 会分条依次发送每条结果。

## 高级能力

- **LLM 自然语言交互**：在配置中填写 `llm_provider_id`（留空则用会话默认 Provider）后，可直接用自然语言提问（如“今天光遇有什么任务？”“服务器炸了吗？”“我有多少光翼？”），由 LLM 自动调用对应查询工具。
- **光翼查询与ID绑定**：先 `/光遇绑定 <ID>` 绑定光遇短ID，之后 `/光翼查询` 直接查当前ID进度；支持多ID切换/删除/列表。需配置 `ovoav_key`（独角兽密钥，光翼查询与身高/任务/蜡烛等共用）。
- **定时推送**（默认关闭，需配置 `push_groups` 并开启对应开关）：
  - 每日任务图片（按 `daily_task_push_time`）
  - 老奶奶用餐提醒（用餐前5分钟）
  - 献祭刷新提醒（每周六 00:00）
  - 每日碎石提醒（与每日任务同时）

## 安装

1. 在 AstrBot 后台「插件市场 / 插件」中，将本仓库添加为 Git 插件源并安装；或手动将本仓库克隆到 AstrBot 的 `plugins` 目录：
   ```bash
   cd <AstrBot>/plugins
   git clone https://github.com/3812142974/astrbot_plugin_xun_sky_tools.git
   ```
2. 重启 AstrBot（或重载插件）。
3. 在插件配置页填入各 API 的 `url` 与 `key`（默认值中的 `你的xxx密钥` 占位符需替换为真实密钥，否则对应命令会提示“未配置 API 密钥”）。

依赖 `aiohttp`（AstrBot 通常已自带，若缺失可在插件目录执行 `pip install -r requirements.txt`）。

## 配置说明

配置项见 `_conf_schema.json`，主要包括：
- 各功能 API 的 `url` / `key` / `timeout`（key 留空或仍为占位符时命令会拒绝执行）。
- 身高查询：`height_default_platform`（默认 `mango`）、`height_enable_mango/ovoav/yingtian` 平台开关，以及三个平台的 `url`/`key`/`timeout`。
- 各功能的启用开关：`enable_*_query`（如 `enable_height_query`、`enable_all_query` 等），关闭后在 `/skytools` 总览中隐藏对应命令。
- 身高查询首查通常需提供好友码：`/height <游戏长ID> [好友码]`。

## 与原插件的差异

- 命令前缀由 MaiBot 的 `#` 改为 AstrBot 默认的 `/`（可在 AstrBot 全局设置中修改）。
- 移除了 MaiBot 专属的 Napcat 合并转发与配置热重载监控，改用 AstrBot 原生消息 API。
- 配置从 `config.toml` 改为 AstrBot 的 `_conf_schema.json` + 后台配置页。
- API 密钥默认以占位符提供，请自行填写，不要提交真实密钥。
