from typing import Dict, List, Optional, Any

import httpx
from nonebot import on_command
from nonebot.adapters import Event, Message
from nonebot.adapters.qq.event import GroupAtMessageCreateEvent
from nonebot.log import logger
from nonebot.params import CommandArg

from hkbot.plugins.translate import trie

_name_dict_ = {
    "Hollow Knight": "空洞骑士",
    "Hollow Knight Category Extensions": "空洞骑士副榜",
    "Hollow Knight: Silksong": "丝之歌",
    "Hollow Knight: Silksong Category Extensions": "丝之歌副榜",
}

def _try_translate(s: str) -> str:
    if s in _name_dict_:
        return _name_dict_[s]
    return trie.replace_all(s)

# ---------------------------------------------------------------------------
# Speedrun API
# ---------------------------------------------------------------------------

class SpeedrunPersonalBestsAPI:
    """Speedrun.com Personal Best API"""

    def __init__(self):
        self.base_url = "https://www.speedrun.com/api/v1"

        # level cache
        self.level_cache = {}

    # -----------------------------------------------------------------------
    # 时间格式化
    # -----------------------------------------------------------------------

    def format_time_detailed(self, seconds: Any) -> str:
        """秒 -> HH:MM:SS.MS"""

        if seconds is None:
            return "00:00.000"

        try:
            seconds = float(seconds)
        except (ValueError, TypeError):
            return str(seconds)

        if seconds < 0:
            return "00:00.000"

        total_ms = int(round(seconds * 1000))

        hours = total_ms // 3_600_000
        minutes = (total_ms % 3_600_000) // 60_000
        secs = (total_ms % 60_000) // 1000
        milliseconds = total_ms % 1000

        if hours > 0:
            return f"{hours:d}:{minutes:02d}:{secs:02d}"
        elif minutes >= 10:
            return f"{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}.{milliseconds:03d}"

    # -----------------------------------------------------------------------
    # 获取用户
    # -----------------------------------------------------------------------

    async def get_user(self, client: httpx.AsyncClient, username: str) -> Optional[Dict]:
        url = f"{self.base_url}/users"
        params = {"lookup": username}

        try:
            resp = await client.get(url, params=params)

            if resp.status_code != 200:
                logger.warning(f"获取用户失败: {resp.status_code}")
                return None

            data = resp.json()

            if not data.get("data"):
                return None

            user = data["data"][0]

            return {
                "id": user["id"],
                "name": user["names"]["international"],
                "weblink": user["weblink"],
                "signup_date": user["signup"],
                "role": user["role"],
            }

        except Exception as e:
            logger.error(f"获取用户异常: {e}")
            return None

    # -----------------------------------------------------------------------
    # 获取用户 PB
    # -----------------------------------------------------------------------

    async def get_user_personal_bests(self, client: httpx.AsyncClient, user_id: str) -> List[Dict]:
        all_pbs = []
        offset = 0
        max_per_page = 200

        url = f"{self.base_url}/users/{user_id}/personal-bests"

        while True:
            params = {
                "max": max_per_page,
                "offset": offset,
                "embed": "game,category,level,level.variables,category.variables",
            }

            try:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    logger.warning(f"获取 PB 失败: {resp.status_code}")
                    break

                data = resp.json()
                if not data.get("data"):
                    break

                all_pbs.extend(data["data"])
                pagination = data.get("pagination", {})
                links = pagination.get("links", [])

                has_next = any(link.get("rel") == "next" for link in links)
                if has_next:
                    offset += max_per_page
                else:
                    break

            except Exception as e:
                logger.error(f"获取 PB 异常: {e}")
                break

        return all_pbs

    # -----------------------------------------------------------------------
    # 处理 PB
    # -----------------------------------------------------------------------

    async def process_personal_best(self, pb: Dict) -> Optional[Dict]:
        run = pb.get("run", {})
        raw_time = run.get("times", {}).get("primary_t")
        place = pb.get("place")
        # embed 数据
        game_data = pb.get("game", {}).get("data", {})
        category_data = pb.get("category", {}).get("data", {})
        game_name = game_data.get("names", {}).get("international", "未知游戏")
        category_name = category_data.get("name", "未知项目")
        if "Hollow Knight" not in game_name:
            return None

        # ---------------------------------------------------------------
        # level run 判断
        # ---------------------------------------------------------------
        level_id = run.get("level")
        if level_id:
            level_data = pb.get("level", {}).get("data", {})
            full_name = level_data.get("name", "")
        else:
            full_name = category_name

        # ---------------------------------------------------------------
        # values 判断
        # ---------------------------------------------------------------
        values = run.get("values", {})
        for key, value in values.items():
            if level_id:
                variables_data = level_data.get("variables", {}).get("data", {})
            else:
                variables_data = category_data.get("variables", {}).get("data", {})
            for variable in variables_data:
                if variable.get("id") == key:
                    if variable.get("is-subcategory", False):
                        label = variable.get("values", {}).get("values", {}).get(value, {}).get("label")
                        if label:
                            full_name += f" {label}"
                    break

        return {
            "rank": place,
            "game": game_name,
            "category": full_name,
            "time": self.format_time_detailed(raw_time),
        }


# ---------------------------------------------------------------------------
# 文本生成
# ---------------------------------------------------------------------------

async def _get_personal_bests_text(username: str) -> str:
    api = SpeedrunPersonalBestsAPI()
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 用户
        user = await api.get_user(client, username)
        if not user:
            return f"❌ 未找到用户"
        # PB
        pbs = await api.get_user_personal_bests(client, user["id"])
        if not pbs:
            return f"❌ 该用户暂无 PB"
        # 处理 PB
        results = []
        for pb in pbs:
            try:
                result = await api.process_personal_best(pb)
                if result is not None:
                    results.append(result)
            except Exception as e:
                logger.error(f"处理 PB 失败: {e}")
        if not results:
            return f"❌ 记录处理失败"
        # 排序
        results.sort(key=lambda x: x["rank"] if x["rank"] is not None else 999999)

        # -------------------------------------------------------------------
        # 输出
        # -------------------------------------------------------------------
        lines = [
            f"👤 用户: {user['name']}",
            f"📅 注册: {user['signup_date'][:10]}",
            "",
        ]

        # 最多显示 50 条
        for record in results[:50]:
            record["game"] = _try_translate(record["game"])
            record["category"] = _try_translate(record["category"])
            rank_display = f"#{record["rank"]}" if record["rank"] is not None else "N/A"
            game_display = record["game"][:25] + ".." if len(record["game"]) > 25 else record["game"]
            category_display = record["category"][:60] + ".." if len(record["category"]) > 60 else record["category"]
            lines.append(f"{rank_display} {game_display} {category_display} {record['time']}")
        if len(results) > 50:
            lines.append(f"...")

        # -------------------------------------------------------------------
        # QQ 长度限制
        # -------------------------------------------------------------------
        final_lines = []
        current_length = 0
        max_length = 3800
        for line in lines:
            if current_length + len(line) + 1 > max_length:
                final_lines.append("")
                final_lines.append("...(内容过长已截断)")
                break
            final_lines.append(line)
            current_length += len(line) + 1
        return "\r\n".join(final_lines)


# ---------------------------------------------------------------------------
# NoneBot 指令
# ---------------------------------------------------------------------------

personal_cmd = on_command("查个人", priority=10, block=True)


@personal_cmd.handle()
async def handle_personal(event: Event, args: Message = CommandArg()) -> None:
    at_me_msg = "@我 " if isinstance(event, GroupAtMessageCreateEvent) else ""
    username = args.extract_plain_text().strip()
    if not username:
        await personal_cmd.finish(
            f"用法：{at_me_msg}/查个人 <用户名>\r\n"
            f"示例：{at_me_msg}/查个人 SclicheD"
        )
    result_text = f"查询失败"
    try:
        result_text = await _get_personal_bests_text(username)
    except Exception as e:
        logger.error(f"❌ 查询个人 PB 失败: {e}")
    await personal_cmd.finish(result_text)
