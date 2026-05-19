from collections import Counter
from typing import Dict, List, Optional, Any

import httpx
from nonebot import on_command
from nonebot.adapters import Bot, Message
from nonebot.log import logger
from nonebot.params import CommandArg


# ---------------------------------------------------------------------------
# 个人最佳成绩查询相关代码
# ---------------------------------------------------------------------------

class SpeedrunPersonalBestsAPI:
    """Speedrun.com 个人最佳成绩 API 封装"""

    def __init__(self):
        self.base_url = "https://www.speedrun.com/api/v1"
        self.game_cache = {}
        self.category_cache = {}
        self.level_cache = {}

    def format_time_detailed(self, seconds: Any) -> str:
        """将秒数转换为 HH:MM:SS.MS 格式"""
        if not seconds:
            return "00:00:00.000"
        try:
            seconds = float(seconds)
        except (ValueError, TypeError):
            return str(seconds) if seconds else "00:00:00.000"
        if seconds < 0:
            return "00:00:00.000"

        milliseconds = int((seconds % 1) * 1000)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"
        else:
            return f"{minutes:02d}:{secs:02d}.{milliseconds:03d}"

    async def get_user(self, client: httpx.AsyncClient, username: str) -> Optional[Dict]:
        """获取用户信息"""
        url = f"{self.base_url}/users"
        params = {"lookup": username}

        try:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('data'):
                    user = data['data'][0]
                    return {
                        'id': user['id'],
                        'name': user['names']['international'],
                        'weblink': user['weblink'],
                        'signup_date': user['signup'],
                        'role': user['role']
                    }
        except Exception:
            pass
        return None

    async def get_game_name(self, client: httpx.AsyncClient, game_id: str) -> str:
        """获取游戏名称（带缓存）"""
        if not game_id:
            return "未知游戏"
        if game_id in self.game_cache:
            return self.game_cache[game_id]

        url = f"{self.base_url}/games/{game_id}"
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                game_name = data['data']['names']['international']
                self.game_cache[game_id] = game_name
                return game_name
        except Exception:
            pass
        return f"未知游戏(ID:{game_id})"

    async def get_category_name(self, client: httpx.AsyncClient, category_id: str, game_id: str = None) -> str:
        """获取项目名称（带缓存）"""
        if not category_id:
            return "未知项目"

        cache_key = f"{game_id}:{category_id}" if game_id else category_id
        if cache_key in self.category_cache:
            return self.category_cache[cache_key]

        url = f"{self.base_url}/categories/{category_id}"
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                category_name = data['data']['name']
                self.category_cache[cache_key] = category_name
                return category_name
        except Exception:
            pass
        return f"未知项目(ID:{category_id})"

    async def get_level_name(self, client: httpx.AsyncClient, level_id: str, game_id: str = None) -> Optional[str]:
        """获取关卡名称（带缓存）"""
        if not level_id:
            return None
        if level_id in self.level_cache:
            return self.level_cache[level_id]

        url = f"{self.base_url}/levels/{level_id}"
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                level_name = data['data'].get('name', f"关卡(ID:{level_id})")
                self.level_cache[level_id] = level_name
                return level_name
        except Exception:
            pass
        return f"关卡(ID:{level_id})"

    async def get_user_personal_bests(self, client: httpx.AsyncClient, user_id: str) -> List[Dict]:
        """获取用户的所有个人最佳成绩"""
        all_pbs = []
        offset = 0
        max_per_page = 200
        url = f"{self.base_url}/users/{user_id}/personal-bests"

        while True:
            params = {"max": max_per_page, "offset": offset}
            try:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    break

                data = resp.json()
                if not data or not data.get('data'):
                    break

                all_pbs.extend(data['data'])

                pagination = data.get('pagination', {})
                if pagination.get('links', {}).get('next'):
                    offset += max_per_page
                else:
                    break
            except Exception:
                break

        return all_pbs

    async def process_personal_best(self, client: httpx.AsyncClient, pb: Dict) -> Dict:
        """处理单条个人最佳记录"""
        run = pb.get('run', {})
        game_id = run.get('game')
        category_id = run.get('category')
        level_id = run.get('level')
        raw_time = run.get('times', {}).get('primary_t')
        place = pb.get('place')

        game_name = await self.get_game_name(client, game_id)
        category_name = await self.get_category_name(client, category_id, game_id)

        # 处理关卡信息
        is_level_run = level_id is not None
        level_name = await self.get_level_name(client, level_id, game_id) if is_level_run else None

        if is_level_run and level_name:
            full_name = f"{category_name} - {level_name}"
            run_type = "关卡"
        else:
            full_name = category_name
            run_type = "全流程"

        return {
            'rank': place,
            'game': game_name,
            'category': full_name,
            'type': run_type,
            'time': self.format_time_detailed(raw_time),
            'date': run.get('date', '')[:10] if run.get('date') else '未知',
            'verified': run.get('status', {}).get('status') == 'verified'
        }


# ---------------------------------------------------------------------------
# 个人最佳成绩文本生成
# ---------------------------------------------------------------------------

async def _get_personal_bests_text(username: str) -> str:
    """获取用户的个人最佳成绩并格式化为文本"""
    api = SpeedrunPersonalBestsAPI()

    async with httpx.AsyncClient(timeout=60.0) as client:
        # 获取用户信息
        user = await api.get_user(client, username)
        if not user:
            return f"❌ 未找到用户 '{username}'"

        # 获取个人最佳成绩
        pbs = await api.get_user_personal_bests(client, user['id'])
        if not pbs:
            return f"❌ 用户 '{username}' 暂无个人最佳记录"

        # 处理所有记录
        results = []
        for pb in pbs:
            try:
                result = await api.process_personal_best(client, pb)
                results.append(result)
            except Exception as e:
                logger.error(f"处理记录失败: {e}")
                continue

        if not results:
            return f"❌ 处理用户 '{username}' 的记录时出错"

        # 按排名排序
        results.sort(key=lambda x: x['rank'])

        # 构建输出文本
        lines = []
        lines.append(f"👤 用户: {user['name']}")
        lines.append(f"🆔 ID: {user['id']}")
        lines.append(f"📅 注册: {user['signup_date'][:10]}")
        lines.append(f"🔗 主页: {user['weblink']}")
        lines.append("")
        lines.append(f"🏆 个人最佳成绩列表 (共 {len(results)} 条)")
        lines.append("=" * 50)

        for record in results[:50]:  # 限制显示50条
            rank_display = f"#{record['rank']}"
            game_display = record['game'][:25] + ".." if len(record['game']) > 25 else record['game']
            category_display = record['category'][:30] + ".." if len(record['category']) > 30 else record['category']
            lines.append(
                f"{rank_display:<5} {game_display:<25} {category_display:<30} {record['time']:<15} {record['date']:<10}")

        if len(results) > 50:
            lines.append(f"\n... 还有 {len(results) - 50} 条记录未显示")

        # 统计信息
        lines.append("")
        lines.append("📊 统计信息")
        lines.append("=" * 50)

        # 游戏分布
        game_counts = Counter(r['game'] for r in results)
        lines.append("\n🎮 游戏记录分布:")
        for game, count in game_counts.most_common(5):
            lines.append(f"   {game[:30]:<30}: {count:>2} 条")

        # 类型统计
        level_count = sum(1 for r in results if r['type'] == "关卡")
        full_count = sum(1 for r in results if r['type'] == "全流程")

        lines.append(f"\n📋 记录类型:")
        lines.append(f"   全流程通关: {full_count} 条 ({full_count / len(results) * 100:.1f}%)")
        lines.append(f"   关卡记录: {level_count} 条 ({level_count / len(results) * 100:.1f}%)")

        # 认证统计
        verified_count = sum(1 for r in results if r['verified'])
        lines.append(f"\n✅ 认证状态:")
        lines.append(f"   已认证: {verified_count} 条 ({verified_count / len(results) * 100:.1f}%)")
        lines.append(
            f"   待认证: {len(results) - verified_count} 条 ({(len(results) - verified_count) / len(results) * 100:.1f}%)")

        return "\n".join(lines)


# ---- 个人最佳成绩查询命令 ----
personal_cmd = on_command("查个人", priority=10, block=True)


@personal_cmd.handle()
async def handle_personal(bot: Bot, args: Message = CommandArg()) -> None:
    username = args.extract_plain_text().strip()

    if not username:
        await personal_cmd.finish(
            "用法：@我 /查个人 <用户名>\n"
            "示例：@我 /查个人 cks\n"
            "查询用户在 speedrun.com 上的个人最佳成绩"
        )

    result_text = f"查询用户 '{username}' 失败，请稍后再试。"
    try:
        result_text = await _get_personal_bests_text(username)
        # 如果结果太长，可能会超过QQ消息长度限制，可以截断
        if len(result_text) > 3800:
            result_text = result_text[:3800] + "\n\n... (内容过长已截断)"
    except Exception as e:
        logger.error(f"查询个人最佳成绩失败: {e}")
    await personal_cmd.finish(result_text)
