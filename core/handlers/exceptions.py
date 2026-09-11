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

    if not re.fullmatch(rf'{re.escape(prefix)}\s*(?:иски|иск)', msg.text, re.IGNORECASE):
        return

    async with session() as ses:
        exceptions = await ExceptionsRepo.get_all_exceptions(ses, me.id)

    if not exceptions:
        sended_msg = await msg.reply("📝 У вас нет исключений.")
        asyncio.create_task(respond_func.delete_msg([sended_msg, msg], tricks['config']['medium_timeout']))
        return

    # Разбиваем на страницы по 30
    PAGE_SIZE = 30
    total_pages = (len(exceptions) + PAGE_SIZE - 1) // PAGE_SIZE

    text_lines = [f"🚫 <b>Исключения юзербота ({len(exceptions)}):</b>\n"]

    for i, exc in enumerate(exceptions[:PAGE_SIZE], 1):
        victim_id = exc.victim_id
        victim_name = exc.victim_name or str(victim_id)
        
        async with session() as ses:
            victim_user = await Repo.get_user(ses, victim_id)
        
        if victim_user:
            victim_name = victim_user[0].full_name
        
        mention = base_func.entity_create(victim_id, html.escape(victim_name))
        
        async with session() as ses:
            victim = await Repo.get_victim(ses, me.id, victim_id)
        
        exp_str = ""
        if victim:
            exp_str = f" | +{intcomma(victim[0].victim_bio_resource_earn)} 🧬"
        else:
            exp_str = " | не заражён"
        
        text_lines.append(f"{i}. {mention}{exp_str}")

    if total_pages > 1:
        text_lines.append(f"\n<i>... и ещё {len(exceptions) - PAGE_SIZE} (стр. 1/{total_pages})</i>")

    text = "\n".join(text_lines)
    sended_msg = await msg.reply(text)
    asyncio.create_task(respond_func.delete_msg([sended_msg, msg], tricks['config']['huge_timeout']))


async def exception_add_command(app: Client, msg: Message, me: User, session: async_sessionmaker[AsyncSession], redis: Redis):
    """Команда {prefix}ис — добавляет/удаляет игрока(ов) из исключений"""
    trusted_ids = await redis.lrange(f'epidemic_userbot_trusted:{me.id}', 0, -1)

    if msg.from_user.id != me.id and str(msg.from_user.id) not in trusted_ids:
        return

    prefix = await redis.hget(f'epidemic_userbot:{me.id}', 'prefix')

    # Проверяем команду
    if not (
        re.fullmatch(rf'{re.escape(prefix)}\s*(?:ис|иск)\s+.*', msg.text, re.IGNORECASE)
        or (msg.text.lower() in [f'{prefix}ис', f'{prefix}иск'] and msg.reply_to_message)
    ):
        return

    # ===== Собираем всех target_id =====
    target_ids = []  # [(victim_id, victim_name), ...]

    # 1. Реплай на список (бт, бч, мои жертвы, обычный)
    if msg.reply_to_message:
        reply_text = msg.reply_to_message.text or ""
        
        # Если реплай на СПИСОК — берём ВСЕ user_id из него
        # Проверяем, есть ли в сообщении несколько user_id
        html_text = ""
        try:
            html_text = msg.reply_to_message.text.html
        except:
            html_text = reply_text
        
        # Ищем все user_id=XXX в HTML
        all_ids = re.findall(r'user_id=(\d{4,16})', html_text)
        
        if all_ids:
            # Это список — берём все ID
            for vid_str in all_ids:
                vid = int(vid_str)
                if vid == me.id:
                    continue
                target_ids.append((vid, None))
        elif msg.reply_to_message.from_user:
            # Обычный реплай на сообщение — берём отправителя
            user = msg.reply_to_message.from_user
            target_ids.append((user.id, user.full_name))

    # 2. Из текста (если не реплай или вместе с реплаем)
    # Ищем @username, ID, tg:// ссылки
    if not target_ids or not msg.reply_to_message:
        # Ищем все ссылки
        all_links = re.findall(
            r'(?:https://t\.me/|@|tg://openmessage\?user_id=)(\d{4,16}|[a-zA-Z0-9_]{5,32})',
            msg.text
        )
        
        for link in all_links:
            if str(link).isdigit():
                target_ids.append((int(link), None))
            else:
                # Username
                try:
                    entity = await app.get_users(link)
                    target_ids.append((entity.id, entity.full_name))
                except:
                    pass

    if not target_ids:
        err = await msg.reply("📝 Укажите @username, ID, реплай на сообщение или список.")
        asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['medium_timeout']))
        return

    # Убираем дубликаты
    target_ids = list({vid: (vid, name) for vid, name in target_ids}.values())

    # ===== Обрабатываем каждого =====
    added = 0
    removed = 0
    errors = []

    for victim_id, victim_name in target_ids:
        # Получаем имя, если нет
        if not victim_name:
            async with session() as ses:
                victim_user = await Repo.get_user(ses, victim_id)
            if victim_user:
                victim_name = victim_user[0].full_name
            else:
                victim_name = str(victim_id)

        # Проверяем, есть ли уже в исключениях
        async with session() as ses:
            is_exc = await ExceptionsRepo.is_exception(ses, me.id, victim_id)

        if is_exc:
            # Удаляем
            async with session() as ses:
                await ExceptionsRepo.remove_exception(ses, me.id, victim_id)
            removed += 1
        else:
            # Добавляем
            async with session() as ses:
                await ExceptionsRepo.add_exception(ses, me.id, victim_id, victim_name)
            added += 1

    # ===== Формируем ответ =====
    result_lines = []
    if added > 0:
        result_lines.append(f"🚫 Добавлено в исключения: <b>{added}</b>")
    if removed > 0:
        result_lines.append(f"✅ Удалено из исключений: <b>{removed}</b>")

    if len(target_ids) <= 10:
        # Показываем имена
        result_lines.append("")
        for vid, vname in target_ids:
            mention = base_func.entity_create(vid, html.escape(vname or str(vid)))
            result_lines.append(f"• {mention}")

    sended_msg = await msg.reply("\n".join(result_lines))
    asyncio.create_task(respond_func.delete_msg([sended_msg, msg], tricks['config']['medium_timeout']))
