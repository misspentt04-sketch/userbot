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
import html


async def zarlist_command(app: Client, msg: Message, me: User, session: async_sessionmaker[AsyncSession], redis: Redis):
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
    
    victims_list = []
    for i, v in enumerate(victims[:20], 1):
        async with session() as ses:
            victim_user = await Repo.get_user(ses, v.victim_id)
        name = victim_user[0].full_name if victim_user else str(v.victim_id)
        mention = base_func.entity_create(v.victim_id, html.escape(name))
        exp = intcomma(v.victim_bio_resource_earn)
        victims_list.append(f"{i}. {mention} — <b>{exp}</b> 🧬")
    
    text = (
        f"☠️ <b>Краткая информация о зарлисте:</b>\n\n"
        f"🦷 <b>Итого:</b> {total_victims:,} заражённых\n"
        f"🏐 <b>Ежедневная Премия:</b> {intcomma(total_earn)} био-ресурсов\n\n"
        f"<b>Список жертв:</b>\n" + "\n".join(victims_list)
    )
    
    sended_msg = await msg.reply(text)
    asyncio.create_task(respond_func.delete_msg([sended_msg, msg], tricks['config']['huge_timeout']))
