from __future__ import annotations

from datetime import date, datetime

import httpx
from nonebot import on_command
from nonebot.adapters import Bot, Message
from nonebot.log import logger
from nonebot.params import CommandArg

# ---------------------------------------------------------------------------
# 查询链接
# ---------------------------------------------------------------------------

_URLS: dict[str, str] = {
    "anylp": "https://www.speedrun.com/api/v1/leaderboards/y65r7g81/category/zd39j4nd?var-ylq4yvzn=qzne828q&var-rn1kmmvl=qj70747q",
    "anyrp": "https://www.speedrun.com/api/v1/leaderboards/y65r7g81/category/zd39j4nd?var-ylq4yvzn=qzne828q&var-rn1kmmvl=10vzvmol",
    "te": "https://www.speedrun.com/api/v1/leaderboards/y65r7g81/category/n2y0m18d?var-dloed1dn=qyzod221",
    "100noab": "https://www.speedrun.com/api/v1/leaderboards/y65r7g81/category/rkl6zprk?var-rn1k7xol=lx5o7641&var-38dg4448=1w4p4dmq",
    "100ab": "https://www.speedrun.com/api/v1/leaderboards/y65r7g81/category/rkl6zprk?var-rn1k7xol=lx5o7641&var-38dg4448=qoxpx35q",
    "judgement": "https://www.speedrun.com/api/v1/leaderboards/y65r7g81/category/wk6544o2?var-jlz631q8=1w4ozxvq&var-j8415y58=qox0j35q",
    "sinner": "https://www.speedrun.com/api/v1/leaderboards/y65r7g81/category/wk6544o2?var-jlz631q8=1w4ozxvq&var-j8415y58=1390xmr1",
    "lowst": "https://www.speedrun.com/api/v1/leaderboards/y65r7g81/category/wkp4r60k?var-9l7geqpl=1397dnx1&var-p850r65n=1923x9yq",
    "lowte": "https://www.speedrun.com/api/v1/leaderboards/y65r7g81/category/wkp4r60k?var-9l7geqpl=1397dnx1&var-p850r65n=12vn9wdq",
    "abact1": "https://www.speedrun.com/api/v1/leaderboards/y65r7g81/category/w206ox52?var-kn0eyxz8=10vzo8wl&var-rn16z5p8=qvv7xrrq",
    "abact2": "https://www.speedrun.com/api/v1/leaderboards/y65r7g81/category/w206ox52?var-kn0eyxz8=10vzo8wl&var-rn16z5p8=le2on4ml",
    "abact3": "https://www.speedrun.com/api/v1/leaderboards/y65r7g81/category/w206ox52?var-kn0eyxz8=10vzo8wl&var-rn16z5p8=q5v6457l",
    "twisted": "https://www.speedrun.com/api/v1/leaderboards/yd4r2x51/category/5dwm145k?var-wle492kn=10v8m0pl",
    "苔穴": "https://www.speedrun.com/api/v1/leaderboards/yd4r2x51/level/9m58yezd/xd1ypjwd?var-r8r69958=qvvpvrrq",
    "pop": "https://www.speedrun.com/api/v1/leaderboards/76rqmld8/level/r9g1qop9/wkpq608d",
    "白色宫殿": "https://www.speedrun.com/api/v1/leaderboards/76rqmld8/level/69znevg9/wkpq608d?var-r8r11k7n=klr8rr21",
}

_CATEGORY_NAMES: dict[str, str] = {
    "anylp": "丝之歌 — Any% 斗篷",
    "anyrp": "丝之歌 — Any% 无斗篷",
    "te": "丝之歌 — True Ending",
    "100noab": "丝之歌 — 100% No AB",
    "100ab": "丝之歌 — 100% All Bosses",
    "judgement": "丝之歌 — 第一幕 - 末代裁决者",
    "sinner": "丝之歌 — 第一幕 - 罪途",
    "lowst": "丝之歌 — Low%",
    "lowte": "丝之歌 — Low% True Ending",
    "abact1": "丝之歌 — All Bosses - Act1",
    "abact2": "丝之歌 — All Bosses - Act2",
    "abact3": "丝之歌 — All Bosses - Act3",
    "twisted": "丝之歌 — Twisted%",
    "苔穴": "丝之歌 — 苔穴",
    "pop": "空洞骑士 — 苦痛之路",
    "白色宫殿": "空洞骑士 — 白色宫殿 1.3.1.5+",
}

_MAP_KEYS: dict[str, list[str]] = {
    "any": ["anyrp", "anylp"],
    "100": ["100noab", "100ab"],
    "low": ["lowst", "lowte"],
    "ab": ["abact1", "abact2", "abact3"],
    "all bosses": ["abact1", "abact2", "abact3"],
    "all boss": ["abact1", "abact2", "abact3"],
    "allbosses": ["abact1", "abact2", "abact3"],
    "allboss": ["abact1", "abact2", "abact3"],
    "苦痛之路": ["pop"],
    "苦痛": ["pop"],
    "白宫": ["白色宫殿"],
    "act1": ["judgement", "sinner"],
    "第一幕": ["judgement", "sinner"],
}

_AVAILABLE_INPUTS: list[str] = ["Any%", "TE", "100%", "第一幕", "Low%", "AB", "Twisted%", "苔穴", "PoP", "白色宫殿"]
_ALIAS_INPUTS: list[str] = ["all bosses", "all boss", "allbosses", "allboss", "苦痛", "苦痛之路", "白宫", "act1"]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """小写化并去除百分号（全半角）"""
    return text.lower().replace("%", "").replace("％", "").strip()


def _is_valid_input(normalized: str) -> bool:
    for s in _AVAILABLE_INPUTS + _ALIAS_INPUTS:
        if normalized == _normalize(s):
            return True
    return False


def _format_time(seconds: float) -> str:
    total_s = int(seconds)
    m, s_int = divmod(total_s, 60)
    s_float = seconds - total_s + s_int
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s_int:02d}"
    if m < 10:
        return f"{m}:{s_float:06.3f}"
    return f"{m:02d}:{s_int:02d}"


def _diff_date(date_str1: str, date_str2: str) -> float:
    obj1 = datetime.fromisoformat(date_str1.replace('Z', '+00:00'))
    obj2 = datetime.fromisoformat(date_str2.replace('Z', '+00:00'))
    d = obj1 - obj2
    return d.days + d.seconds / 86400


def _format_relative_date(date_str: str) -> str:
    if not date_str:
        return date_str
    try:
        run_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return date_str
    today = date.today()
    days = (today - run_date).days
    if days == 0:
        return "今天"
    if days == 1:
        return "昨天"
    if days == 2:
        return "前天"
    if 3 <= days < 30:
        return f"{days}天前"
    if 30 <= days < 60:
        return "上个月"
    if days >= 60:
        months = days // 30
        if months >= 12:
            return f"{months // 12}年前"
        return f"{months}个月前"
    return date_str


def _get_player_name(ref_id: str, players: list[dict], ref_name: str) -> str:
    for p in players:
        if p.get("id") == ref_id:
            return p.get("names", {}).get("international", "Unknown")
    return ref_name or "Unknown"


# ---------------------------------------------------------------------------
# 数据获取
# ---------------------------------------------------------------------------

async def _fetch_data(client: httpx.AsyncClient, key: str) -> dict:
    """拉取单个分类 Top 5 排名，返回结构化字典"""
    url = _URLS.get(key)
    if url is None:
        raise ValueError(f"未知的分类: {key}")

    sep = "&" if "?" in url else "?"
    url += f"{sep}embed=players&top=5"

    resp = await client.get(url)
    resp.raise_for_status()
    data = resp.json()

    runs_raw: list[dict] = data["data"]["runs"][:5]
    players: list[dict] = data["data"]["players"]["data"]

    runs = []
    total_dates = 0
    total_diff_dates = 0
    for entry in runs_raw:
        place = entry["place"]
        run = entry["run"]
        time_str = _format_time(run["times"]["primary_t"])
        player_refs: list[dict] = run.get("players", [])
        player_name = "Unknown"
        if player_refs:
            ref = player_refs[0]
            player_name = _get_player_name(ref.get("id", ""), players, ref.get("name", ""))
        run_date = run.get("date", "")
        submit_date = run.get("submitted", "")
        verify_date = run.get("status", {}).get("verify-date", "")
        if submit_date and verify_date:
            diff_date = _diff_date(verify_date, submit_date)
            total_diff_dates += diff_date
            total_dates += 1
        runs.append({
            "place": place,
            "player": player_name,
            "time": time_str,
            "date": _format_relative_date(run_date) if run_date else "",
        })

    if total_dates == 0:
        return {"name": _CATEGORY_NAMES[key], "runs": runs}

    return {"name": _CATEGORY_NAMES[key], "runs": runs, "total_dates": total_diff_dates / total_dates}

async def _request_speedrun(normalized_arg: str) -> list[dict]:
    """根据规范化的用户输入查询对应排行榜，返回 sections 列表"""
    keys = _MAP_KEYS.get(normalized_arg, [normalized_arg])
    sections: list[dict] = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for key in keys:
            sections.append(await _fetch_data(client, key))
    return sections


def _sections_to_text(sections: list[dict]) -> str:
    """将 sections 转为纯文本"""
    lines: list[str] = []
    for sec in sections:
        lines.append(f"=== {sec['name']} — NMG ===")
        if not sec["runs"]:
            lines.append("暂无记录")
        else:
            for run in sec["runs"]:
                date_suffix = f" — {run['date']}" if run["date"] else ""
                lines.append(f"{run['place']}. {run['player']} — {run['time']}{date_suffix}")
        if "total_dates" in sec:
            avg_date = sec["total_dates"]
            if avg_date and avg_date >= 0.5:
                lines.append(f"平均审核时间: {avg_date:.0f} 天")
        lines.append("")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# NoneBot2 命令处理器
# ---------------------------------------------------------------------------

speedrun_cmd = on_command("查榜", priority=10, block=True)


@speedrun_cmd.handle()
async def handle_speedrun(bot: Bot, args: Message = CommandArg()) -> None:
    raw_arg = args.extract_plain_text().strip()

    if not raw_arg:
        await speedrun_cmd.finish(
            "用法：/查榜 <分类>\n支持的榜单类型有：" + "，".join(_AVAILABLE_INPUTS)
        )

    normalized = _normalize(raw_arg)

    if not _is_valid_input(normalized):
        await speedrun_cmd.finish(
            "支持的榜单类型有：" + "，".join(_AVAILABLE_INPUTS)
        )

    try:
        sections = await _request_speedrun(normalized)
    except Exception as e:
        logger.error(f"查询 speedrun 排行榜失败: {e}")
        await speedrun_cmd.finish("查询失败，请稍后再试。")
        return

    await speedrun_cmd.finish(_sections_to_text(sections))
