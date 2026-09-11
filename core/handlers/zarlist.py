from pyrogram import Client
from pyrogram.types import Message, User

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from redis.asyncio import Redis

from core.utils.db_api.repo import Repo
from core.data.tricks.tricks import tricks
from core.functions import base_func, respond_func
from core.utils.db_api import Victims

from humanize import intcomma

import asyncio
import re
import html
import time


async def zarlist_command(app: Client, msg: Message, me: User, session: async_sessionmaker[AsyncSession], redis: Redis):
    """Команда {prefix}инф — показывает список жертв и их опыт"""
    trusted_ids = await redis.lrange(f'epidemic_userbot_trusted:{me.id}', 0, -1)

    if msg.from_user.id != me.id and str(msg.from_user.id) not in trusted_ids:
        return

    prefix = await redis.hget(f'epidemic_userbot:{me.id}', 'prefix')

    if msg.text.lower() != f'{prefix}инф':
        return

    async with session() as ses:
        victims = await Repo.get_all_victims(ses, me.id)

    if not victims:
        err = await msg.reply("📝 У вас нет жертв.")
        return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['small_timeout']))

    total_victims = len(victims)
    total_earn = sum(v.victim_bio_resource_earn for v in victims if v.victim_bio_resource_earn)
    now = int(time.time())

    victims_list = []
    for i, v in enumerate(victims[:20], 1):
        async with session() as ses:
            victim_user = await Repo.get_user(ses, v.victim_id)
            kd_record = await Repo.get_victim_kd(ses, me.id, v.victim_id)
        
        name = victim_user[0].full_name if victim_user else str(v.victim_id)
        mention = base_func.entity_create(v.victim_id, name)
        exp = intcomma(v.victim_bio_resource_earn)
        
        # Проверяем КД
        kd_str = ""
        if kd_record:
            kd_expire = int(kd_record.kd_expire)
            if kd_expire > now:
                kd_left = kd_expire - now
                kd_minutes = kd_left // 60
                kd_hours = kd_minutes // 60
                kd_mins = kd_minutes % 60
                if kd_hours > 0:
                    kd_str = f" ⏳ {kd_hours}ч {kd_mins}м"
                else:
                    kd_str = f" ⏳ {kd_mins}м"
        
        victims_list.append(f"{i}. {mention}{kd_str} — <b>{exp}</b> 🧬")

    text = (
        f"☠️ <b>Краткая информация о зарлисте:</b>\n\n"
        f"🦷 <b>Итого:</b> {total_victims:,} заражённых\n"
        f"🏐 <b>Ежедневная Премия:</b> {intcomma(total_earn)} био-ресурсов\n\n"
        f"<b>Список жертв:</b>\n" + "\n".join(victims_list)
    )

    sended_msg = await msg.reply(text)
    asyncio.create_task(respond_func.delete_msg([sended_msg, msg], tricks['config']['huge_timeout']))


async def zarlist_plus_command(app: Client, msg: Message, me: User, session: async_sessionmaker[AsyncSession], redis: Redis):
    """Команда {prefix}зз+ — показывает только выгодных жертв"""
    trusted_ids = await redis.lrange(f'epidemic_userbot_trusted:{me.id}', 0, -1)

    if msg.from_user.id != me.id and str(msg.from_user.id) not in trusted_ids:
        return

    prefix = await redis.hget(f'epidemic_userbot:{me.id}', 'prefix')

    if not re.fullmatch(rf'{re.escape(prefix)}\s*зз\s*\+', msg.text, re.IGNORECASE):
        return

    if not msg.reply_to_message:
        err = await msg.reply("📝 Ответьте на список жертв (топ/бiotop/мои жертвы)")
        return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['small_timeout']))

    try:
        text = msg.reply_to_message.text.html
    except:
        text = msg.reply_to_message.text or ""

    if not text:
        err = await msg.reply("📝 Сообщение пустое.")
        return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['small_timeout']))

    victims = []
    for line in text.splitlines():
        user_id_match = re.search(r'user_id=(\d+)', line)
        if not user_id_match:
            continue

        victim_id = int(user_id_match.group(1))

        exp_match = re.search(r'\| ([\d,\s]+) опыт', line)
        if not exp_match:
            continue

        total_exp = int(exp_match.group(1).replace(',', '').replace(' ', ''))

        async with session() as ses:
            victim = await Repo.get_victim(ses, me.id, victim_id)

        current_earn = victim[0].victim_bio_resource_earn if victim else 0
        potential_earn = int(total_exp * 0.10)
        diff = potential_earn - current_earn

        # Не добавляем себя в список
        if int(victim_id) == me.id:
            continue

        if diff > 0:
            victims.append((victim_id, total_exp, current_earn, potential_earn, diff))

    if not victims:
        err = await msg.reply("📝 Нет выгодных жертв в этом списке.")
        return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['small_timeout']))

    victims.sort(key=lambda x: x[4], reverse=True)

    now = int(time.time())

    victims_list = []
    for i, (vid, total, current, potential, diff) in enumerate(victims[:30], 1):
        async with session() as ses:
            victim_user = await Repo.get_user(ses, vid)
            kd_record = await Repo.get_victim_kd(ses, me.id, vid)

        name = victim_user[0].full_name if victim_user else str(vid)
        mention = base_func.entity_create(vid, name)

        # Проверяем КД
        kd_str = ""
        if kd_record:
            kd_expire = int(kd_record.kd_expire)
            if kd_expire > now:
                kd_left = kd_expire - now
                kd_minutes = kd_left // 60
                kd_hours = kd_minutes // 60
                kd_mins = kd_minutes % 60
                if kd_hours > 0:
                    kd_str = f" ⏳ {kd_hours}ч {kd_mins}м"
                else:
                    kd_str = f" ⏳ {kd_mins}м"

        victims_list.append(
            f"{i}. {mention}{kd_str}\n"
            f"   📊 {intcomma(current)} → <b>{intcomma(potential)}</b> 🧬 (+{intcomma(diff)})"
        )

    result = (
        f"🎯 <b>Выгодные жертвы ({len(victims)}):</b>\n\n"
        + "\n".join(victims_list)
    )

    from .random_commands import generate_random_code, save_random_command
    code = generate_random_code(5)
    victim_ids = [v[0] for v in victims]
    await save_random_command(redis, me.id, code, 'infect_plus', {'victims': victim_ids})

    result += f"\n\n/{code}"

    sended_msg = await msg.reply(result)
    asyncio.create_task(respond_func.delete_msg([sended_msg, msg], tricks['config']['huge_timeout']))
