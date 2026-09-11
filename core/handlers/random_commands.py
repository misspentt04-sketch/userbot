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
    return ''.join(random.choices(string.ascii_lowercase, k=length))


async def save_random_command(redis: Redis, user_id: int, code: str, action: str, data: dict):
    key = f'epidemic_userbot_random:{user_id}:{code}'
    value = json.dumps({'action': action, 'data': data})
    await redis.set(key, value, ex=60)


async def check_random_command(redis: Redis, user_id: int, code: str) -> dict:
    key = f'epidemic_userbot_random:{user_id}:{code}'
    value = await redis.get(key)
    if value:
        return json.loads(value)
    return None


async def send_buy_vaccine(app: Client):
    """Отправляет .Купить вакцину в ЛС бота"""
    try:
        await app.send_message(tricks['game']['bot_username'], '.Купить вакцину')
        await asyncio.sleep(0.5)
        print("[VACCINE] Отправил .Купить вакцину")
    except Exception as e:
        print(f"[VACCINE ERROR] {e}")


async def random_command_handler(app: Client, msg: Message, me: User, session: async_sessionmaker[AsyncSession], redis: Redis):

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

    await redis.set(f'epidemic_userbot_infect_stop:{me.id}', 0)

    # Отправляем .Купить вакцину перед заражением
    await send_buy_vaccine(app)

    if action == 'infect_all':
        victims = action_data.get('victims', [])
        if not victims:
            return

        count = 0
        for victim_id in victims:
            if int(victim_id) == me.id:
                continue
            
            # Проверяем исключения
            from core.utils.db_api.repo import ExceptionsRepo
            async with session() as ses:
                is_exc = await ExceptionsRepo.is_exception(ses, me.id, int(victim_id))
            if is_exc:
                print(f"[EXCEPTION] Пропускаю {victim_id} (в исключениях)")
                continue
            

            infect_is_stop = await redis.get(f'epidemic_userbot_infect_stop:{me.id}')
            if infect_is_stop and int(infect_is_stop) == 1:
                await redis.set(f'epidemic_userbot_infect_stop:{me.id}', 0)
                sended_msg = await msg.reply(f"🛑 Заражение остановлено! Заразил: {count}")
                asyncio.create_task(respond_func.delete_msg([sended_msg], tricks['config']['medium_timeout']))
                return

            try:
                await app.send_message(msg.chat.id, f'Заразить @{victim_id}')
                count += 1
                await asyncio.sleep(1.2)
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
            if int(victim_id) == me.id:
                continue
            
            # Проверяем исключения
            from core.utils.db_api.repo import ExceptionsRepo
            async with session() as ses:
                is_exc = await ExceptionsRepo.is_exception(ses, me.id, int(victim_id))
            if is_exc:
                print(f"[EXCEPTION] Пропускаю {victim_id} (в исключениях)")
                continue
            

            infect_is_stop = await redis.get(f'epidemic_userbot_infect_stop:{me.id}')
            if infect_is_stop and int(infect_is_stop) == 1:
                await redis.set(f'epidemic_userbot_infect_stop:{me.id}', 0)
                sended_msg = await msg.reply(f"🛑 Заражение остановлено! Заразил: {count}")
                asyncio.create_task(respond_func.delete_msg([sended_msg], tricks['config']['medium_timeout']))
                return

            try:
                await app.send_message(msg.chat.id, f'Заразить @{victim_id}')
                count += 1
                await asyncio.sleep(1.2)
            except Exception as e:
                print(f"[RANDOM INJECT ERROR] {e}")

        sended_msg = await msg.reply(f"🦠 Заражено (выгодных): {count} жертв")
        asyncio.create_task(respond_func.delete_msg([sended_msg], tricks['config']['medium_timeout']))

    elif action == 'infect_file':
        victims = action_data.get('victims', [])
        if not victims:
            return
        
        # Отправляем .Купить вакцину
        await send_buy_vaccine(app)
        
        count = 0
        for victim_id in victims:
            if int(victim_id) == me.id:
                continue
            
            # Проверяем исключения
            from core.utils.db_api.repo import ExceptionsRepo
            async with session() as ses:
                is_exc = await ExceptionsRepo.is_exception(ses, me.id, int(victim_id))
            if is_exc:
                continue
            
            infect_is_stop = await redis.get(f'epidemic_userbot_infect_stop:{me.id}')
            if infect_is_stop and int(infect_is_stop) == 1:
                await redis.set(f'epidemic_userbot_infect_stop:{me.id}', 0)
                sended_msg = await msg.reply(f"🛑 Заражение остановлено! Заразил: {count}")
                asyncio.create_task(respond_func.delete_msg([sended_msg], tricks['config']['medium_timeout']))
                return
            
            try:
                await app.send_message(msg.chat.id, f'Заразить @{victim_id}')
                count += 1
                await asyncio.sleep(1.2)
            except Exception as e:
                print(f"[FILE INJECT ERROR] {e}")
        
        sended_msg = await msg.reply(f"🦠 Заражено из файла: {count} жертв")
        asyncio.create_task(respond_func.delete_msg([sended_msg], tricks['config']['medium_timeout']))

    elif action == 'infect_one':
        victim_id = action_data.get('victim_id')
        if not victim_id:
            return

        # Проверяем исключения
        from core.utils.db_api.repo import ExceptionsRepo
        async with session() as ses:
            is_exc = await ExceptionsRepo.is_exception(ses, me.id, int(victim_id))
        if is_exc:
            print(f"[EXCEPTION] Пропускаю {victim_id} (в исключениях)")
            sended_msg = await msg.reply(f"🚫 @{victim_id} в исключениях. Пропускаю.")
            asyncio.create_task(respond_func.delete_msg([sended_msg], tricks['config']['medium_timeout']))
            return

        try:
            await app.send_message(msg.chat.id, f'Заразить @{victim_id}')
            sended_msg = await msg.reply(f"🦠 Заражён @{victim_id}")
        except Exception as e:
            sended_msg = await msg.reply(f"❌ Ошибка: {e}")

        asyncio.create_task(respond_func.delete_msg([sended_msg], tricks['config']['medium_timeout']))


async def vaccine_all_command(app: Client, msg: Message, me: User, session: async_sessionmaker[AsyncSession], redis: Redis):
    """Команда 'тк' — каждый юзербот покупает вакцину САМ ЗА СЕБЯ"""
    
    # Проверяем команду
    if msg.text.lower().strip() != 'тк':
        return
    
    # Проверяем доступ (только для этого юзербота)
    trusted_ids = await redis.lrange(f'epidemic_userbot_trusted:{me.id}', 0, -1)
    
    if msg.from_user.id != me.id and str(msg.from_user.id) not in trusted_ids:
        return
    
    # Этот юзербот отправляет .Купить вакцину САМ
    try:
        sent = await app.send_message(tricks['game']['bot_username'], '.Купить вакцину')
        
        # Ждём ответа (до 3 сек)
        response_text = None
        for _ in range(10):
            await asyncio.sleep(0.3)
            reply = await app.get_messages(tricks['game']['bot_username'], message_ids=sent.id + 1)
            if not reply.empty and reply.text:
                response_text = reply.text
                break
        
        # Отвечаем в чат
        if response_text:
            if 'Вы здоровы' in response_text or 'излечились' in response_text or 'Затраты на лечение' in response_text or '✅' in response_text:
                await msg.reply(f"✅ <b>Вакцина куплена!</b> — <code>{me.id}</code>")
            else:
                await msg.reply(f"❌ <b>Вакцина не куплена!</b> — <code>{me.id}</code>")
        else:
            await msg.reply(f"❌ <b>Вакцина не куплена!</b> — <code>{me.id}</code>\n└ Ответ не получен")
    except Exception as e:
        await msg.reply(f"❌ <b>Ошибка</b> — <code>{me.id}</code>\n└ {str(e)[:100]}")
