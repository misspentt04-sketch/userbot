from pyrogram.types import Message, User
from pyrogram.errors.exceptions import PeerIdInvalid, FloodWait
from pyrogram import Client, enums

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import select, insert, delete
from redis.asyncio import Redis

from core.utils.db_api import UserbotTrustedUsers
from core.utils.db_api.repo import Repo
from core.data.tricks.tricks import tricks
from core.data import triggers as trg
from core.functions import base_func, respond_func

from humanize import intcomma
from datetime import datetime, timedelta
from loguru import logger

import re
import asyncio
import json
import html
import time


async def main_skills(app: Client, msg: Message, me: User, session: async_sessionmaker[AsyncSession], redis: Redis):

    trusted_ids = await redis.lrange(f'epidemic_userbot_trusted:{me.id}', 0, -1)

    if msg.from_user.id != me.id and str(msg.from_user.id) not in trusted_ids:
        return

    # ===== ОБРАБОТКА ФАЙЛОВ =====
    # Если это файл — скачиваем и подменяем msg.text
    if msg.document:
        try:
            file_path = await msg.download()
            with open(file_path, 'r', encoding='utf-8') as f:
                file_text = f.read()
            
            # Подменяем текст сообщения на содержимое файла
            msg.text = file_text
            
            # Удаляем временный файл
            import os
            os.remove(file_path)
            
            print(f"[FILE] Загружен файл, {len(file_text)} символов")
        except Exception as e:
            print(f"[FILE ERROR] {e}")
            return
    
    # Аналогично для реплая на файл
    if msg.reply_to_message and msg.reply_to_message.document:
        try:
            file_path = await msg.reply_to_message.download()
            with open(file_path, 'r', encoding='utf-8') as f:
                file_text = f.read()
            
            # Подменяем текст реплая на содержимое файла
            msg.reply_to_message.text = file_text
            
            import os
            os.remove(file_path)
            
            print(f"[FILE] Загружен файл из реплая, {len(file_text)} символов")
        except Exception as e:
            print(f"[FILE ERROR] {e}")
            return

    if msg.reply_to_message:
        reply_text = msg.reply_to_message.text

    prefix = await redis.hget(f'epidemic_userbot:{me.id}', 'prefix')

    # Infect
    if msg.text is not None and (
        # Просто "аб" реплаем на любое сообщение
        re.fullmatch(f'{re.escape(prefix)}б', msg.text, re.IGNORECASE) and msg.reply_to_message
        or
        re.fullmatch(f'{re.escape(prefix)}б' + r'\s{1,3}' + r'(\d{1,2}\s{1,3}|)' + trg.re_link_sup, msg.text, re.IGNORECASE)
        or
        re.fullmatch(f'{prefix}б' + r'(\s+[\d\s\-]+|)', msg.text.lower()) and msg.reply_to_message and (
            reply_text and msg.reply_to_message.text.lower().startswith(tricks['game_texts']['sec_serv']) or
            reply_text and
            re.findall(r'🦠 .+ подвер[гла]{1,3} заражению', msg.reply_to_message.text.splitlines()[0], re.IGNORECASE)
            or reply_text and '🪬 Иммунитет объекта' in msg.reply_to_message.text and
            msg.reply_to_message.entities and
            len(msg.reply_to_message.entities) == 1
        ) or
        (
            msg.reply_to_message and
            msg.reply_to_message.document and
            re.fullmatch(f'{re.escape(prefix)}б' + r'\s+[\d\s\-]+', msg.text, re.IGNORECASE)
        ) or
        (
            msg.reply_to_message and
            msg.reply_to_message.document and
            re.fullmatch(f'{re.escape(prefix)}б' + r'\s+[-\d\s]+', msg.text, re.IGNORECASE)
        ) or
        (
            msg.reply_to_message and
            reply_text and
            re.search(r'@\d{6,16}', msg.reply_to_message.text) and
            re.fullmatch(f'{re.escape(prefix)}б' + r'\s+[-\d\s]+', msg.text, re.IGNORECASE)
        ) or
        msg.reply_to_message and (
            reply_text and '@' in msg.reply_to_message.text
            or
            msg.reply_to_message.entities and len(msg.reply_to_message.entities) >= 1
        ) and
        re.fullmatch(f'{re.escape(prefix)}б' + r'\s+[-\d\s]+', msg.text, re.IGNORECASE)
    ):
        quote = False
        list_infect = False
        msg_to = msg
        link = None
        pathogens_to_use = False
        if len(msg.text.split()) > 1 and msg.text.split()[1].isdigit():
            pathogens_to_use = msg.text.split()[1]
        if re.fullmatch(f'{re.escape(prefix)}б' + r'\s{1,3}' + r'(\d{1,2}\s{1,3}|)' + trg.re_link_sup, msg.text, re.IGNORECASE):
            link = base_func.link_getter(msg.text)
        if (
            msg.reply_to_message and
            msg.reply_to_message.text.lower().startswith(tricks['game_texts']['sec_serv']) and
            len(msg.reply_to_message.entities) >= 3
        ):
            link = base_func.link_getter(msg.reply_to_message.entities[2].url)
            quote = True
            msg_to = msg.reply_to_message
        elif (
            msg.reply_to_message and
            re.findall(r'🦠 .+ подвер[гла]{1,3} заражению', msg.reply_to_message.text.splitlines()[0], re.IGNORECASE) and
            len(msg.reply_to_message.entities) >= 2
        ):
            link = base_func.link_getter(msg.reply_to_message.entities[1].url)
        elif (
            msg.reply_to_message and '🪬 Иммунитет объекта' in msg.reply_to_message.text and
            msg.reply_to_message.entities and len(msg.reply_to_message.entities) == 1
        ):
            link = base_func.link_getter(msg.reply_to_message.entities[0].url)
        elif (
            msg.reply_to_message and
            msg.reply_to_message.from_user and
            not re.fullmatch(f'{re.escape(prefix)}б' + r'\s{1,3}([-\d\s]{1,20})', msg.text, re.IGNORECASE)
        ):
            # Обычный реплай — берём ID из from_user
            link = msg.reply_to_message.from_user.id
        elif (
            msg.reply_to_message and
            re.fullmatch(f'{re.escape(prefix)}б' + r'\s+[-\d\s]+', msg.text, re.IGNORECASE)
        ):
            list_infect = True
            print(f"[AB DEBUG] text={msg.text!r}")
            print(f"[AB DEBUG] reply_text={msg.reply_to_message.text!r}")
            print(f"[AB DEBUG] is_document={bool(msg.reply_to_message.document)}")
            # Парсим строки: чистый ID, @ID, @username, tg:// или \n-разделители
            link = []
            raw_text = msg.reply_to_message.text
            # Заменяем литеральный \n на реальный перенос
            raw_text = raw_text.replace('\\n', '\n')
            for line in raw_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                # Чистый ID
                if re.fullmatch(r'\d{6,16}', line):
                    link.append(int(line))
                    continue
                # @123456789 — ID с @
                at_id = re.search(r'@(\d{6,16})', line)
                if at_id:
                    link.append(int(at_id.group(1)))
                    continue
                # @username или tg://
                got = base_func.link_getter(line)
                if got:
                    link.append(got)
            print(f"[AB DEBUG] link={link[:5]}... (всего {len(link)})")
            print(f"[AB DEBUG] link_count={len(link)}")
            nums = msg.text.split()[1:]
            print(f"[AB DEBUG] nums={nums!r}")
            nums_list = []
            links_list = []
            for num in nums:
                if '-' in num:
                    num_spl = num.split('-')
                    nums_list += [n - 1 for n in range(int(num_spl[0]), int(num_spl[1]) + 1)]
                else:
                    nums_list.append(int(num)-1)
            links_list += [l for n, l in enumerate(link, 0) if n in nums_list]
            link = links_list

        if not link:
            err = await msg.reply(tricks['errors']['something_went_wrong'])
            return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['small_timeout']))

        text = f'Заразить{" "+pathogens_to_use+" " if pathogens_to_use else " "}@{link}'

        if list_infect:
            link_list = link
            link = link[-1]
            await redis.set(f'epidemic_userbot_infect_stop:{me.id}', 0)
            if link_list[:-1] != []:
                for lnk in link_list[:-1]:
                    infect_is_stop = await redis.get(f'epidemic_userbot_infect_stop:{me.id}')

                    if infect_is_stop and int(infect_is_stop) == 1:
                        err = await msg.reply(tricks['errors']['infect_list_stop'])
                        await redis.set(f'epidemic_userbot_infect_stop:{me.id}', 0)
                        return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['medium_timeout']))

                    msg_infect = await msg_to.reply(f'Заразить @{lnk}')
                    exp = 0
                    async with session() as ses:
                        user = await Repo.get_user(ses, lnk)
                        if user:
                            get_victim = await Repo.get_victim(ses, me.id, user[0].id)
                            if get_victim:
                                exp = get_victim[0].victim_bio_resource_earn

                    await redis.lpush(f'epidemic_userbot_victim:{me.id}:{lnk}', f'{msg_infect.id}:{exp}')
                    await redis.expire(f'epidemic_userbot_victim:{me.id}:{lnk}', 6)
                    await asyncio.sleep(tricks['config']['list_infect_delay'])
            text = f'Заразить @{link}'
            quote = True
            msg_to = msg.reply_to_message

        exp = 0
        async with session() as ses:
            user = await Repo.get_user(ses, link)
            if user:
                get_victim = await Repo.get_victim(ses, me.id, user[0].id)
                if get_victim:
                    exp = get_victim[0].victim_bio_resource_earn

        # Проверяем исключения
        from core.utils.db_api.repo import ExceptionsRepo
        if link and str(link).isdigit():
            async with session() as ses:
                is_exc = await ExceptionsRepo.is_exception(ses, me.id, int(link))
            if is_exc:
                err = await msg.reply(f"🚫 <a href=\"tg://openmessage?user_id={link}\">{link}</a> в исключениях. Пропускаю.")
                return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['medium_timeout']))

        msg_infect = await msg_to.reply(text)
        await redis.lpush(f'epidemic_userbot_victim:{me.id}:{link}', f'{msg_infect.id}:{exp}')
        await redis.expire(f'epidemic_userbot_victim:{me.id}:{link}', 6)
        if not list_infect: await msg.delete()

    # Buy vaccine
    if msg.text.lower() == f'{prefix}х':
        await msg.reply(tricks['triggers']['buy_vaccine'])
        await msg.delete()

    # Get small info about lab (ала, ал, амл, алаб)
    if msg.text.lower() in [f'{prefix}ла', f'{prefix}л', f'{prefix}мл', f'{prefix}лаб']:
        lab_receive = await redis.hget(f'epidemic_userbot:{me.id}', 'lab_receive_progress')
        if lab_receive and int(lab_receive):
            err = await msg.reply(tricks['errors']['lab_receive_in_progress'])
            return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['small_timeout']))
        await redis.hset(f'epidemic_userbot:{me.id}', 'lab_receive_progress', 1)

        lab = await respond_func.get_lab(app, me)

        if not lab:
            err = await msg.reply(tricks['errors']['something_went_wrong'])
            await redis.hset(f'epidemic_userbot:{me.id}', 'lab_receive_progress', 0)
            return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['medium_timeout']))
        await redis.hset(f'epidemic_userbot:{me.id}', 'lab_receive_progress', 0)

        msg_lab = await msg.reply('<blockquote>' + '\n'.join(lab) + '</blockquote>')
        asyncio.create_task(respond_func.delete_msg([msg_lab, msg], tricks['config']['medium_timeout']))

    # Trusted
    if (
        msg.from_user.id == me.id and (
            msg.reply_to_message and re.fullmatch(r'(-|\+)дов', msg.text, re.IGNORECASE)
            or
            re.fullmatch(r'(-|\+)дов\s{1,3}' + trg.re_link_sup, msg.text, re.IGNORECASE)
        )
    ):
        trusted_name = False
        trust_id = base_func.link_getter(msg.text)

        if msg.reply_to_message and not trust_id:
            trust_id = msg.reply_to_message.from_user.id
            trusted_name = msg.reply_to_message.from_user.full_name
        else:
            try:
                trusted_entity = await app.get_users(trust_id)
            except PeerIdInvalid:
                err = await msg.reply(tricks['errors']['user_not_found'])
                return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['medium_timeout']))
            except FloodWait as err:
                err = await msg.reply(tricks['errors']['flood_wait'].format(err.value / 60))
                return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['medium_timeout']))
            trusted_name = trusted_entity.full_name
            trust_id = trusted_entity.id

        async with session() as ses:
            is_trusted = (await ses.execute(
                select(UserbotTrustedUsers).where(UserbotTrustedUsers.user_id == me.id, UserbotTrustedUsers.trusted_user_id == trust_id)
                )).all()

        trusted_mention = base_func.entity_create(trust_id, trusted_name)

        if '+' in msg.text and is_trusted:
            err = await msg.reply(tricks['errors']['already_trusted'].format(trusted_mention))
            return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['small_timeout']))
        elif '-' in msg.text and not is_trusted:
            err = await msg.reply(tricks['errors']['trusted_not_exist'].format(trusted_mention))
            return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['small_timeout']))

        if '+' in msg.text:
            async with session() as ses:
                await ses.execute(insert(UserbotTrustedUsers).values(user_id=me.id, trusted_user_id=trust_id))
            await redis.rpush(f'epidemic_userbot_trusted:{me.id}', trust_id)
            text = tricks['game_texts']['add_trusted'].format(trusted_mention)
            if me.id == trust_id:
                text = tricks['game_texts']['add_trusted_self'].format(trusted_mention)
        else:
            async with session() as ses:
                await ses.execute(
                    delete(UserbotTrustedUsers).where(UserbotTrustedUsers.user_id == me.id, UserbotTrustedUsers.trusted_user_id == trust_id)
                )
            await redis.lrem(f'epidemic_userbot_trusted:{me.id}', 1, str(trust_id))
            text = tricks['game_texts']['remove_trusted'].format(trusted_mention)
            if me.id == trust_id:
                text = tricks['game_texts']['remove_trusted_self'].format(trusted_mention)

        await msg.edit(text)

    # check victim (оп, о, с) — работает с ЛЮБЫМ реплаем, КРОМЕ списков
    if (
        re.fullmatch('(' + re.escape(prefix) + r'|)(оп|о|с|чк)\s' + trg.re_link_sup, msg.text, re.IGNORECASE)
        or
        re.fullmatch('(' + re.escape(prefix) + r'|)(оп|о|с|чк)', msg.text, re.IGNORECASE) and msg.reply_to_message and (
            not msg.reply_to_message.text or
            msg.reply_to_message.text.splitlines()[0] not in tricks['game_texts']['notexec_allow_list']
        )
    ):
        victim_id = base_func.link_getter(msg.text)
        victim = victim_name = victim_mention = None

        if (
            msg.reply_to_message and
            msg.reply_to_message.text and
            msg.reply_to_message.text.lower().startswith(tricks['game_texts']['sec_serv']) and
            len(msg.reply_to_message.entities) >= 2
        ):
            # Берём ВТОРОГО игрока (организатора) — entities[1]
            try:
                url = msg.reply_to_message.entities[1].url
                if url:
                    victim_id = base_func.link_getter(url)
            except:
                pass
        elif (
            msg.reply_to_message and
            msg.reply_to_message.text and
            re.findall(r'🦠 .+ подвер[гла]{1,3} заражению', msg.reply_to_message.text.splitlines()[0], re.IGNORECASE) and
            len(msg.reply_to_message.entities) >= 2
        ):
            try:
                url = msg.reply_to_message.entities[1].url
                if url:
                    victim_id = base_func.link_getter(url)
            except:
                pass
        elif (
            msg.reply_to_message and
            msg.reply_to_message.text and
            '🪬 Иммунитет объекта' in msg.reply_to_message.text and
            msg.reply_to_message.entities and len(msg.reply_to_message.entities) == 1
        ):
            try:
                url = msg.reply_to_message.entities[0].url
                if url:
                    victim_id = base_func.link_getter(url)
            except:
                pass
        elif (
            msg.reply_to_message and
            msg.reply_to_message.text and
            '🕵️‍♂️ Служба безопасности' in msg.reply_to_message.text and
            'Иммунитет объекта' in msg.reply_to_message.text and
            msg.reply_to_message.entities and len(msg.reply_to_message.entities) >= 1
        ):
            try:
                url = msg.reply_to_message.entities[0].url
                if url:
                    victim_id = base_func.link_getter(url)
            except:
                pass
        elif (
            msg.reply_to_message and
            msg.reply_to_message.text and
            'Иммунитет' in msg.reply_to_message.text and
            'оказался сильнее' in msg.reply_to_message.text and
            msg.reply_to_message.entities and len(msg.reply_to_message.entities) >= 1
        ):
            try:
                url = msg.reply_to_message.entities[0].url
                if url:
                    victim_id = base_func.link_getter(url)
            except:
                pass
        elif msg.reply_to_message and msg.reply_to_message.from_user:
            victim_id = msg.reply_to_message.from_user.id
            victim_name = msg.reply_to_message.from_user.full_name
        elif msg.reply_to_message and msg.reply_to_message.entities:
            for entity in msg.reply_to_message.entities:
                if hasattr(entity, 'url') and entity.url and 'user_id=' in entity.url:
                    victim_id = int(entity.url.split('user_id=')[1])
                    break

        if not victim_id:
            err = await msg.reply(tricks['errors']['user_not_found'])
            return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['medium_timeout']))

        if not str(victim_id).isdigit():
            try:
                entity = await app.get_users(victim_id)
            except PeerIdInvalid:
                err = await msg.reply(tricks['errors']['user_not_found'])
                return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['medium_timeout']))
            except FloodWait as err:
                err = await msg.reply(tricks['errors']['flood_wait'].format(err.value / 60))
                return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['medium_timeout']))
            except Exception as e:
                logger.error(e)
            victim_id = entity.id
            victim_name = entity.full_name

        async with session() as ses:
            victim = await Repo.get_victim(ses, me.id, victim_id)
            victim_user = await Repo.get_user(ses, victim_id)
            if victim and not victim_name:
                victim_name = victim_user[0].full_name
                victim_id = victim[0].victim_id

        if victim_name:
            victim_mention = base_func.entity_create(victim_id, victim_name)

        if victim:
            text = tricks['game_texts']['check_victim_infected'].format(
                victim_mention, intcomma(victim[0].victim_bio_resource_earn), victim_id
            )
        else:
            text = tricks['game_texts']['check_victim_new'].format(victim_id)
            if victim_mention:
                text = tricks['game_texts']['check_victim_new_entity'].format(victim_mention, victim_id)

        now = int(time.time())
        async with session() as ses:
            kd_record = await Repo.get_victim_kd(ses, me.id, victim_id)

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
                text += kd_str

        from .random_commands import generate_random_code, save_random_command
        code = generate_random_code(5)
        await save_random_command(redis, me.id, code, 'infect_one', {'victim_id': victim_id})
        text += f"\n\n/{code}"

        sended_msg = await msg.reply(text)
        asyncio.create_task(respond_func.delete_msg([sended_msg, msg], tricks['config']['smal_plus_timeout']))

    # notexec (азз, ас)
    if msg.text.lower() in [f'{prefix}зз', f'{prefix}с', f'{prefix}чк'] and msg.reply_to_message and msg.reply_to_message.text:

        title = msg.reply_to_message.text.splitlines()[0]

        if title not in tricks['game_texts']['notexec_allow_list']:
            return

        biotop_chat = tricks['game_texts']['biotop_chat']
        biotop = tricks['game_texts']['biotop']
        my_victims = tricks['game_texts']['my_victims']

        victims_list = []
        for titles in tricks['game_texts']['notexec_allow_list']:
            if title == titles:
                victims_list.append('<b>' + titles.replace('🔬', '📖') + '</b>\n')
                break
        num = 0

        victim_ids_for_infect = []

        async with session() as ses:
            # Безопасно получаем HTML-текст
            try:
                html_text = msg.reply_to_message.text.html
            except AttributeError:
                # text уже строка
                html_text = msg.reply_to_message.text or ""
            
            for r in html_text.splitlines():
                # ===== УНИВЕРСАЛЬНЫЙ ПАРСИНГ =====
                victim_id = None
                victim_name = None
                
                # 1. Формат "1. @826461867 | 10485075" (файл)
                file_match = re.search(r'\d+\.\s*@(\d{6,16})\s*\|\s*(\d+)', r)
                if file_match:
                    victim_id = file_match.group(1)
                    victim_name = victim_id
                else:
                    # 2. user_id=123 (старый формат)
                    user_id_match = re.search(r'user_id=(\d{4,16})', r)
                    if user_id_match:
                        victim_id = user_id_match.group(1)
                        name_match = re.search(r'user_id=\d{4,16}[\">]*([^<\n]+)', r)
                        victim_name = name_match.group(1).strip() if name_match else str(victim_id)
                    else:
                        # 3. @123456789 (числовой username)
                        at_id_match = re.search(r'@(\d{6,16})', r)
                        if at_id_match:
                            victim_id = at_id_match.group(1)
                            victim_name = victim_id
                        else:
                            # 4. @username (текстовый)
                            at_username_match = re.search(r'@([a-zA-Z0-9_]{5,32})', r)
                            if at_username_match and not at_username_match.group(1).isdigit():
                                try:
                                    entity = await app.get_users(at_username_match.group(1))
                                    victim_id = entity.id
                                    victim_name = entity.full_name
                                except:
                                    victim_id = None
                            else:
                                # 5. Просто ID (6-16 цифр)
                                simple_id_match = re.search(r'(?:^|\s|\d+\.\s)(\d{6,16})(?:\s|\||$)', r)
                                if simple_id_match:
                                    victim_id = simple_id_match.group(1)
                                    victim_name = victim_id
                
                if not victim_id:
                    continue
                
                # Проверяем, что ID — число
                if not str(victim_id).isdigit():
                    continue
                
                # Проверяем длину ID (6-16 цифр)
                if len(str(victim_id)) < 6 or len(str(victim_id)) > 16:
                    continue
                
                id = victim_id
                name = victim_name or str(victim_id)
                num += 1
                # Парсим опыт — универсально
                exp = 0
                if title == biotop or title == biotop_chat:
                    # Формат 1: | 10485,1k опыта
                    exp_match = re.search(r'\|\s*([\d,\.]+)(k|к|M|м|K|К)?\s*опыт', r)
                    if exp_match:
                        exp_value = exp_match.group(1).replace(',', '.')
                        try:
                            exp = float(exp_value)
                            suffix = exp_match.group(2)
                            if suffix and suffix.lower() in ['k', 'к']:
                                exp *= 1000
                            elif suffix and suffix.lower() in ['m', 'м']:
                                exp *= 1000000
                            exp = int(exp)
                        except:
                            exp = 0
                    else:
                        # Формат 2: | 10485075 (просто число)
                        simple_exp = re.search(r'\|\s*(\d{1,16})\s*$', r)
                        if simple_exp:
                            try:
                                exp = int(simple_exp.group(1))
                            except:
                                exp = 0
                        else:
                            # Формат 3: | 10485 опыт (старый)
                            old_match = re.search(r'\|\s*([\d,]{1,64})\s*опыт', r)
                            if old_match:
                                try:
                                    exp = int(old_match.group(1).replace(',', ''))
                                except:
                                    exp = 0
                elif title == my_victims:
                    exp = int(re.search(r'\| (\+[,\d]{1,64}) \|', r).group(1).replace(',', ''))
                victim = await Repo.get_victim(ses, me.id, id)
                victim_user = await Repo.get_user(ses, id)

                # Проверяем исключения
                from core.utils.db_api.repo import ExceptionsRepo
                is_exc = await ExceptionsRepo.is_exception(ses, me.id, int(id))

                # Пропускаем себя и исключённых
                if int(id) == me.id or is_exc:
                        continue

                victim_ids_for_infect.append(int(id))

                if victim:
                        mention = base_func.entity_create(id, victim_user[0].full_name)
                        mention_nostyle = mention
                        plus_exp = int(exp*0.10)-victim[0].victim_bio_resource_earn

                        now = int(time.time())
                        kd_record = await Repo.get_victim_kd(ses, me.id, int(id))

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

                        mention = (f'<b>{mention}</b>{kd_str}' if plus_exp>0 else f'<i>{mention}</i>{kd_str}')
                        plus_exp_nostyle = (f'+{intcomma(plus_exp)} 🧬' if plus_exp>0 else f'{intcomma(plus_exp)} ☁️')
                        if plus_exp == 0:
                            plus_exp_nostyle = f'{intcomma(plus_exp)} 💭'
                        if plus_exp == 0:
                            plus_exp = f'<b>{intcomma(plus_exp)}</b> 💭'
                        else:
                            plus_exp = (f'<b>+{intcomma(plus_exp)}</b> 🧬' if plus_exp>0 else f'<i>{intcomma(plus_exp)}</i> ☁️')
                        text = (
                            f'{num}. {mention_nostyle if title == my_victims else mention} '
                            f'{plus_exp_nostyle if title == my_victims else plus_exp}'
                        )
                else:
                    mention = base_func.entity_create(id, name)
                    get_exp = (1 if int(exp*0.10) <= 0 else intcomma(int(exp*0.10)))
                    text = f'{num}. {mention} {f"+<b>{get_exp}</b>" if title == my_victims else f"+{get_exp}"} ✨'
                victims_list.append(text)

        from .random_commands import generate_random_code, save_random_command
        code = generate_random_code(5)
        await save_random_command(redis, me.id, code, 'infect_all', {'victims': victim_ids_for_infect})

        # Если больше 50 жертв — отправляем ФАЙЛОМ
        if len(victim_ids_for_infect) > 50:
            # Создаём файл с ID
            file_content = "\n".join([str(vid) for vid in victim_ids_for_infect])
            file_path = f"/tmp/victims_{me.id}_{code}.txt"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(file_content)
            
            # Отправляем файл
            from pyrogram.types import InputMediaDocument
            try:
                sent_file = await msg.reply_document(
                    document=file_path,
                    caption=f"🦠 <b>Список жертв ({len(victim_ids_for_infect)})</b>\n\nНапиши <code>/{code}</code> для заражения",
                    parse_mode="HTML"
                )
                import os
                os.remove(file_path)
                print(f"[FILE] Отправил файл с {len(victim_ids_for_infect)} ID")
            except Exception as e:
                print(f"[FILE ERROR] {e}")
            
            # Отправляем только список жертв (без кода)
            send_msg = await msg.reply_to_message.reply('\n'.join(victims_list) + f"\n\n<i>Код для заражения в файле выше</i>")
        else:
            victims_list.append(f"\n/{code}")
            send_msg = await msg.reply_to_message.reply('\n'.join(victims_list))
        asyncio.create_task(respond_func.delete_msg([send_msg, msg], tricks['config']['huge_timeout']))

    # change prifix
    if msg.from_user.id == me.id and re.fullmatch(r'\.(преф|префикс) .+', msg.text, re.IGNORECASE):
        pref = msg.text.split()[1]
        mention = base_func.entity_create(me.id, me.full_name)

        if len(pref) >= 2:
            err = await msg.reply(tricks['errors']['prefix_too_long'])
            return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['small_timeout']))

        async with session() as ses:
            await Repo.change_prefix(ses, me.id, pref)
            await redis.hset(f'epidemic_userbot:{me.id}', 'prefix', pref)

        send_msg = await msg.reply(tricks['game_texts']['change_prefix'].format(mention, pref))
        asyncio.create_task(respond_func.delete_msg([send_msg, msg], tricks['config']['medium_timeout']))

    # calculator skiils level up
    if (
        msg.from_user.id == me.id and
        re.fullmatch(r'\.к (%(skills)s \d{1,64}|\d{1,64} %(skills)s) \d{1,64}' % {'skills': trg.re_skills}, msg.text, re.IGNORECASE)
    ):
        parts = msg.text.split()
        if parts[1].isdigit():
            from_lvl, skill, to_lvl = int(parts[1]), parts[2], int(parts[3])
        else:
            skill, from_lvl, to_lvl = parts[1], int(parts[2]), int(parts[3])

        if from_lvl > to_lvl or from_lvl == to_lvl or from_lvl == 0 or to_lvl == 0:
            err = await msg.reply(tricks['errors']['invalid_skills_level'])
            return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['small_timeout']))
        if to_lvl - from_lvl > 999999:
            err = await msg.reply(tricks['errors']['skills_level_too_high'])
            return asyncio.create_task(respond_func.delete_msg([err, msg], tricks['config']['small_timeout']))

        text = base_func.skills_calc(skill, from_lvl, to_lvl)

        sended_msg = await msg.reply(text)
        asyncio.create_task(respond_func.delete_msg([sended_msg, msg], tricks['config']['huge_timeout']))
