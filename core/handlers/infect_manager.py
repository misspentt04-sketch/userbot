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

    # ===== 2. ПАРСИМ ЗАРАЖЕНИЕ (успешное) =====
    if (
        msg.text and
        re.findall(r'🦠 .+ подвер[гла]{1,3} заражению', msg.text.splitlines()[0], re.IGNORECASE)
    ):
        # ===== УНИВЕРСАЛЬНЫЙ ПАРСИНГ =====
        victimer_id = None
        victimer_username = None
        
        try:
            html_text = msg.text.html
        except:
            html_text = msg.text or ""
        
        # Все user_id из ссылок
        all_ids = re.findall(r'user_id=(\d+)', html_text)
        all_ids.extend(re.findall(r'tg://user\?id=(\d+)', html_text))
        
        # Все @username
        all_usernames = re.findall(r'(?<!user_id=)@([a-zA-Z0-9_]{5,32})', html_text)
        
        print(f"[DEBUG] HTML: {html_text[:200]}")
        print(f"[DEBUG] IDs: {all_ids}, Usernames: {all_usernames}")
        
        # Определяем жертву
        if all_ids:
            if len(all_ids) >= 2 and int(all_ids[0]) == me.id:
                victimer_id = int(all_ids[1])
            elif len(all_ids) == 1:
                victimer_id = int(all_ids[0])
            else:
                for vid in all_ids:
                    if int(vid) != me.id:
                        victimer_id = int(vid)
                        break
        
        if not victimer_id and all_usernames:
            victimer_username = all_usernames[0]
            try:
                entity = await app.get_users(victimer_username)
                victimer_id = entity.id
            except Exception as e:
                print(f"[USERNAME ERROR] {e}")
        
        # Fallback: entities[1]
        if not victimer_id and msg.entities and len(msg.entities) >= 2:
            try:
                url = msg.entities[1].url
                if url:
                    parsed = base_func.link_getter(url)
                    if parsed:
                        if str(parsed).isdigit():
                            victimer_id = int(parsed)
                        else:
                            victimer_username = parsed
                            entity = await app.get_users(victimer_username)
                            victimer_id = entity.id
            except Exception as e:
                print(f"[ENTITIES ERROR] {e}")
        
        if not victimer_id:
            print("[DEBUG] Не удалось определить жертву")
            return

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
        
        if victimer_name:
            victimer_name = victimer_name[0]
        else:
            # Если имя не найдено — берём из БД
            async with session() as ses:
                victim_user = await Repo.get_user(ses, victimer_id)
            if victim_user:
                victimer_name = victim_user[0].full_name
            else:
                victimer_name = str(victimer_id)
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
        
        # Записываем КД ТОЛЬКО при успешном заражении
        try:
            kd_expire = int(time.time()) + 2 * 60 * 60
            async with session() as ses:
                async with ses.begin():
                    await ses.execute(
                        delete(VictimKD).where(
                            VictimKD.owner_id == me.id,
                            VictimKD.victim_id == victimer_id
                        )
                    )
                    await ses.execute(
                        insert(VictimKD).values(
                            owner_id=me.id,
                            victim_id=victimer_id,
                            kd_expire=kd_expire
                        )
                    )
            print(f"[KD SAVE] Сохранил КД для {victimer_id} (успех)")
        except Exception as e:
            print(f"[KD SAVE ERROR] {e}")

        try:
            await app.edit_message_text(msg.chat.id, links, text)
            print(f"[EDIT OK] Отредактировал сообщение")
        except Exception as e:
            print(f"[EDIT ERROR] {e}")
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
