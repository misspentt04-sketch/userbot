from pyrogram.errors.exceptions import PeerIdInvalid, FloodWait
from pyrogram.types import Message, User
from pyrogram import Client

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy.sql import select, delete, insert
from redis.asyncio import Redis

from datetime import datetime, timedelta

from core.utils.db_api import UserbotVictims, VictimKD
from core.utils.db_api.repo import Repo
from core.data.tricks.tricks import tricks
from core.data.triggers import deep_links
from core.functions import base_func

from humanize import intcomma

import re
import html
import time


async def self_victim_infect(app: Client, msg: Message, me: User, session: async_sessionmaker[AsyncSession], redis: Redis):
    link = base_func.link_getter(msg.text)
    exp = 0
    if msg.reply_to_message and not link:
        link = msg.reply_to_message.from_user.id
        async with session() as ses:
            user = await Repo.get_user(ses, link)
            if user:
                get_victim = await Repo.get_victim(ses, me.id, user[0].id)
                if get_victim:
                    exp = get_victim[0].victim_bio_resource_earn
    elif not link:
        link = '!random'
        exp = '!random'
    await redis.lpush(f'epidemic_userbot_victim:{me.id}:{link}', f'{msg.id}:{exp}')
    await redis.expire(f'epidemic_userbot_victim:{me.id}:{link}', 5)


async def auto_write_infect(app: Client, msg: Message, me: User, session: async_sessionmaker[AsyncSession], redis: Redis):

    # ===== 1. ПАРСИМ КД (Недавно Вы уже подвергали заражению) =====
    if msg.text and 'Недавно Вы уже подвергали заражению' in msg.text:
        kd_match = re.search(r'Следующая возможность появится через\s+(?:(\d+)\s+час(?:ов|а)?\s+)?(\d+)\s+минут', msg.text)
        if kd_match:
            hours = int(kd_match.group(1)) if kd_match.group(1) else 0
            minutes = int(kd_match.group(2))
            total_seconds = hours * 3600 + minutes * 60
            
            victim_id = None
            
            keys = await redis.keys(f'epidemic_userbot_victim:{me.id}:*')
            for key in keys:
                if '!random' in key:
                    continue
                parts = key.split(':')
                if len(parts) >= 3:
                    try:
                        vid = int(parts[-1])
                        victim_id = vid
                        await redis.delete(key)
                        break
                    except:
                        continue
            
            if victim_id:
                kd_expire = int(time.time()) + total_seconds
                
                try:
                    async with session() as ses:
                        async with ses.begin():
                            await ses.execute(
                                delete(VictimKD).where(
                                    VictimKD.owner_id == me.id,
                                    VictimKD.victim_id == victim_id
                                )
                            )
                            await ses.execute(
                                insert(VictimKD).values(
                                    owner_id=me.id,
                                    victim_id=victim_id,
                                    kd_expire=kd_expire
                                )
                            )
                    print(f"[KD FROM BOT] Сохранил КД для {victim_id} на {total_seconds} сек")
                except Exception as e:
                    print(f"[KD FROM BOT ERROR] {e}")
        return

    # ===== 2. ПАРСИМ ЗАРАЖЕНИЕ =====
    if (
        msg.text and
        re.findall(r'🦠 .+ подвер[гла]{1,3} заражению', msg.text.splitlines()[0], re.IGNORECASE) and
        msg.entities and len(msg.entities) >= 3 and int(msg.entities[0].url.split('user_id=')[1]) == me.id
    ):
        victimer_id = int(base_func.link_getter(msg.entities[1].url))
        victimer_username = str(base_func.link_getter(msg.entities[2].url))

        is_random = await redis.lrange(f'epidemic_userbot_victim:{me.id}:!random', 0, 0)

        if is_random:
            links = int(is_random[0].split(':')[0])
            exp = (is_random[0].split(':')[1])
            await redis.lpop(f'epidemic_userbot_victim:{me.id}:!random')
        else:
            links = await redis.lrange(f'epidemic_userbot_victim:{me.id}:{victimer_id}', 0, -1)
            if not links:
                links = await redis.lrange(f'epidemic_userbot_victim:{me.id}:{victimer_username}', 0, -1)
            links = [lnk for lnk in links]
            if links:
                min_val = links[0]
                for nums in links:
                    if int(nums.split(':')[0]) < int(min_val.split(':')[0]):
                        min_val = nums
                links = int(min_val.split(':')[0])
                exp = int(min_val.split(':')[1])
            else:
                return

        victimer_name = re.findall(r'«.+»\s(.+)', msg.text)
        if not victimer_name:
            victimer_name = re.findall(r'неизвестным патогеном\s(.+)', msg.text)
        victimer_name = victimer_name[0]
        victim_expire_days = int(re.findall(r'🤒 Заражение на ([\d\s]+) дней', msg.text)[0])
        victim_expire = datetime.utcnow() + timedelta(days=victim_expire_days)
        bio_resource = re.findall(r'☣️ \+([\d,]+) био-опыта', msg.text)[0].replace(',', '')

        victimer_mention = base_func.entity_create(victimer_id, victimer_name)

        async with session() as ses:
            get_victim = await Repo.get_victim(ses, me.id, victimer_id)

        if exp != '!random':
            victim_exp = exp
            exp_diff = int(int(get_victim[0].victim_bio_resource_earn) - exp)
            bio_resource = (f'+{intcomma(exp_diff)}' if exp_diff > 0 else intcomma(exp_diff))
        else:
            victim_exp = f'+{intcomma(get_victim[0].victim_bio_resource_earn)}'

        text = tricks['game_texts']['infect_style'].format(
            ('✨ ' if '✨' in msg.text.splitlines()[-1] else ''), victimer_id,
            bio_resource, victimer_mention
        )

        # Пытаемся отредактировать сообщение
        try:
            await app.edit_message_text(msg.chat.id, links, text)
            print(f"[EDIT OK] Отредактировал сообщение")
        except Exception as e:
            print(f"[EDIT ERROR] {e}")
            # Если не удалось — отправляем новое
            try:
                await app.send_message(msg.chat.id, text)
                print(f"[SEND OK] Отправил новое сообщение")
            except Exception as e2:
                print(f"[SEND ERROR] {e2}")


async def stop_infect(app: Client, msg: Message, me: User, session: async_sessionmaker[AsyncSession], redis: Redis):

    trusted_ids = await redis.lrange(f'epidemic_userbot_trusted:{me.id}', 0, -1)

    if msg.from_user.id != me.id and str(msg.from_user.id) not in trusted_ids:
        return

    prefix = await redis.hget(f'epidemic_userbot:{me.id}', 'prefix')


    if msg.text.lower() == f'{prefix}б стоп':
        await redis.set(f'epidemic_userbot_infect_stop:{me.id}', 1)
