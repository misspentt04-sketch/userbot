from pyrogram import Client
from pyrogram.types import Message, User

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from redis.asyncio import Redis

from core.utils.db_api.repo import Repo
from core.data.tricks.tricks import tricks
from core.functions import base_func, respond_func

from humanize import intcomma

import asyncio
import random
import string
import json
import re
import html


def generate_random_code(length: int = 5) -> str:
    """Генерирует случайный код из английских букв"""
    return ''.join(random.choices(string.ascii_lowercase, k=length))


async def save_random_command(redis: Redis, user_id: int, code: str, action: str, data: dict):
    """Сохраняет рандомную команду в Redis на 1 минуту"""
    key = f'epidemic_userbot_random:{user_id}:{code}'
    value = json.dumps({'action': action, 'data': data})
    await redis.set(key, value, ex=60)


async def check_random_command(redis: Redis, user_id: int, code: str) -> dict:
    """Проверяет рандомную команду"""
    key = f'epidemic_userbot_random:{user_id}:{code}'
    value = await redis.get(key)
    if value:
        return json.loads(value)
    return None


async def random_command_handler(app: Client, msg: Message, me: User, session: async_sessionmaker[AsyncSession], redis: Redis):
    """Обрабатывает рандомные команды для заражения"""

    trusted_ids = await redis.lrange(f'epidemic_userbot_trusted:{me.id}', 0, -1)

    if msg.from_user.id != me.id and str(msg.from_user.id) not in trusted_ids:
        return

    text = msg.text.strip().lower()
    if text.startswith('/'):
        text = text[1:]

    if len(text) > 5 or len(text) == 0 or not text.isascii() or not text.isalpha():
        return

    data = await check_random_command(redis, me.id, text)
    if not data:
        return

    action = data.get('action')
    action_data = data.get('data', {})

    await redis.delete(f'epidemic_userbot_random:{me.id}:{text}')

    try:
        await msg.delete()
    except:
        pass

    # Сбрасываем флаг остановки
    await redis.set(f'epidemic_userbot_infect_stop:{me.id}', 0)

    if action == 'infect_all':
        victims = action_data.get('victims', [])
        if not victims:
            return

        count = 0
        for victim_id in victims:
            # Проверяем флаг остановки
            infect_is_stop = await redis.get(f'epidemic_userbot_infect_stop:{me.id}')
            if infect_is_stop and int(infect_is_stop) == 1:
                await redis.set(f'epidemic_userbot_infect_stop:{me.id}', 0)
                sended_msg = await msg.reply(f"🛑 Заражение остановлено! Заразил: {count}")
                asyncio.create_task(respond_func.delete_msg([sended_msg], tricks['config']['medium_timeout']))
                return

            try:
                await app.send_message(msg.chat.id, f'Заразить @{victim_id}')
                count += 1
                
                # Записываем КД
                try:
                    async with session() as ses:
                        await Repo.save_victim_kd(ses, me.id, victim_id)
                    print(f"[KD SAVE] Сохранил КД для {victim_id}")
                except Exception as e:
                    print(f"[KD SAVE ERROR] {e}")
                
                await asyncio.sleep(2)
            except Exception as e:
                print(f"[RANDOM INJECT ERROR] {e}")

        sended_msg = await msg.reply(f"🦠 Заражено: {count} жертв")
        asyncio.create_task(respond_func.delete_msg([sended_msg], tricks['config']['medium_timeout']))

    elif action == 'infect_plus':
        victims = action_data.get('victims', [])
        if not victims:
            return

        count = 0
        for victim_id in victims:
            infect_is_stop = await redis.get(f'epidemic_userbot_infect_stop:{me.id}')
            if infect_is_stop and int(infect_is_stop) == 1:
                await redis.set(f'epidemic_userbot_infect_stop:{me.id}', 0)
                sended_msg = await msg.reply(f"🛑 Заражение остановлено! Заразил: {count}")
                asyncio.create_task(respond_func.delete_msg([sended_msg], tricks['config']['medium_timeout']))
                return

            try:
                await app.send_message(msg.chat.id, f'Заразить @{victim_id}')
                count += 1
                
                async with session() as ses:
                    await Repo.save_victim_kd(ses, me.id, victim_id)
                
                await asyncio.sleep(2)
            except Exception as e:
                print(f"[RANDOM INJECT ERROR] {e}")

        sended_msg = await msg.reply(f"🦠 Заражено (выгодных): {count} жертв")
        asyncio.create_task(respond_func.delete_msg([sended_msg], tricks['config']['medium_timeout']))

    elif action == 'infect_one':
        victim_id = action_data.get('victim_id')
        if not victim_id:
            return

        try:
            await app.send_message(msg.chat.id, f'Заразить @{victim_id}')
            
            # Записываем КД
            try:
                async with session() as ses:
                    await Repo.save_victim_kd(ses, me.id, victim_id)
                print(f"[KD SAVE] Сохранил КД для {victim_id}")
            except Exception as e:
                print(f"[KD SAVE ERROR] {e}")
            
            sended_msg = await msg.reply(f"🦠 Заражён @{victim_id}")
        except Exception as e:
            sended_msg = await msg.reply(f"❌ Ошибка: {e}")

        asyncio.create_task(respond_func.delete_msg([sended_msg], tricks['config']['medium_timeout']))
