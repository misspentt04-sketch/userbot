from pyrogram import Client
from pyrogram.types import Message, User

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from redis.asyncio import Redis

from core.utils.db_api.repo import Repo, ExceptionsRepo
from core.utils.db_api import UserbotExceptions
from core.data.tricks.tricks import tricks
from core.functions import base_func, respond_func

from humanize import intcomma

import asyncio
import re
import html


async def exceptions_list_command(app: Client, msg: Message, me: User, session: async_sessionmaker[AsyncSession], redis: Redis):
    """Команда {prefix}иски — показывает список исключений"""
    trusted_ids = await redis.lrange(f'epidemic_userbot_trusted:{me.id}', 0, -1)

    if msg.from_user.id != me.id and str(msg.from_user.id) not in trusted_ids:
        return

    prefix = await redis.hget(f'epidemic_userbot:{me.id}', 'prefix')

    if msg.text.lower() not in [f'{prefix}иски', f'{prefix}иск']:
        return

    async with session() as ses:
        exceptions = await ExceptionsRepo.get_all_exceptions(ses, me.id)

    if not exceptions:
        sended_msg = await msg.reply("📝 У вас нет исключений.")
        asyncio.create_task(respond_func.delete_msg([sended_msg, msg], tricks['config']['medium_timeout']))
        return

    text_lines = [f"🚫 <b>Исключения юзербота ({len(exceptions)}):</b>\n"]

    for i, exc in enumerate(exceptions, 1):
        victim_id = exc.victim_id
        victim_name = exc.victim_name or str(victim_id)
        
        # Пробуем получить актуальное имя
        async with session() as ses:
            victim_user = await Repo.get_user(ses, victim_id)
        
        if victim_user:
            victim_name = victim_user[0].full_name
        
        mention = base_func.entity_create(victim_id, html.escape(victim_name))
        
        # Считаем опыт
        async with session() as ses:
            victim = await Repo.get_victim(ses, me.id, victim_id)
        
        exp_str = ""
        if victim:
            exp_str = f" | +{intcomma(victim[0].victim_bio_resource_earn)} 🧬"
        else:
            exp_str = " | не заражён"
        
        text_lines.append(f"{i}. {mention}{exp_str}")

    text = "\n".join(text_lines)
    sended_msg = await msg.reply(text)
    asyncio.create_task(respond_func.delete_msg([sended_msg, msg], tricks['config']['huge_timeout']))


async def exception_add_command(app: Client, msg: Message, me: User, session: async_sessionmaker[AsyncSession], redis: Redis):
    """Команда {prefix}ис — добавляет/удаляет игрока из исключений"""
    trusted_ids = await redis.lrange(f'epidemic_userbot_trusted:{me.id}', 0, -1)

    if msg.from_user.id != me.id and str(msg.from_user.id) not in trusted_ids:
        return

    prefix = await redis.hget(f'epidemic_userbot:{me.id}', 'prefix')

    # Проверяем команду (ас, аис, а ис)
    if not (
        re.fullmatch(rf'{re.escape(prefix)}\s*(?:ис|иск)\s+.*', msg.text, re.IGNORECASE)
        or (msg.text.lower() == f'{prefix}ис' and msg.reply_to_message)
    ):
        return

    # Парсим цель
    victim_id = None
    victim_name = None

    # Из реплая
    if msg.reply_to_message and msg.reply_to_message.from_user:
        victim_id = msg.reply_to_message.from_user.id
        victim_name = msg.reply_to_message.from_user.full_name
    else:
        # Из текста
        target = base_func.link_getter(msg.text)
        
        if target:
            if str(target).isdigit():
                victim_id = int(target)
            else:
                # Username
                try:
                    entity = await app.get_users(target)
                    victim_id = entity.id
                    victim_name = entity.full_name
                except Exception as e:
                    err = await msg.reply(f"❌ Не удалось найти игрока: {e}")
                    asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['medium_timeout']))
                    return
        else:
            err = await msg.reply("📝 Укажите @username, ID или реплай на сообщение.")
            asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['medium_timeout']))
            return

    if not victim_id:
        err = await msg.reply("📝 Не удалось определить игрока.")
        asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['medium_timeout']))
        return

    # Получаем имя
    if not victim_name:
        async with session() as ses:
            victim_user = await Repo.get_user(ses, victim_id)
        if victim_user:
            victim_name = victim_user[0].full_name
        else:
            victim_name = str(victim_id)

    mention = base_func.entity_create(victim_id, html.escape(victim_name))

    # Проверяем, есть ли уже в исключениях
    async with session() as ses:
        is_exc = await ExceptionsRepo.is_exception(ses, me.id, victim_id)

    if is_exc:
        # Удаляем
        async with session() as ses:
            await ExceptionsRepo.remove_exception(ses, me.id, victim_id)
        
        sended_msg = await msg.reply(f"✅ {mention} удалён из исключений.")
    else:
        # Добавляем
        async with session() as ses:
            await ExceptionsRepo.add_exception(ses, me.id, victim_id, victim_name)
        
        sended_msg = await msg.reply(f"🚫 {mention} добавлен в исключения. Юзербот не будет его заражать.")

    asyncio.create_task(respond_func.delete_msg([sended_msg, msg], tricks['config']['medium_timeout']))
