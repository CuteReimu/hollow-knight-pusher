from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx
from nonebot import get_driver, on_message, on_command
from nonebot.adapters import Event
from nonebot.adapters.qq.event import (
    GroupAtMessageCreateEvent,
    GroupMessageCreateEvent,
)
from nonebot.log import logger
from nonebot.rule import Rule

from .translate import trie

# ---------------------------------------------------------------------------
# 数据持久化
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_DATA_DIR.mkdir(exist_ok=True)

_GROUP_IDS_FILE = _DATA_DIR / "group_ids.json"
_PUSHED_MSGS_FILE = _DATA_DIR / "pushed_messages.json"
_PENDING_FILE = _DATA_DIR / "pending_push.json"


def _load_group_ids() -> set[str]:
    if _GROUP_IDS_FILE.exists():
        return set(json.loads(_GROUP_IDS_FILE.read_text(encoding="utf-8")))
    return set()


def _save_group_ids() -> None:
    _GROUP_IDS_FILE.write_text(
        json.dumps(list(_group_ids), ensure_ascii=False), encoding="utf-8"
    )


def _load_pushed() -> list[str]:
    if _PUSHED_MSGS_FILE.exists():
        return json.loads(_PUSHED_MSGS_FILE.read_text(encoding="utf-8"))
    return []


def _save_pushed(msgs: list[str]) -> None:
    _PUSHED_MSGS_FILE.write_text(
        json.dumps(msgs, ensure_ascii=False), encoding="utf-8"
    )


def _load_pending() -> dict[str, list[str]]:
    if _PENDING_FILE.exists():
        return json.loads(_PENDING_FILE.read_text(encoding="utf-8"))
    return {}


def _save_pending() -> None:
    _PENDING_FILE.write_text(
        json.dumps(_pending_push, ensure_ascii=False), encoding="utf-8"
    )


_group_ids: set[str] = _load_group_ids()
_pending_push: dict[str, list[str]] = _load_pending()

# ---------------------------------------------------------------------------
# doTimer：每5分钟拉取 speedrun.com 通知
# ---------------------------------------------------------------------------

_re_html = re.compile(r"<.*?>")


async def _do_timer() -> None:
    config = get_driver().config
    api_key: str = getattr(config, "speedrun_api_key", "")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                "https://www.speedrun.com/api/v1/notifications",
                headers={"X-API-Key": api_key},
            )
    except Exception as e:
        logger.error(f"get speedrun notifications failed: {e}")
        return

    if resp.status_code != 200:
        logger.error(
            f"get speedrun notifications failed: {resp.status_code} {resp.text[:200]}"
        )
        return

    data = resp.json()
    pushed = _load_pushed()
    changed = False
    results: list[str] = []

    for v in data.get("data", []):
        vid = v.get("id", "")
        if vid in pushed:
            continue
        pushed.append(vid)
        changed = True
        s = _re_html.sub("", v.get("text", ""))
        if "beat the WR" in s or "got a new top 3 PB" in s:
            results.append(trie.replace_all(s))

    if len(pushed) > 100:
        pushed = pushed[-100:]
        changed = True

    if changed:
        _save_pushed(pushed)

    if results and _group_ids:
        for gid in _group_ids:
            _pending_push.setdefault(gid, []).extend(results)
        _save_pending()


async def _timer_loop() -> None:
    while True:
        await asyncio.sleep(300)
        try:
            await _do_timer()
        except Exception as e:
            logger.error(f"doTimer panic: {e}")


driver = get_driver()


@driver.on_startup
async def _start_timer() -> None:
    asyncio.create_task(_timer_loop())


# ---------------------------------------------------------------------------
# 群机器人订阅/退订事件
# ---------------------------------------------------------------------------

_group_receive_handler = on_command("开启订阅speedrun", priority=10, block=False)
_group_reject_handler = on_command("关闭订阅speedrun", priority=10, block=False)


@_group_receive_handler.handle()
async def _handle_receive(event: Event) -> None:
    if not isinstance(event, GroupMessageCreateEvent):
        await _group_receive_handler.finish()
        return
    _group_ids.add(event.group_openid)
    _save_group_ids()
    logger.info(f"speedrun push enabled for group {event.group_openid}")
    await _group_receive_handler.finish("已开启订阅")


@_group_reject_handler.handle()
async def _handle_reject(event: Event) -> None:
    if not isinstance(event, GroupMessageCreateEvent):
        await _group_receive_handler.finish()
        return
    _group_ids.discard(event.group_openid)
    _save_group_ids()
    logger.info(f"speedrun push disabled for group {event.group_openid}")
    await _group_receive_handler.finish("已关闭订阅")


# ---------------------------------------------------------------------------
# 被动推送：有待推送内容时，借用任意群消息回复
# ---------------------------------------------------------------------------


async def _has_pending_for_group(event: Event) -> bool:
    if not isinstance(event, (GroupAtMessageCreateEvent, GroupMessageCreateEvent)):
        return False
    return event.group_openid in _group_ids and bool(_pending_push.get(event.group_openid))


_push_sender = on_message(rule=Rule(_has_pending_for_group), priority=99, block=False)


@_push_sender.handle()
async def _send_pending(event: Event) -> None:
    gid = event.group_openid  # type: ignore[union-attr]
    msgs = _pending_push.get(gid)
    if not msgs:
        return
    msg = "\n".join(msgs)
    _pending_push.pop(gid, None)
    _save_pending()
    await _push_sender.finish(msg)
