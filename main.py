"""
光遇工具 AstrBot 插件
由 MaiBot 插件 xun_sky_tools_plugin 迁移而来
支持命令:
  /skytools (/help)        帮助
  /height (/身高)          身高查询 (mango / 独角兽 / 应天)
  /task (/rw /任务 /每日任务)    每日任务图片
  /candle (/dl /大蜡 /大蜡烛)    大蜡烛位置
  /season_candle (/scandel /jl /季蜡 /季节蜡烛 /季蜡位置)  季蜡位置
  /ancestor (/fk /复刻 /先祖 /复刻先祖)  复刻先祖
  /magic (/mf /魔法 /每日魔法)        每日魔法
  /calendar (/rl /日历 /活动日历)     活动日历
  /redstone (/hs /红石 /红石位置)     红石位置
  /skytest (/服务器状态)     服务器状态
  /all (/每日 /日常 /rc /mr)         一键汇总
  /season_progress (/季节进度)        当前季节进度
  /debris_info (/碎石信息 /碎石)      今日碎石位置
  /debris_calendar (/碎石日历)       某月碎石日历
  /grandma (/老奶奶时间)       雨林老奶奶用餐时间
  /sacrifice (/献祭信息 /献祭)        献祭（伊甸之眼）信息
  /光翼查询 (/wing_query)     个人光翼收集进度（需绑定/提供ID）
  /光翼统计 (/wing_stats)     全图光翼统计
  /光遇绑定 /光遇切换 /光遇删除 /光遇ID列表   光遇ID绑定管理
另支持 LLM 自然语言触发与定时推送（需在配置中开启）。
"""
import asyncio
import base64
import json
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import aiohttp

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter, MessageChain
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.core.config import AstrBotConfig
import astrbot.api.message_components as Comp

import random
import calendar as _calendar
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

# ============================================================================
# 新增功能常量（季节进度 / 碎石 / 献祭 / 老奶奶 / 光翼）
# ============================================================================


RESOURCES_BASE_DEFAULT = "https://ghfast.top/https://raw.githubusercontent.com/A-Kevin1217/resources/master/resources"
WING_API_DEFAULT = "https://s.166.net/config/ds_yy_02/ma75_wing_wings.json"
WING_QUERY_API_DEFAULT = "https://ovoav.com/api/sky/gycx/gka"

SACRIFICE_INFO_TEXT = """🔥 献祭信息

📅 刷新时间: 每周六 00:00
📍 位置: 暴风眼（伊甸之眼）

📖 献祭是光遇中获取升华蜡烛的主要途径

🎁 献祭奖励:
   • 升华蜡烛（用于解锁先祖节点）
   • 每周最多约15根升华蜡烛

💡 小贴士:
   • 进入暴风眼需要20+光翼
   • 献祭时尽量点亮更多石像
   • 可以组队献祭互相照亮
   • 注意躲避冥龙，被照到会损失光翼"""

GRANDMA_SCHEDULE_TEXT = """🍲 老奶奶用餐信息

📍 位置: 雨林隐藏图（秘密花园）
📖 雨林老奶奶会在用餐时间提供烛火

⏰ 用餐时间:
   • 08:00 - 08:30
   • 10:00 - 10:30
   • 12:00 - 12:30
   • 16:00 - 16:30
   • 18:00 - 18:30
   • 20:00 - 20:30

💡 小贴士:
   • 带上火盆或火把可以自动收集烛火
   • 可以挂机收集
   • 每次约可获得1000+烛火（约10根蜡烛）"""

# 老奶奶提醒时间（用餐前5分钟）
GRANDMA_REMIND_TIMES = [(7, 55), (9, 55), (11, 55), (15, 55), (17, 55), (19, 55)]

# 碎石地图轮换规律（基于日期）
_DEBRIS_MAPS = ["暮土", "禁阁", "云野", "雨林", "霞谷"]
_DEBRIS_LOCATIONS = {
    "云野": {1: "蝴蝶平原", 2: "仙乡", 4: "云顶浮石", 5: "幽光山洞", 6: "圣岛"},
    "雨林": {1: "荧光森林", 2: "密林遗迹", 4: "大树屋", 5: "雨林神殿", 6: "秘密花园"},
    "霞谷": {1: "滑冰场", 2: "滑冰场", 4: "圆梦村", 5: "圆梦村", 6: "雪隐峰"},
    "暮土": {1: "边陲荒漠", 2: "远古战场", 4: "黑水港湾", 5: "巨兽荒原", 6: "失落方舟"},
    "禁阁": {1: "星光沙漠", 2: "星光沙漠", 4: "星光沙漠·一隅", 5: "星光沙漠·一隅", 6: "星光沙漠·一隅"},
}
_DEBRIS_TIMES = ["10:08", "14:08", "22:08"]

# ============================================================================
# 通用验证函数
# ============================================================================


def validate_game_id(game_id: str) -> bool:
    """验证游戏ID格式 (UUID)"""
    if not game_id:
        return False
    uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    return re.match(uuid_pattern, game_id.lower()) is not None


def validate_friend_code(friend_code: str) -> bool:
    """验证好友码格式 (XXXX-XXXX-XXXX)"""
    if not friend_code:
        return False
    pattern = r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$"
    return re.match(pattern, friend_code.upper()) is not None


# ============================================================================
# 身高查询平台处理器
# ============================================================================


class BasePlatformHandler(ABC):
    """平台处理器基类"""

    @abstractmethod
    async def query(
        self, url: str, key: str, game_id: str, friend_code: Optional[str], timeout: int
    ) -> Dict[str, Any]:
        pass


def _safe_float(value, default=None):
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


class MangoPlatformHandler(BasePlatformHandler):
    """芒果平台处理器"""

    def __init__(self):
        self.height_types = {
            "very_short": "非常矮",
            "short": "矮",
            "medium": "中等",
            "tall": "高",
            "very_tall": "非常高",
        }

    async def query(self, url, key, game_id, friend_code, timeout):
        params = {"key": key, "id": game_id.lower()}
        if friend_code:
            params["inviteCode"] = friend_code.upper()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=params, timeout=timeout) as resp:
                    return await self._handle_response(resp)
        except Exception as e:
            return self._handle_error(e)

    async def _handle_response(self, response):
        if response.status != 200:
            error_detail = await self._parse_error_response(response)
            return {
                "success": False,
                "message": f"❌ API请求失败: {error_detail}",
                "error": f"HTTP {response.status}: {error_detail}",
            }
        try:
            data = await response.json()
            if "data" not in data or not data["data"]:
                return {
                    "success": False,
                    "message": f"❌ API返回错误: {data.get('message', '未知错误')}",
                    "error": data.get("message", "未知错误"),
                }
            return {"success": True, "message": self._format_data(data["data"])}
        except Exception as e:
            return {"success": False, "message": f"❌ 解析响应失败: {str(e)}", "error": str(e)}

    def _format_data(self, data):
        try:
            s_value = _safe_float(data.get("s"))
            h_value = _safe_float(data.get("h"))
            height_value = _safe_float(data.get("height"), h_value)
            max_height = _safe_float(data.get("max"), 1.0)
            min_height = _safe_float(data.get("min"), 14.0)
            height_type = self._calculate_height_type(height_value, min_height, max_height)
            to_min_diff = (
                max(0, min_height - height_value)
                if height_value is not None and min_height is not None
                else 0
            )
            to_max_diff = (
                max(0, height_value - max_height)
                if height_value is not None and max_height is not None
                else 0
            )
            result = [
                "✨ 芒果平台 - 身高查询结果",
                "━━━━━━━━━━━━━━━━━━━━",
                f"📊 体型值(s值): {s_value:.8f}" if s_value is not None else "📊 体型值(s值): 未知",
                f"📊 身高值(h值): {h_value:.8f}" if h_value is not None else "📊 身高值(h值): 未知",
                f"📈 最高身高: {max_height:.8f}" if max_height is not None else "📈 最高身高: 未知",
                f"📉 最矮身高: {min_height:.8f}" if min_height is not None else "📉 最矮身高: 未知",
                f"✨ 当前身高: {height_value:.8f}" if height_value is not None else "✨ 当前身高: 未知",
                f"🏷️ 身高类型: {height_type}",
                "",
                f"🎯 距离最矮: {to_min_diff:.8f}" if to_min_diff > 0 else "🎯 已达到最矮身高",
                f"🎯 距离最高: {to_max_diff:.8f}" if to_max_diff > 0 else "🎯 已达到最高身高",
                "━━━━━━━━━━━━━━━━━━━━",
            ]
            return "\n".join(result)
        except Exception as e:
            return f"❌ 解析芒果平台数据失败: {str(e)}"

    def _calculate_height_type(self, h_value, min_height, max_height):
        if h_value is None or min_height is None or max_height is None:
            return "未知"
        height_range = min_height - max_height
        if height_range <= 0:
            return self.height_types["medium"]
        position = (h_value - max_height) / height_range
        if position < 0.2:
            return self.height_types["very_tall"]
        elif position < 0.4:
            return self.height_types["tall"]
        elif position < 0.6:
            return self.height_types["medium"]
        elif position < 0.8:
            return self.height_types["short"]
        else:
            return self.height_types["very_short"]

    async def _parse_error_response(self, response):
        try:
            error_data = await response.json()
            if "message" in error_data:
                return error_data["message"]
            return str(error_data)
        except Exception:
            try:
                return await response.text()
            except Exception:
                return f"状态码: {response.status}"

    def _handle_error(self, error):
        if isinstance(error, aiohttp.ClientError):
            return {"success": False, "message": f"❌ 网络请求错误: {str(error)}", "error": str(error)}
        elif isinstance(error, asyncio.TimeoutError):
            return {"success": False, "message": "❌ 请求超时", "error": "请求超时"}
        else:
            return {"success": False, "message": f"❌ 请求错误: {str(error)}", "error": str(error)}


class OvoavPlatformHandler(BasePlatformHandler):
    """独角兽平台处理器"""

    async def query(self, url, key, game_id, friend_code, timeout):
        params = {"key": key}
        if game_id and not validate_game_id(game_id) and validate_friend_code(game_id):
            params["id"] = game_id.upper()
        elif game_id and validate_game_id(game_id):
            params["id"] = game_id.lower()
        elif friend_code and validate_friend_code(friend_code):
            params["id"] = friend_code.upper()
        else:
            return {"success": False, "message": "❌ 请提供有效的游戏长ID或好友码", "error": "缺少有效参数"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=timeout) as response:
                    return await self._handle_response(response)
        except Exception as e:
            return self._handle_error(e)

    async def _handle_response(self, response):
        if response.status != 200:
            error_detail = await self._parse_error_response(response)
            return {
                "success": False,
                "message": f"❌ API请求失败: {error_detail}",
                "error": f"HTTP {response.status}: {error_detail}",
            }
        try:
            response_text = await response.text()
            cleaned = re.sub(r"<[^>]+>", "", response_text)
            cleaned = re.sub(r"[ ]+", " ", cleaned)
            return {"success": True, "message": cleaned.strip()}
        except Exception as e:
            return {"success": False, "message": f"❌ 解析响应失败: {str(e)}", "error": str(e)}

    async def _parse_error_response(self, response):
        try:
            return await response.text()
        except Exception:
            return f"状态码: {response.status}"

    def _handle_error(self, error):
        if isinstance(error, aiohttp.ClientError):
            return {"success": False, "message": f"❌ 网络请求错误: {str(error)}", "error": str(error)}
        elif isinstance(error, asyncio.TimeoutError):
            return {"success": False, "message": "❌ 请求超时", "error": "请求超时"}
        else:
            return {"success": False, "message": f"❌ 请求错误: {str(error)}", "error": str(error)}


class YingtianPlatformHandler(BasePlatformHandler):
    """应天平台处理器"""

    def __init__(self):
        self.height_types = {
            "very_short": "非常矮",
            "short": "矮",
            "medium": "中等",
            "tall": "高",
            "very_tall": "非常高",
        }

    async def query(self, url, key, game_id, friend_code, timeout):
        params = {"key": key}
        if not game_id or not validate_game_id(game_id):
            return {"success": False, "message": "❌ 请提供有效的游戏长ID", "error": "缺少游戏长ID"}
        params["cx"] = game_id.lower()
        if friend_code:
            if not validate_friend_code(friend_code):
                return {"success": False, "message": "❌ 好友码格式错误", "error": "好友码格式错误"}
            params["code"] = friend_code.upper()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=timeout) as response:
                    return await self._handle_response(response)
        except Exception as e:
            return self._handle_error(e)

    async def _handle_response(self, response):
        if response.status != 200:
            error_detail = await self._parse_error_response(response)
            return {
                "success": False,
                "message": f"❌ API请求失败: {error_detail}",
                "error": f"HTTP {response.status}: {error_detail}",
            }
        try:
            response_text = await response.text()
            data = json.loads(response_text)
            if data.get("code") != 200:
                return {
                    "success": False,
                    "message": f"❌ API返回错误: {data.get('msg', '未知错误')}",
                    "error": data.get("msg", "未知错误"),
                }
            return {"success": True, "message": self._format_data(data)}
        except json.JSONDecodeError as e:
            return {"success": False, "message": f"❌ 解析JSON失败: {str(e)}", "error": str(e)}
        except Exception as e:
            return {"success": False, "message": f"❌ 解析响应失败: {str(e)}", "error": str(e)}

    def _format_data(self, data):
        try:
            data_info = data.get("data", {})
            score_info = data.get("score", {})
            adorn_info = data.get("adorn", {})
            action_info = data.get("action", {})
            scale = _safe_float(data_info.get("scale"))
            height = _safe_float(data_info.get("height"))
            current_height = _safe_float(data_info.get("currentHeight"))
            max_height = _safe_float(data_info.get("maxHeight"))
            min_height = _safe_float(data_info.get("minHeight"))
            height_desc = data_info.get("heightDesc", "未知")
            if isinstance(height_desc, str) and height_desc.startswith("当前身高："):
                height_desc = height_desc.replace("当前身高：", "").strip()
            result = [
                "✨ 应天平台 - 身高查询结果",
                "━━━━━━━━━━━━━━━━━━━━",
                f"📊 体型值(s值): {scale}" if scale is not None else "📊 体型值(s值): 未知",
                f"📊 身高值(h值): {height}" if height is not None else "📊 身高值(h值): 未知",
                f"✨ 当前身高: {current_height}" if current_height is not None else "✨ 当前身高: 未知",
                f"📈 最高身高: {max_height}" if max_height is not None else "📈 最高身高: 未知",
                f"📉 最矮身高: {min_height}" if min_height is not None else "📉 最矮身高: 未知",
                f"🏷️ 身高描述: {height_desc}",
                "",
                "📊 评分信息:",
                f"  • 体型值评分: {score_info.get('scaleScore', '未知')}分",
                f"  • 身高值评分: {score_info.get('heightScore', '未知')}分",
                f"  • 当前身高评分: {score_info.get('currentHeightScore', '未知')}分",
                f"  • 最高身高评分: {score_info.get('maxHeightScore', '未知')}分",
                f"  • 最矮身高评分: {score_info.get('minHeightScore', '未知')}分",
                "",
                "👗 装扮信息:",
                f"  • 斗篷: {adorn_info.get('cloak', '未知')}",
                f"  • 发型: {adorn_info.get('hair', '未知')}",
                f"  • 面具: {adorn_info.get('mask', '未知')}",
                f"  • 裤子: {adorn_info.get('pants', '未知')}",
                f"  • 道具: {adorn_info.get('prop', '未知')}",
                f"  • 头饰: {adorn_info.get('horn', '未知')}",
                f"  • 项链: {adorn_info.get('neck', '未知')}",
                "",
                "🎭 动作信息:",
                f"  • 站姿: {action_info.get('attitude', '未知')}",
                f"  • 叫声: {action_info.get('voice', '未知')}",
                "━━━━━━━━━━━━━━━━━━━━",
            ]
            return "\n".join([line for line in result if line.strip()])
        except Exception as e:
            return f"❌ 解析应天平台数据失败: {str(e)}"

    async def _parse_error_response(self, response):
        try:
            error_data = await response.json()
            return error_data.get("msg", str(error_data))
        except Exception:
            try:
                return await response.text()
            except Exception:
                return f"状态码: {response.status}"

    def _handle_error(self, error):
        if isinstance(error, aiohttp.ClientError):
            return {"success": False, "message": f"❌ 网络请求错误: {str(error)}", "error": str(error)}
        elif isinstance(error, asyncio.TimeoutError):
            return {"success": False, "message": "❌ 请求超时", "error": "请求超时"}
        else:
            return {"success": False, "message": f"❌ 请求错误: {str(error)}", "error": str(error)}


class PlatformRegistry:
    """平台注册表（单例）"""

    _instance = None
    _handlers = {}
    _aliases = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._handlers = {}
            cls._instance._aliases = {}
        return cls._instance

    def register(self, name, handler_class, aliases=None):
        self._handlers[name] = handler_class
        self._aliases[name] = name
        if aliases:
            for alias in aliases:
                self._aliases[alias] = name

    def get_handler(self, name_or_alias):
        main_name = self._aliases.get(name_or_alias)
        if main_name:
            return self._handlers.get(main_name)
        return None

    def get_all_platforms(self):
        return list(self._handlers.keys())

    def get_platform_info(self):
        info = {}
        for main_name in self._handlers:
            aliases = [a for a, m in self._aliases.items() if m == main_name and a != main_name]
            info[main_name] = aliases
        return info


registry = PlatformRegistry()
registry.register("mango", MangoPlatformHandler, ["mg", "芒果"])
registry.register("ovoav", OvoavPlatformHandler, ["独角兽", "djs"])
registry.register("yingtian", YingtianPlatformHandler, ["应天", "yt"])


# ============================================================================
# 图片 / 文本类 API 抓取辅助
# ============================================================================


async def _fetch_image_base64(url: str, key: str, timeout: int):
    """调用图片类 API，返回 (base64_str 或 None, 错误信息 或 None)"""
    params = {"key": key, "time": str(int(time.time()))}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=timeout) as resp:
                if resp.status != 200:
                    error_detail = await _parse_error(resp)
                    return None, f"❌ API请求失败: {error_detail}"
                image_data = await resp.read()
                if not image_data:
                    return None, "❌ 图片数据为空"
                if len(image_data) < 1024:
                    return None, "❌ 图片数据过小"
                return base64.b64encode(image_data).decode("utf-8"), None
    except aiohttp.ClientError as e:
        return None, f"❌ 网络错误: {str(e)}"
    except asyncio.TimeoutError:
        return None, "❌ 请求超时"
    except Exception as e:
        return None, f"❌ 请求错误: {str(e)}"


async def _parse_error(response):
    try:
        error_data = await response.json()
        if "message" in error_data:
            return error_data["message"]
        return str(error_data)
    except Exception:
        try:
            return await response.text()
        except Exception:
            return f"状态码: {response.status}"


async def _fetch_ancestor(url: str, key: str, timeout: int):
    """复刻先祖：返回 (image_b64, text_info, error)"""
    params = {"key": key, "time": str(int(time.time()))}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=timeout) as resp:
                if resp.status != 200:
                    return None, None, f"❌ API请求失败: {await _parse_error(resp)}"
                data = await resp.json()
                if data.get("code") != 200:
                    return None, None, f"❌ API返回错误: {data.get('msg', '未知错误')}"
                image_b64 = await _download_first_image(data)
                text_info = _build_ancestor_text(data)
                return image_b64, text_info, None
    except Exception as e:
        return None, None, f"❌ 请求错误: {str(e)}"


async def _download_first_image(data):
    try:
        image_urls = data.get("data", {}).get("image", [])
        if not image_urls:
            return None
        image_url = image_urls[0]
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status == 200:
                    image_data = await resp.read()
                    if image_data:
                        return base64.b64encode(image_data).decode("utf-8")
        return None
    except Exception:
        return None


def _build_ancestor_text(data):
    try:
        data_info = data.get("data", {})
        duantext = data_info.get("duantext", "")
        event_start = data_info.get("event_start", "")
        event_end = data_info.get("event_end", "")
        screen_name = data_info.get("screen_name", "")
        clean_text = (
            duantext.replace("#Sky光遇#", "")
            .replace("#光遇旅行先祖#", "")
            .replace("#sky光遇[超话]#", "")
            .strip()
        )
        clean_text = re.sub(r"\n+", "\n", clean_text)
        lines = [
            "✨ 本周复刻先祖信息",
            "━━━━━━━━━━━━━━━━",
            clean_text,
            "",
            f"📅 开始时间: {event_start}",
            f"📅 结束时间: {event_end}",
            f"📱 信息来源: {screen_name}",
            "━━━━━━━━━━━━━━━━",
        ]
        return "\n".join([line for line in lines if line.strip()])
    except Exception:
        return "✨ 本周复刻先祖信息已更新"


async def _fetch_skytest(url: str, key: str, timeout: int):
    """服务器状态：返回 (文本, 错误)"""
    params = {"key": key, "time": str(int(time.time()))}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=timeout) as resp:
                if resp.status != 200:
                    return None, f"❌ API请求失败: {await _parse_error(resp)}"
                data = await resp.json()
                if "msg" not in data:
                    return None, "❌ API返回数据格式错误"
                return (
                    f"🔍 服务器状态查询结果：\n━━━━━━━━━━━━━━━━\n{data['msg']}\n━━━━━━━━━━━━━━━━",
                    None,
                )
    except aiohttp.ClientError as e:
        return None, f"❌ 网络错误: {str(e)}"
    except asyncio.TimeoutError:
        return None, "❌ 请求超时"
    except Exception as e:
        return None, f"❌ 请求错误: {str(e)}"


# ============================================================================
# 插件主体
# ============================================================================


@register("astrbot_plugin_xun_sky_tools", "寻(xc94188)", "光遇(Sky)查询工具：身高/任务/大蜡烛/季蜡/复刻先祖/魔法/日历/红石/服务器状态/季节进度/碎石/老奶奶/献祭/光翼，及一键汇总、LLM自然语言、定时推送", "1.1.0")
class SkyToolsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config or {}

        # 新增功能配置
        self.resources_base = self._cfg("resources_base", RESOURCES_BASE_DEFAULT)
        self.wing_query_url = self._cfg("wing_query_url", WING_QUERY_API_DEFAULT)
        # 平台级密钥：同一平台共用一把 key
        self.mango_key = self._cfg("mango_key", "")
        self.ovoav_key = self._cfg("ovoav_key", "")
        self.yingtian_key = self._cfg("yingtian_key", "")
        self.wing_query_key = self.ovoav_key  # 光翼查询复用独角兽(ovoav) key
        self.wing_stats_url = self._cfg("wing_stats_url", WING_API_DEFAULT)

        # 定时推送配置
        self.push_platform = self._cfg("push_platform", "aiocqhttp")
        self.push_groups = self._cfg("push_groups", []) or []
        self.enable_daily_task_push = self._cfg("enable_daily_task_push", False)
        self.daily_task_push_time = self._cfg("daily_task_push_time", "08:00")
        self.enable_grandma_reminder = self._cfg("enable_grandma_reminder", False)
        self.enable_sacrifice_reminder = self._cfg("enable_sacrifice_reminder", False)
        self.enable_debris_reminder = self._cfg("enable_debris_reminder", False)
        self.llm_provider_id = self._cfg("llm_provider_id", "")

        # 光翼绑定数据目录
        try:
            plugin_data_dir = StarTools.get_data_dir()
            self.bindings_dir = plugin_data_dir / "sky_bindings"
            self.bindings_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.bindings_dir = None
        self._file_lock = asyncio.Lock()
        self._user_locks: Dict[str, asyncio.Lock] = {}

        # 共享会话 & 调度状态
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._last_push_exec: Dict[str, str] = {}

        # 简易缓存（季节进度/复刻先祖/光翼统计）
        self._cache: Dict[str, Dict] = {}
        self._cache_time: Dict[str, float] = {}
        self._cache_ttl = self._cfg("cache_duration", 30) * 60

    # ------------------------------------------------------------------
    # 配置读取辅助
    # ------------------------------------------------------------------
    def _cfg(self, key, default=None):
        try:
            return self.config.get(key, default)
        except Exception:
            return default

    @staticmethod
    def _split_args(event: AstrMessageEvent) -> List[str]:
        """从消息文本中提取命令之后的参数列表"""
        text = getattr(event, "message_str", "") or ""
        text = text.strip()
        text = re.sub(r"^[\s/#]+", "", text)
        parts = text.split()
        if not parts:
            return []
        return parts[1:]

    # ------------------------------------------------------------------
    # 帮助命令
    # ------------------------------------------------------------------
    @filter.command("skytools", "help")
    async def help_cmd(self, event: AstrMessageEvent):
        """查看光遇工具插件所有功能"""
        args = self._split_args(event)
        cmd_name = args[0].lower() if args else ""
        yield event.plain_result(await self._generate_help(cmd_name) if cmd_name else await self._generate_overview())

    async def _generate_overview(self) -> str:
        enable_map = {
            "height": "enable_height_query",
            "task": "enable_task_query",
            "candle": "enable_candle_query",
            "season_candle": "enable_season_candle_query",
            "ancestor": "enable_ancestor_query",
            "magic": "enable_magic_query",
            "calendar": "enable_calendar_query",
            "redstone": "enable_redstone_query",
            "skytest": "enable_skytest_query",
            "all": "enable_all_query",
            "season_progress": "enable_season_progress_query",
            "debris_info": "enable_debris_query",
            "debris_calendar": "enable_debris_query",
            "grandma": "enable_grandma_query",
            "sacrifice": "enable_sacrifice_query",
            "wing_query": "enable_wing_query",
            "wing_stats": "enable_wing_query",
            "bind": "enable_wing_query",
        }
        alias_map = {
            "height": ["身高"],
            "task": ["rw", "任务", "每日任务"],
            "candle": ["dl", "大蜡", "大蜡烛"],
            "season_candle": ["scandel", "jl", "季蜡", "季节蜡烛", "季蜡位置"],
            "ancestor": ["fk", "复刻", "先祖", "复刻先祖"],
            "magic": ["mf", "魔法", "每日魔法"],
            "calendar": ["rl", "日历", "活动日历"],
            "redstone": ["hs", "红石", "红石位置"],
            "skytest": ["服务器状态"],
            "all": ["每日", "日常", "rc", "mr"],
            "season_progress": ["季节进度", "当前季节"],
            "debris_info": ["碎石信息", "碎石"],
            "debris_calendar": ["碎石日历"],
            "grandma": ["老奶奶时间", "老奶奶", "奶奶"],
            "sacrifice": ["献祭信息", "献祭", "伊甸"],
            "wing_query": ["wing_query", "光翼"],
            "wing_stats": ["wing_stats", "全图光翼"],
            "bind": ["光遇绑定", "光遇切换", "光遇删除", "光遇ID列表"],
        }
        desc_map = {
            "height": "查询光遇国服玩家身高数据",
            "task": "获取光遇每日任务图片",
            "candle": "获取光遇大蜡烛位置图片",
            "season_candle": "获取光遇每日季蜡位置图片",
            "ancestor": "获取光遇复刻先祖位置图片",
            "magic": "获取光遇每日魔法图片",
            "calendar": "获取光遇日历图片",
            "redstone": "获取光遇红石位置图片",
            "skytest": "查询光遇服务器状态",
            "all": "一键获取所有光遇日常信息",
            "season_progress": "查询当前季节进度与剩余时间",
            "debris_info": "查询今日碎石（黑石/红石）位置",
            "debris_calendar": "查询某月光遇碎石日历",
            "grandma": "查询雨林老奶奶用餐时间",
            "sacrifice": "查询献祭（伊甸之眼）信息",
            "wing_query": "查询个人光翼收集进度（需绑定/提供ID）",
            "wing_stats": "查询光遇全图光翼统计",
            "bind": "光遇ID绑定/切换/删除/列表（用于光翼查询）",
        }
        lines = ["✨ 光遇工具插件使用说明 ✨", "", "📋 可用命令:"]
        for name in [
            "all",
            "height",
            "task",
            "candle",
            "season_candle",
            "ancestor",
            "magic",
            "calendar",
            "redstone",
            "skytest",
            "season_progress",
            "debris_info",
            "debris_calendar",
            "grandma",
            "sacrifice",
            "wing_query",
            "wing_stats",
            "bind",
        ]:
            if not self._cfg(enable_map[name], True):
                continue
            aliases = [f"/{a}" for a in alias_map[name]]
            cmd_str = f"• /{name}" + (f" 或 {' 或 '.join(aliases)}" if aliases else "")
            lines.append(cmd_str)
            lines.append(f"   → {desc_map[name]}")
            lines.append("")
        lines.append("💡 提示: 输入 /skytools <命令名> 查看详细用法；部分功能可能已被管理员禁用")
        return "\n".join(lines)

    async def _generate_help(self, cmd_name: str) -> str:
        detail = {
            "height": (
                "📏 身高查询\n━━━━━━━━━━━━━━━━━━━━\n"
                "用法: /height [平台] <游戏长ID> [好友码]\n"
                "平台: mango(mg/芒果) / ovoav(独角兽/djs) / yingtian(应天/yt)，省略则用默认平台\n"
                "游戏长ID格式: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx\n"
                "好友码格式: XXXX-XXXX-XXXX（首次查询建议提供）\n"
                "示例: /height mango xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx\n"
                "      /height ovoav XXXX-XXXX-XXXX"
            ),
            "task": "📋 每日任务\n━━━━━━━━━━━━━━━━━━━━\n用法: /task\n获取今日每日任务图片。",
            "candle": "💎 大蜡烛\n━━━━━━━━━━━━━━━━━━━━\n用法: /candle\n获取今日大蜡烛位置图片。",
            "season_candle": "🕯️ 季蜡\n━━━━━━━━━━━━━━━━━━━━\n用法: /season_candle\n获取今日季节蜡烛位置图片。",
            "ancestor": "🧭 复刻先祖\n━━━━━━━━━━━━━━━━━━━━\n用法: /ancestor\n获取本周复刻先祖位置图片与文字信息。",
            "magic": "🔮 每日魔法\n━━━━━━━━━━━━━━━━━━━━\n用法: /magic\n获取今日每日魔法图片。",
            "calendar": "🗓️ 活动日历\n━━━━━━━━━━━━━━━━━━━━\n用法: /calendar\n获取光遇活动日历图片。",
            "redstone": "🔴 红石\n━━━━━━━━━━━━━━━━━━━━\n用法: /redstone\n获取今日红石位置图片。",
            "skytest": "🔍 服务器状态\n━━━━━━━━━━━━━━━━━━━━\n用法: /skytest\n查询光遇服务器当前状态。",
            "all": "📦 一键汇总\n━━━━━━━━━━━━━━━━━━━━\n用法: /all\n一次性获取所有已启用功能的日常信息。",
            "season_progress": "🌸 季节进度\n━━━━━━━━━━━━━━━━━━━━\n用法: /season_progress\n查看当前季节名称、剩余时间、毕业所需天数。",
            "debris_info": "💎 碎石信息\n━━━━━━━━━━━━━━━━━━━━\n用法: /debris_info\n查看今日碎石（黑石/红石）地图、位置与坠落时间。",
            "debris_calendar": "🗓️ 碎石日历\n━━━━━━━━━━━━━━━━━━━━\n用法: /debris_calendar [月份] [年份]\n示例: /debris_calendar 8  或  /debris_calendar 8 2026",
            "grandma": "🍲 老奶奶时间\n━━━━━━━━━━━━━━━━━━━━\n用法: /grandma\n查看雨林老奶奶用餐时间与挂机烛火信息。",
            "sacrifice": "🔥 献祭信息\n━━━━━━━━━━━━━━━━━━━━\n用法: /sacrifice\n查看献祭（伊甸之眼）刷新时间与奖励说明。",
            "wing_query": "🪽 光翼查询\n━━━━━━━━━━━━━━━━━━━━\n用法: /光翼查询 [ID]\n省略ID则查询当前绑定的光遇ID。需先「光遇绑定 <ID>」或配置 ovoav_key（独角兽密钥）。",
            "wing_stats": "📊 光翼统计\n━━━━━━━━━━━━━━━━━━━━\n用法: /wing_stats\n查看光遇全图光翼数量统计。",
            "bind": "🔗 光遇ID绑定\n━━━━━━━━━━━━━━━━━━━━\n光翼查询用途：\n• /光遇绑定 <ID>   绑定光遇短ID\n• /光遇切换 <序号>  切换当前ID\n• /光遇删除 <序号>  删除绑定\n• /光遇ID列表       查看已绑定ID",
        }
        return detail.get(cmd_name, f"❌ 未找到命令 `{cmd_name}`\n可用命令见 /skytools")

    # ------------------------------------------------------------------
    # 身高查询
    # ------------------------------------------------------------------
    @filter.command("height", "身高")
    async def height_cmd(self, event: AstrMessageEvent):
        """查询光遇国服玩家身高数据"""
        if not self._cfg("enable_height_query", True):
            yield event.plain_result("❌ 身高查询功能未启用")
            return

        args = self._split_args(event)
        platform_input = None
        game_id = None
        friend_code = None
        if args:
            first = args[0].lower()
            if registry.get_handler(first):
                platform_input = first
                rest = args[1:]
            else:
                rest = args
            if rest:
                game_id = rest[0]
                if len(rest) > 1:
                    friend_code = rest[1]

        if not game_id or game_id.lower() == "help":
            yield event.plain_result(await self._height_help())
            return

        enabled = [p for p in registry.get_all_platforms() if self._cfg(f"height_enable_{p}", True)]
        if not enabled:
            yield event.plain_result("❌ 所有身高查询平台都未启用，请联系管理员启用")
            return

        target = self._resolve_platform(platform_input, enabled)
        if not target:
            yield event.plain_result("❌ 平台名称错误或该平台未启用")
            return

        validation = self._validate_parameters(target, game_id, friend_code)
        if not validation["success"]:
            yield event.plain_result(validation["message"])
            return

        cfg = self._get_platform_config(target)
        if not cfg:
            yield event.plain_result(f"❌ 插件未配置 {target} 平台 API 密钥")
            return

        handler_cls = registry.get_handler(target)
        if not handler_cls:
            yield event.plain_result(f"❌ 平台 {target} 处理器未注册")
            return

        result = await handler_cls().query(
            cfg["url"], cfg["key"], validation.get("game_id", game_id),
            validation.get("friend_code", friend_code), cfg["timeout"],
        )
        if result["success"]:
            yield event.plain_result(result["message"])
        else:
            err = (result.get("error") or "").lower()
            if any(kw in err for kw in ["record not found", "未找到", "no record", "不存在"]):
                yield event.plain_result(self._record_not_found_suggestion(target))
            else:
                yield event.plain_result(result.get("message", "❌ 身高查询失败"))

    def _resolve_platform(self, user_input, enabled):
        if not user_input:
            default = self._cfg("height_default_platform", "mango")
            return default if default in enabled else (enabled[0] if enabled else None)
        if registry.get_handler(user_input.lower()):
            for main_name in registry.get_all_platforms():
                if registry.get_handler(main_name) == registry.get_handler(user_input.lower()):
                    return main_name if main_name in enabled else None
        return None

    def _validate_parameters(self, platform, game_id, friend_code):
        result = {"success": True, "game_id": game_id, "friend_code": friend_code}
        if platform == "mango":
            if not game_id or not validate_game_id(game_id):
                return {"success": False, "message": "❌ 游戏长ID格式错误。正确格式应为：xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", "error": "游戏ID格式错误"}
            if friend_code and not validate_friend_code(friend_code):
                return {"success": False, "message": "❌ 好友码格式错误。正确格式应为：XXXX-XXXX-XXXX", "error": "好友码格式错误"}
            return result
        elif platform in ["ovoav", "yingtian"]:
            if game_id and validate_game_id(game_id):
                result["game_id"] = game_id.lower()
            elif game_id and validate_friend_code(game_id):
                result["friend_code"] = game_id.upper()
                result["game_id"] = None
            else:
                return {"success": False, "message": "❌ 需要提供有效的游戏长ID或好友码（格式 XXXX-XXXX-XXXX）", "error": "缺少有效参数"}
            if friend_code and not validate_friend_code(friend_code):
                return {"success": False, "message": "❌ 好友码格式错误。正确格式应为：XXXX-XXXX-XXXX", "error": "好友码格式错误"}
            if friend_code:
                result["friend_code"] = friend_code.upper()
            return result
        return result

    def _get_platform_config(self, platform):
        url = self._cfg(f"height_{platform}_url")
        key = self._cfg(f"{platform}_key")
        if not key or str(key).startswith("你的"):
            return None
        return {"url": url, "key": key, "timeout": self._cfg(f"height_{platform}_timeout", 15)}

    def _record_not_found_suggestion(self, platform):
        lines = [
            f"❌ 在 **{platform}** 平台未找到该玩家的身高记录。",
            "",
            "📌 **首次查询请务必提供好友码**",
            "   格式：`/height <游戏ID> <好友码>`",
            "",
            "🔗 **好友码获取方法**",
            "   游戏设置 → 好友 → 使用编号 → 设置昵称后获取",
            "",
            "💡 **为什么需要好友码？**",
            "   好友码用于将游戏ID与你的查询绑定，首次提供后后续可直接使用游戏ID查询。",
            "",
            "⚠️ **注意**：请勿拉黑测身高好友，否则后续无法查询。",
        ]
        return "\n".join(lines)

    async def _height_help(self) -> str:
        enabled = [p for p in registry.get_all_platforms() if self._cfg(f"height_enable_{p}", True)]
        info = registry.get_platform_info()
        lines = ["📏 身高查询使用说明", "", "使用方法（两种格式）:", f"  1. 使用默认平台(当前默认:{self._cfg('height_default_platform', 'mango')}):", "     /height <游戏长ID> [好友码]", "  2. 指定平台:", "     /height <平台名> <游戏长ID> [好友码]", "", "参数说明:", "• 平台名: 支持以下平台和别名"]
        for main_name in enabled:
            alias_str = ", ".join(info.get(main_name, [])) or "无"
            lines.append(f"  • {main_name} (别名: {alias_str}) - ✅ 启用")
        lines.extend(["• 游戏长ID: UUID格式的游戏ID", "• 好友码: 可选的好友码参数", "", "平台要求:"])
        if "mango" in enabled:
            lines.append("• 芒果平台: 必须提供游戏长ID，好友码可选")
        if "ovoav" in enabled:
            lines.append("• 独角兽平台: 提供游戏长ID或好友码任选其一")
        if "yingtian" in enabled:
            lines.append("• 应天平台: 必须提供游戏长ID，好友码可选")
        lines.extend(["", "获取方式:", "• 长ID: 游戏右上角设置→精灵→询问'长id'", "• 好友码: 游戏右上角设置→好友→使用编号→设置昵称后获取", "", "示例:"])
        if "mango" in enabled:
            lines.extend(["芒果平台:", "/height mango xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", "/height mg xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx XXXX-XXXX-XXXX", ""])
        if "ovoav" in enabled:
            lines.extend(["独角兽平台:", "/height ovoav xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", "/height djs XXXX-XXXX-XXXX", ""])
        if "yingtian" in enabled:
            lines.extend(["应天平台:", "/height yingtian xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", "/height yt xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx XXXX-XXXX-XXXX", ""])
        lines.extend(["注意:", "• 首次查询请提供好友码", "• 请勿拉黑测身高好友，否则后续无法查询"])
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 通用图片类命令
    # ------------------------------------------------------------------
    @filter.command("task", "rw", "任务", "每日任务")
    async def task_cmd(self, event: AstrMessageEvent):
        """获取光遇每日任务图片"""
        async for r in self._image_command(
            event, "task", "enable_task_query", "任务", "🔄 正在获取任务图片..."
        ):
            yield r

    @filter.command("candle", "dl", "大蜡", "大蜡烛")
    async def candle_cmd(self, event: AstrMessageEvent):
        """获取光遇大蜡烛位置图片"""
        async for r in self._image_command(
            event, "candle", "enable_candle_query", "大蜡烛", "🔄 正在获取大蜡烛位置..."
        ):
            yield r

    @filter.command("season_candle", "scandel", "jl", "季蜡", "季节蜡烛", "季蜡位置")
    async def season_candle_cmd(self, event: AstrMessageEvent):
        """获取光遇每日季蜡位置图片"""
        async for r in self._image_command(
            event, "season_candle", "enable_season_candle_query", "季蜡", "🔄 正在获取季蜡位置..."
        ):
            yield r

    @filter.command("magic", "mf", "魔法", "每日魔法")
    async def magic_cmd(self, event: AstrMessageEvent):
        """获取光遇每日魔法图片"""
        async for r in self._image_command(
            event, "magic", "enable_magic_query", "每日魔法", "🔄 正在获取每日魔法..."
        ):
            yield r

    @filter.command("calendar", "rl", "日历", "活动日历")
    async def calendar_cmd(self, event: AstrMessageEvent):
        """获取光遇日历图片"""
        async for r in self._image_command(
            event, "calendar", "enable_calendar_query", "光遇日历", "🔄 正在获取光遇日历..."
        ):
            yield r

    @filter.command("redstone", "hs", "红石", "红石位置")
    async def redstone_cmd(self, event: AstrMessageEvent):
        """获取光遇红石位置图片"""
        async for r in self._image_command(
            event, "redstone", "enable_redstone_query", "红石", "🔄 正在获取红石位置..."
        ):
            yield r

    async def _image_command(self, event, key_prefix, enable_key, label, loading_text):
        if not self._cfg(enable_key, True):
            yield event.plain_result(f"❌ {label}查询功能未启用")
            return
        url = self._cfg(f"{key_prefix}_url")
        key = self.ovoav_key
        timeout = self._cfg(f"{key_prefix}_timeout", 15)
        if not key or str(key).startswith("你的"):
            yield event.plain_result(f"❌ 插件未配置{label}API密钥")
            return
        yield event.plain_result(loading_text)
        b64, err = await _fetch_image_base64(url, key, timeout)
        if b64:
            yield event.chain_result([Image.fromBase64(b64)])
        else:
            yield event.plain_result(err or "❌ 获取失败")

    # ------------------------------------------------------------------
    # 复刻先祖（图片 + 文字）
    # ------------------------------------------------------------------
    @filter.command("ancestor", "fk", "复刻", "先祖", "复刻先祖")
    async def ancestor_cmd(self, event: AstrMessageEvent):
        """获取光遇复刻先祖位置图片"""
        if not self._cfg("enable_ancestor_query", True):
            yield event.plain_result("❌ 复刻先祖查询功能未启用")
            return
        url = self._cfg("ancestor_url")
        key = self.ovoav_key
        timeout = self._cfg("ancestor_timeout", 15)
        if not key or str(key).startswith("你的"):
            yield event.plain_result("❌ 插件未配置复刻先祖API密钥")
            return
        yield event.plain_result("🔄 正在获取复刻先祖信息...")
        image_b64, text_info, err = await _fetch_ancestor(url, key, timeout)
        if err:
            yield event.plain_result(err)
            return
        chain = []
        if image_b64:
            chain.append(Image.fromBase64(image_b64))
        if text_info:
            chain.append(Plain(text_info))
        if chain:
            yield event.chain_result(chain)
        else:
            yield event.plain_result("❌ 未找到复刻先祖信息")

    # ------------------------------------------------------------------
    # 服务器状态（纯文本）
    # ------------------------------------------------------------------
    @filter.command("skytest", "服务器状态")
    async def skytest_cmd(self, event: AstrMessageEvent):
        """查询光遇服务器状态"""
        if not self._cfg("enable_skytest_query", True):
            yield event.plain_result("❌ 服务器状态查询功能未启用")
            return
        url = self._cfg("skytest_url")
        key = self.ovoav_key
        timeout = self._cfg("skytest_timeout", 15)
        if not key or str(key).startswith("你的"):
            yield event.plain_result("❌ 插件未配置服务器状态API密钥")
            return
        text, err = await _fetch_skytest(url, key, timeout)
        if text:
            yield event.plain_result(text)
        else:
            yield event.plain_result(err or "❌ 服务器状态查询失败")

    # ------------------------------------------------------------------
    # 一键汇总
    # ------------------------------------------------------------------
    @filter.command("all", "每日", "日常", "rc", "mr")
    async def all_cmd(self, event: AstrMessageEvent):
        """一键获取所有光遇日常信息"""
        if not self._cfg("enable_all_query", True):
            yield event.plain_result("❌ 一键汇总查询功能未启用")
            return

        execution_order = [
            ("task", "📋", "每日任务"),
            ("season_candle", "🕯️", "季节蜡烛"),
            ("candle", "💎", "大蜡烛"),
            ("redstone", "🔴", "红石"),
            ("ancestor", "🧭", "复刻先祖"),
            ("magic", "🔮", "每日魔法"),
            ("calendar", "🗓️", "活动日历"),
            ("skytest", "🔍", "服务器状态"),
        ]
        enable_key = {
            "task": "enable_task_query",
            "season_candle": "enable_season_candle_query",
            "candle": "enable_candle_query",
            "redstone": "enable_redstone_query",
            "ancestor": "enable_ancestor_query",
            "magic": "enable_magic_query",
            "calendar": "enable_calendar_query",
            "skytest": "enable_skytest_query",
        }

        enabled = [c for c, _, _ in execution_order if self._cfg(enable_key[c], True)]
        if not enabled:
            yield event.plain_result("❌ 所有查询功能均未启用，无法执行一键查询")
            return

        yield event.plain_result("🔄 正在获取所有信息，请稍候...")

        count = 0
        for name, icon, display in execution_order:
            if name not in enabled:
                continue
            try:
                if name == "skytest":
                    key = self.ovoav_key
                    if not key or str(key).startswith("你的"):
                        yield event.plain_result(f"{icon} {display}: ❌ 未配置API密钥")
                        continue
                    text, err = await _fetch_skytest(
                        self._cfg("skytest_url"), key, self._cfg("skytest_timeout", 15)
                    )
                    if text:
                        yield event.plain_result(f"{icon} {display}\n{text}")
                        count += 1
                    else:
                        yield event.plain_result(f"{icon} {display}: ❌ {err}")
                elif name == "ancestor":
                    key = self.ovoav_key
                    if not key or str(key).startswith("你的"):
                        yield event.plain_result(f"{icon} {display}: ❌ 未配置API密钥")
                        continue
                    image_b64, text_info, err = await _fetch_ancestor(
                        self._cfg("ancestor_url"), key, self._cfg("ancestor_timeout", 15)
                    )
                    if err:
                        yield event.plain_result(f"{icon} {display}: ❌ {err}")
                        continue
                    chain = [Plain(f"{icon} {display}")]
                    if image_b64:
                        chain.append(Image.fromBase64(image_b64))
                    if text_info:
                        chain.append(Plain(text_info))
                    yield event.chain_result(chain)
                    count += 1
                else:
                    key = self.ovoav_key
                    if not key or str(key).startswith("你的"):
                        yield event.plain_result(f"{icon} {display}: ❌ 未配置API密钥")
                        continue
                    b64, err = await _fetch_image_base64(
                        self._cfg(f"{name}_url"), key, self._cfg(f"{name}_timeout", 15)
                    )
                    if b64:
                        yield event.chain_result([Plain(f"{icon} {display}"), Image.fromBase64(b64)])
                        count += 1
                    else:
                        yield event.plain_result(f"{icon} {display}: ❌ {err}")
            except Exception as e:
                yield event.plain_result(f"{icon} {display}: ❌ 错误 - {str(e)[:50]}")

        yield event.plain_result(f"✅ 已获取 {count} 条光遇日常信息")

    # ==================================================================
    # 生命周期 & 通用工具（新增功能）
    # ==================================================================
    async def initialize(self):
        """插件加载后自动调用：建立共享会话、按需启动定时推送调度"""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self._cfg("api_timeout", 15))
        )
        self._running = True
        if any(
            [
                self.enable_daily_task_push,
                self.enable_grandma_reminder,
                self.enable_sacrifice_reminder,
                self.enable_debris_reminder,
            ]
        ):
            if self.push_groups:
                self._scheduler_task = asyncio.create_task(self._scheduler_loop())
                logger.info("光遇定时推送调度器已启动")
            else:
                logger.warning("已启用定时推送但 push_groups 为空，调度器未启动")

    async def terminate(self):
        """插件卸载时调用：停止调度、关闭会话"""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("光遇插件已终止")

    def _get_beijing_time(self) -> datetime:
        # 北京时间 = UTC+8，使用时间戳计算，避免依赖系统时区数据库（Windows 无需 tzdata）
        return datetime.fromtimestamp(time.time() + 8 * 3600)

    def _get_cache(self, key: str):
        if key in self._cache and key in self._cache_time:
            if time.time() - self._cache_time[key] < self._cache_ttl:
                return self._cache[key]
        return None

    def _set_cache(self, key: str, data):
        self._cache[key] = data
        self._cache_time[key] = time.time()

    async def _fetch_json(self, url: str) -> Optional[Any]:
        """GET 并解析 JSON（无共享会话时临时建会话）"""
        if self._session is None:
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self._cfg("api_timeout", 15))
                ) as s:
                    async with s.get(url) as resp:
                        if resp.status == 200:
                            return await resp.json()
            except Exception as e:
                logger.error(f"JSON请求失败 {url}: {e}")
                return None
            return None
        try:
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error(f"JSON请求失败 {url}: {e}")
        return None

    def _build_unified_msg_origin(self, group_id: str) -> str:
        if ":" in str(group_id):
            return str(group_id)
        return f"{self.push_platform}:GroupMessage:{group_id}"

    async def _send_push_text(self, text: str):
        if not self.push_groups:
            return
        for gid in self.push_groups:
            try:
                chain = MessageChain()
                chain.chain = [Comp.Plain(text)]
                await self.context.send_message(self._build_unified_msg_origin(gid), chain)
            except Exception as e:
                logger.error(f"推送文本到 {gid} 失败: {e}")

    async def _send_push_image(self, image_b64: str, caption: str = ""):
        if not self.push_groups:
            return
        for gid in self.push_groups:
            try:
                chain = MessageChain()
                parts = []
                if caption:
                    parts.append(Comp.Plain(caption))
                parts.append(Comp.Image.fromBase64(image_b64))
                chain.chain = parts
                await self.context.send_message(self._build_unified_msg_origin(gid), chain)
            except Exception as e:
                logger.error(f"推送图片到 {gid} 失败: {e}")

    # ==================================================================
    # 季节进度 / 碎石 / 老奶奶 / 献祭（纯文本查询）
    # ==================================================================
    async def _season_progress_data(self) -> Optional[Dict]:
        cached = self._get_cache("season_progress")
        if cached is not None:
            return cached
        url = f"{self.resources_base}/json/SkyChildrenoftheLight/GameProgress.json"
        data = await self._fetch_json(url)
        if data:
            self._set_cache("season_progress", data)
        return data

    def _format_season_result(self, data: Optional[Dict]) -> str:
        if not data:
            return "❌ 获取季节信息失败，请稍后重试"
        season = data.get("season", {})
        season_name = season.get("name", "未知季节")
        start_date = season.get("startDate", "")
        end_date = season.get("endDate", "")
        required_true = season.get("requiredCandlesTrue", 0)
        required_false = season.get("requiredCandlesFalse", 0)
        now = self._get_beijing_time()
        remaining = "未知"
        days = 0
        if end_date and isinstance(end_date, str):
            try:
                date_str = end_date.strip().replace("-", "/")
                date_part = date_str.split()[0]
                end = datetime.strptime(date_part, "%Y/%m/%d")
                diff = end - now
                if diff.total_seconds() <= 0:
                    remaining = "已结束"
                else:
                    days = diff.days
                    hours = diff.seconds // 3600
                    minutes = (diff.seconds % 3600) // 60
                    remaining = f"{days}天{hours}时{minutes}分" if days > 0 else f"{hours}时{minutes}分"
            except Exception:
                remaining = "未知"
        result = f"🌸 当前季节: {season_name}\n"
        if start_date:
            result += f"📅 开始时间: {start_date}\n"
        if end_date:
            result += f"📅 结束时间: {end_date}\n"
        result += f"⏰ 剩余时间: {remaining}\n"
        if days > 0:
            days_with = (required_true + 5) // 6
            days_without = (required_false + 4) // 5
            result += (
                f"\n📊 毕业所需天数:\n"
                f"   有季卡: 约{days_with}天 ({required_true}根季节蜡烛)\n"
                f"   无季卡: 约{days_without}天 ({required_false}根季节蜡烛)"
            )
        return result

    def _compute_debris(self, now: datetime) -> Dict:
        day = now.day
        dow = now.weekday()
        is_first_half = day <= 15
        valid = [1, 5, 6] if is_first_half else [2, 4, 6]
        if dow not in valid:
            return {"has_debris": False}
        map_name = _DEBRIS_MAPS[(day - 1) % len(_DEBRIS_MAPS)]
        debris_type = "红石" if dow in [4, 5, 6] else "黑石"
        location = _DEBRIS_LOCATIONS.get(map_name, {}).get(dow, "未知位置")
        return {
            "has_debris": True,
            "map_name": map_name,
            "location": location,
            "debris_type": debris_type,
            "times": _DEBRIS_TIMES,
        }

    def _format_debris(self, data: Dict) -> str:
        if not data.get("has_debris"):
            return "💎 今日碎石信息\n\n今日无碎石"
        r = (
            f"💎 今日碎石信息\n\n"
            f"📍 地图: {data['map_name']}\n"
            f"📍 位置: {data['location']}\n"
            f"🔷 类型: {data['debris_type']}\n\n"
            f"⏰ 坠落时间:\n"
        )
        for t in data.get("times", []):
            r += f"   • {t}\n"
        r += "\n🎁 奖励: 升华蜡烛\n💡 完成碎石任务可以获得升华蜡烛奖励"
        return r

    def _month_debris(self, year: int, month: int) -> List[Dict]:
        _, dim = _calendar.monthrange(year, month)
        out = []
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for day in range(1, dim + 1):
            dt = datetime(year, month, day)
            dow = dt.weekday()
            is_first_half = day <= 15
            valid = [1, 5, 6] if is_first_half else [2, 4, 6]
            if dow not in valid:
                continue
            map_name = _DEBRIS_MAPS[(day - 1) % len(_DEBRIS_MAPS)]
            debris_type = "红石" if dow in [4, 5, 6] else "黑石"
            location = _DEBRIS_LOCATIONS.get(map_name, {}).get(dow, "未知位置")
            out.append(
                {
                    "date": dt.strftime("%m月%d日"),
                    "weekday": weekdays[dow],
                    "map_name": map_name,
                    "location": location,
                    "debris_type": debris_type,
                }
            )
        return out

    def _format_month_debris(self, year: int, month: int, lst: List[Dict]) -> str:
        r = f"💎 {year}年{month}月碎石日历\n\n"
        if not lst:
            return r + "本月无碎石数据"
        lst = sorted(lst, key=lambda x: x["date"])
        for d in lst:
            icon = "⚫" if d["debris_type"] == "黑石" else "🔴"
            r += f"{icon} {d['date']} ({d['weekday']})\n   {d['map_name']} - {d['location']} ({d['debris_type']})\n\n"
        r += "⏰ 坠落时间: 10:08 / 14:08 / 22:08\n💡 黑石奖励烛火，红石奖励升华蜡烛"
        return r

    @filter.command("season_progress", "季节进度", "当前季节")
    async def season_progress_cmd(self, event: AstrMessageEvent):
        """查询光遇当前季节进度"""
        if not self._cfg("enable_season_progress_query", True):
            yield event.plain_result("❌ 季节进度查询功能未启用")
            return
        data = await self._season_progress_data()
        yield event.plain_result(self._format_season_result(data))

    @filter.command("debris_info", "碎石信息", "碎石")
    async def debris_info_cmd(self, event: AstrMessageEvent):
        """查询今日碎石（黑石/红石）位置"""
        if not self._cfg("enable_debris_query", True):
            yield event.plain_result("❌ 碎石查询功能未启用")
            return
        data = self._compute_debris(self._get_beijing_time())
        yield event.plain_result(self._format_debris(data))

    @filter.command("debris_calendar", "碎石日历")
    async def debris_calendar_cmd(self, event: AstrMessageEvent):
        """查询某月光遇碎石日历，用法: /碎石日历 [月份] [年份]"""
        if not self._cfg("enable_debris_query", True):
            yield event.plain_result("❌ 碎石日历查询功能未启用")
            return
        now = self._get_beijing_time()
        args = self._split_args(event)
        year, month = now.year, now.month
        if args:
            try:
                month = int(args[0])
                if month < 1 or month > 12:
                    raise ValueError
                if len(args) > 1:
                    year = int(args[1])
            except ValueError:
                yield event.plain_result("❌ 月份格式错误，正确示例: /碎石日历 8 或 /碎石日历 8 2026")
                return
        lst = self._month_debris(year, month)
        yield event.plain_result(self._format_month_debris(year, month, lst))

    @filter.command("grandma", "老奶奶时间", "老奶奶", "奶奶")
    async def grandma_cmd(self, event: AstrMessageEvent):
        """查询雨林老奶奶用餐时间"""
        if not self._cfg("enable_grandma_query", True):
            yield event.plain_result("❌ 老奶奶查询功能未启用")
            return
        yield event.plain_result(GRANDMA_SCHEDULE_TEXT)

    @filter.command("sacrifice", "献祭信息", "献祭", "伊甸")
    async def sacrifice_cmd(self, event: AstrMessageEvent):
        """查询献祭（伊甸之眼）信息"""
        if not self._cfg("enable_sacrifice_query", True):
            yield event.plain_result("❌ 献祭查询功能未启用")
            return
        yield event.plain_result(SACRIFICE_INFO_TEXT)

    # ==================================================================
    # 光翼查询 & 光遇ID绑定（持久化）
    # ==================================================================
    def _get_binding_file(self, user_id: str):
        if not self.bindings_dir:
            return None
        return self.bindings_dir / f"{user_id}.json"

    async def _get_user_lock(self, user_id: str) -> asyncio.Lock:
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]

    async def _load_binding(self, user_id: str) -> Dict:
        fp = self._get_binding_file(user_id)
        if fp is None or not fp.exists():
            return {"ids": [], "current_id": None}
        try:
            async with self._file_lock:
                with open(fp, "r", encoding="utf-8") as f:
                    content = f.read().strip()
            return json.loads(content) if content else {"ids": [], "current_id": None}
        except Exception as e:
            logger.error(f"读取绑定数据失败 {fp}: {e}")
            return {"ids": [], "current_id": None}

    async def _save_binding(self, user_id: str, data: Dict):
        fp = self._get_binding_file(user_id)
        if fp is None:
            return
        try:
            async with self._file_lock:
                with open(fp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存绑定数据失败 {fp}: {e}")

    @filter.command("光遇绑定")
    async def bind_sky_id(self, event: AstrMessageEvent, sky_id: str):
        """绑定光遇游戏内短ID，用法: /光遇绑定 <ID>"""
        if not self._cfg("enable_wing_query", True):
            yield event.plain_result("❌ 光翼/绑定功能未启用")
            return
        user_id = event.get_sender_id()
        async with self._get_user_lock(user_id):
            data = await self._load_binding(user_id)
            if sky_id in data["ids"]:
                yield event.plain_result(f"⚠️ ID {sky_id} 已经绑定过了！")
                return
            data["ids"].append(sky_id)
            if not data["current_id"]:
                data["current_id"] = sky_id
            await self._save_binding(user_id, data)
        yield event.plain_result(
            f"✅ 已绑定光遇ID: {sky_id}\n💡 当前ID: {data['current_id']}；可用「光翼查询」查进度"
        )

    @filter.command("光遇切换")
    async def switch_sky_id(self, event: AstrMessageEvent, index: int):
        """切换当前光遇ID，用法: /光遇切换 <序号>"""
        if not self._cfg("enable_wing_query", True):
            yield event.plain_result("❌ 光翼/绑定功能未启用")
            return
        user_id = event.get_sender_id()
        data = await self._load_binding(user_id)
        if not data["ids"]:
            yield event.plain_result("⚠️ 你还没有绑定任何ID，使用「光遇绑定 <ID>」")
            return
        if index < 1 or index > len(data["ids"]):
            yield event.plain_result(f"❌ 序号无效，当前共有 {len(data['ids'])} 个ID")
            return
        data["current_id"] = data["ids"][index - 1]
        await self._save_binding(user_id, data)
        yield event.plain_result(f"✅ 已切换当前ID为: {data['current_id']}")

    @filter.command("光遇删除")
    async def delete_sky_id(self, event: AstrMessageEvent, index: int):
        """删除已绑定的光遇ID，用法: /光遇删除 <序号>"""
        if not self._cfg("enable_wing_query", True):
            yield event.plain_result("❌ 光翼/绑定功能未启用")
            return
        user_id = event.get_sender_id()
        async with self._get_user_lock(user_id):
            data = await self._load_binding(user_id)
            if not data["ids"]:
                yield event.plain_result("⚠️ 你还没有绑定任何ID")
                return
            if index < 1 or index > len(data["ids"]):
                yield event.plain_result(f"❌ 序号无效，当前共有 {len(data['ids'])} 个ID")
                return
            removed = data["ids"].pop(index - 1)
            if data["current_id"] == removed:
                data["current_id"] = data["ids"][0] if data["ids"] else None
            await self._save_binding(user_id, data)
        yield event.plain_result(f"✅ 已删除ID: {removed}")

    @filter.command("光遇ID列表")
    async def list_sky_ids(self, event: AstrMessageEvent):
        """查看已绑定的光遇ID列表"""
        if not self._cfg("enable_wing_query", True):
            yield event.plain_result("❌ 光翼/绑定功能未启用")
            return
        user_id = event.get_sender_id()
        data = await self._load_binding(user_id)
        if not data["ids"]:
            yield event.plain_result("⚠️ 你还没有绑定任何ID，使用「光遇绑定 <ID>」")
            return
        lines = ["📋 你的光遇ID列表:"]
        for i, sid in enumerate(data["ids"], 1):
            mark = " ✅当前" if sid == data["current_id"] else ""
            lines.append(f"  {i}. {sid}{mark}")
        lines.append("\n💡 光翼查询将使用当前ID；可「光遇切换 <序号>」切换")
        yield event.plain_result("\n".join(lines))

    async def _wing_stats_data(self) -> Optional[List]:
        cached = self._get_cache("wing_stats")
        if cached is not None:
            return cached
        data = await self._fetch_json(self.wing_stats_url)
        if isinstance(data, list):
            self._set_cache("wing_stats", data)
            return data
        return None

    def _format_wing_stats(self, data: List) -> str:
        if not data:
            return "❌ 获取光翼数据失败，请稍后重试"
        category_map = {
            "晨岛": "晨",
            "云野": "云",
            "雨林": "雨",
            "霞谷": "霞",
            "暮土": "暮",
            "禁阁": "禁",
            "暴风眼": "暴",
            "复刻永久": "复刻永久",
            "普通永久": "普通永久",
        }
        counts = {v: 0 for v in category_map.values()}
        for item in data:
            k = category_map.get(item.get("一级标签", ""))
            if k:
                counts[k] += 1
        reissue = counts.get("复刻永久", 0)
        normal = counts.get("普通永久", 0)
        r = "🪽 光遇全图光翼统计\n\n"
        r += f"📊 总光翼数量: {len(data)}\n   永久翼: {reissue + normal}个\n   (复刻先祖: {reissue}个, 常驻先祖: {normal}个)\n\n📍 各图光翼数量:\n"
        for name, k in category_map.items():
            if k not in ["复刻永久", "普通永久"]:
                r += f"   {name}: {counts[k]}个\n"
        r += "\n💡 数据来源: 网易大神"
        return r

    @filter.command("光翼统计", "wing_stats", "全图光翼")
    async def wing_stats_cmd(self, event: AstrMessageEvent):
        """查询光遇全图光翼统计"""
        if not self._cfg("enable_wing_query", True):
            yield event.plain_result("❌ 光翼查询功能未启用")
            return
        data = await self._wing_stats_data()
        yield event.plain_result(self._format_wing_stats(data))

    async def _query_wing(self, sky_id: str) -> str:
        if not self.wing_query_key:
            return "❌ 管理员未配置 ovoav_key（独角兽API密钥），光翼查询不可用"
        encoded = quote(str(sky_id), safe="")
        url = f"{self.wing_query_url}?key={self.wing_query_key}&id={encoded}&type=json"
        data = await self._fetch_json(url)
        if not isinstance(data, dict) or not data.get("success"):
            msg = data.get("message", "未知错误") if isinstance(data, dict) else "网络请求失败"
            return f"❌ 查询失败：{msg}"
        stats = data.get("statistics", {})
        role_id = data.get("roleId", "未知")
        ts = data.get("timestamp", "")
        if "T" in ts:
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        total = stats.get("total", 0)
        collected = stats.get("collected", 0)
        uncollected = stats.get("uncollected", 0)
        r = (
            f"🪽 光翼查询结果\n📍 ID: {role_id}\n🕐 数据时间: {ts}\n\n"
            f"📊 光翼统计:\n   总数: {total}\n   已收集: {collected}\n   未收集: {uncollected}\n"
        )
        map_stats = stats.get("map_statistics", {})
        if map_stats:
            r += "\n📍 各地图光翼详情:\n"
            for m, v in map_stats.items():
                r += f"   {m}: 已{v.get('collected', 0)}/共{v.get('total', 0)}\n"
        if total > 0:
            r += f"\n📈 总进度: {collected / total * 100:.1f}% ({collected}/{total})"
        return r

    @filter.command("光翼查询", "wing_query", "光翼")
    async def wing_query_cmd(self, event: AstrMessageEvent, sky_id: str = ""):
        """查询光翼收集进度，用法: /光翼查询 [ID]，省略ID则查当前绑定ID"""
        if not self._cfg("enable_wing_query", True):
            yield event.plain_result("❌ 光翼查询功能未启用")
            return
        if not sky_id:
            data = await self._load_binding(event.get_sender_id())
            sky_id = data.get("current_id")
            if not sky_id:
                yield event.plain_result("⚠️ 请先「光遇绑定 <ID>」或直接加上ID，如「光翼查询 123456」")
                return
        yield event.plain_result(await self._query_wing(sky_id))

    # ==================================================================
    # LLM 自然语言工具
    # ==================================================================
    @filter.llm_tool(name="get_season_progress")
    async def tool_season_progress(self, event: AstrMessageEvent):
        """获取光遇当前季节进度（剩余时间、毕业所需天数）。当用户问“现在是什么季节”“季节还有多久结束”时调用。"""
        if not self._cfg("enable_season_progress_query", True):
            yield event.plain_result("❌ 季节进度查询功能未启用")
            return
        data = await self._season_progress_data()
        yield event.plain_result(self._format_season_result(data))

    @filter.llm_tool(name="get_debris_info")
    async def tool_debris_info(self, event: AstrMessageEvent):
        """获取今日碎石（黑石/红石）位置、类型与坠落时间。当用户问“今天有碎石吗”“碎石在哪里”时调用。"""
        if not self._cfg("enable_debris_query", True):
            yield event.plain_result("❌ 碎石查询功能未启用")
            return
        yield event.plain_result(self._format_debris(self._compute_debris(self._get_beijing_time())))

    @filter.llm_tool(name="get_grandma_schedule")
    async def tool_grandma(self, event: AstrMessageEvent):
        """获取雨林老奶奶用餐时间与挂机烛火信息。当用户问“老奶奶什么时候开饭”“奶奶吃饭时间”时调用。"""
        if not self._cfg("enable_grandma_query", True):
            yield event.plain_result("❌ 老奶奶查询功能未启用")
            return
        yield event.plain_result(GRANDMA_SCHEDULE_TEXT)

    @filter.llm_tool(name="get_sacrifice_guide")
    async def tool_sacrifice(self, event: AstrMessageEvent):
        """获取献祭（伊甸之眼）刷新时间与奖励说明。当用户问“献祭什么时候刷新”“升华蜡烛怎么获得”时调用。"""
        if not self._cfg("enable_sacrifice_query", True):
            yield event.plain_result("❌ 献祭查询功能未启用")
            return
        yield event.plain_result(SACRIFICE_INFO_TEXT)

    @filter.llm_tool(name="get_wing_stats")
    async def tool_wing_stats(self, event: AstrMessageEvent):
        """获取光遇全图光翼统计（各地图数量）。当用户问“光翼有多少个”“全图光翼”时调用。"""
        if not self._cfg("enable_wing_query", True):
            yield event.plain_result("❌ 光翼查询功能未启用")
            return
        yield event.plain_result(self._format_wing_stats(await self._wing_stats_data()))

    @filter.llm_tool(name="query_personal_wings")
    async def tool_wing_query(self, event: AstrMessageEvent, sky_id: str = ""):
        """查询用户个人光翼收集进度。当用户问“我有多少光翼”“我的光翼进度”时调用。sky_id 为可选光遇短ID。"""
        if not self._cfg("enable_wing_query", True):
            yield event.plain_result("❌ 光翼查询功能未启用")
            return
        if not sky_id:
            data = await self._load_binding(event.get_sender_id())
            sky_id = data.get("current_id")
            if not sky_id:
                yield event.plain_result("⚠️ 请先绑定光遇ID或提供 sky_id")
                return
        yield event.plain_result(await self._query_wing(sky_id))

    @filter.llm_tool(name="get_server_queue_status")
    async def tool_server_status(self, event: AstrMessageEvent):
        """获取光遇服务器当前排队状态。当用户问“服务器炸了吗”“需要排队吗”时调用。"""
        url = self._cfg("skytest_url")
        key = self.ovoav_key
        if not key or str(key).startswith("你的"):
            yield event.plain_result("❌ 插件未配置服务器状态API密钥")
            return
        text, err = await _fetch_skytest(url, key, self._cfg("skytest_timeout", 15))
        yield event.plain_result(text or err or "❌ 查询失败")

    # ==================================================================
    # 定时推送调度
    # ==================================================================
    def _create_push_task(self, coro):
        t = asyncio.create_task(coro)
        if not hasattr(self, "_push_tasks"):
            self._push_tasks = set()
        self._push_tasks.add(t)
        t.add_done_callback(lambda _t: self._push_tasks.discard(_t))
        return t

    async def _scheduler_loop(self):
        logger.info("光遇定时推送调度器启动")
        last_exec: Dict[str, bool] = {}
        while self._running:
            try:
                now = self._get_beijing_time()
                key_sec = now.strftime("%Y-%m-%d_%H:%M:%S")
                if (
                    self.enable_grandma_reminder
                    and (now.hour, now.minute) in GRANDMA_REMIND_TIMES
                    and now.second == 0
                ):
                    k = f"grandma_{key_sec}"
                    if k not in last_exec:
                        last_exec[k] = True
                        self._create_push_task(self._push_grandma())
                if (
                    self.enable_sacrifice_reminder
                    and now.weekday() == 5
                    and now.hour == 0
                    and now.minute == 0
                    and now.second == 0
                ):
                    k = f"sac_{key_sec}"
                    if k not in last_exec:
                        last_exec[k] = True
                        self._create_push_task(self._push_sacrifice())
                try:
                    th, tm = map(int, self.daily_task_push_time.split(":"))
                except Exception:
                    th, tm = 8, 0
                if now.hour == th and now.minute == tm and now.second == 0:
                    k = f"daily_{key_sec}"
                    if k not in last_exec:
                        last_exec[k] = True
                        if self.enable_daily_task_push:
                            self._create_push_task(self._push_daily_task())
                        if self.enable_debris_reminder:
                            self._create_push_task(self._push_debris())
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"调度循环出错: {e}")
                await asyncio.sleep(5)

    async def _push_daily_task(self):
        key = self.ovoav_key
        if not key or str(key).startswith("你的"):
            logger.error("每日任务推送: 未配置 ovoav_key（独角兽API密钥）")
            return
        b64, err = await _fetch_image_base64(
            self._cfg("task_url"), key, self._cfg("task_timeout", 15)
        )
        if b64:
            await self._send_push_image(b64, "🌟 光遇今日每日任务")
        else:
            await self._send_push_text("🌟 光遇今日每日任务\n\n⚠️ 图片获取失败，请用「每日任务」命令手动查询")

    async def _push_grandma(self):
        msg = (
            "🍲 老奶奶还有5分钟开饭！\n\n"
            "📍 位置: 雨林隐藏图（秘密花园）\n⏰ 用餐约30分钟\n"
            "💡 带上火盆或火把可自动收集烛火~"
        )
        await self._send_push_text(msg)

    async def _push_sacrifice(self):
        msg = "🔥 献祭已刷新！\n\n📅 每周六凌晨00:00刷新\n💡 记得去暴风眼献祭获取升华蜡烛~"
        await self._send_push_text(msg)

    async def _push_debris(self):
        data = self._compute_debris(self._get_beijing_time())
        if not data.get("has_debris"):
            msg = "💎 今日碎石信息\n\n今日无碎石"
        else:
            msg = (
                f"💎 今日碎石信息\n\n📍 地图: {data['map_name']}\n"
                f"📍 位置: {data['location']}\n🔷 类型: {data['debris_type']}\n\n"
                f"⏰ 坠落时间:\n   • 10:08 (约50分钟)\n   • 14:08 (约50分钟)\n   • 22:08 (约50分钟)\n\n"
                f"🎁 奖励: 升华蜡烛"
            )
        await self._send_push_text(msg)
