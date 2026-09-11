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
        return

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

    await msg.reply(text)


async def zarlist_plus_command(app: Client, msg: Message, me: User, session: async_sessionmaker[AsyncSession], redis: Redis):
    """Команда {prefix}зз+ — показывает только выгодных жертв"""
    trusted_ids = await redis.lrange(f'epidemic_userbot_trusted:{me.id}', 0, -1)

    if msg.from_user.id != me.id and str(msg.from_user.id) not in trusted_ids:
        return

    prefix = await redis.hget(f'epidemic_userbot:{me.id}', 'prefix')

    # Работает как: азз+, азз +, а зз+, а зз +, ас+, ас +, а с+, а с +
    if not re.fullmatch(rf'{re.escape(prefix)}\s*(?:зз|с)\s*\+', msg.text, re.IGNORECASE):
        return

    if not msg.reply_to_message:
        err = await msg.reply("📝 Ответьте на список жертв (топ/бiotop/мои жертвы)")
        return

    # ===== ОБРАБОТКА ФАЙЛА =====
    if msg.reply_to_message.document:
        try:
            file_path = await msg.reply_to_message.download()
            with open(file_path, 'r', encoding='utf-8') as f:
                file_text = f.read()
            
            msg.reply_to_message.text = file_text
            import os
            os.remove(file_path)
            print(f"[FILE] Загружен файл из реплая, {len(file_text)} символов")
        except Exception as e:
            print(f"[FILE ERROR] {e}")

    # Безопасно получаем HTML-текст
    try:
        text = msg.reply_to_message.text.html
    except AttributeError:
        text = msg.reply_to_message.text or ""

    if not text:
        err = await msg.reply("📝 Сообщение пустое.")
        return

    # ===== ЗАГРУЖАЕМ ВСЕХ ЖЕРТВ ОДНИМ ЗАПРОСОМ =====
    async with session() as ses:
        all_victims = await Repo.get_all_victims(ses, me.id)
    victims_dict = {v.victim_id: v.victim_bio_resource_earn for v in all_victims}
    
    # Загружаем все КД одним запросом
    async with session() as ses:
        from core.utils.db_api import VictimKD
        from sqlalchemy.sql import select
        result = await ses.execute(
            select(VictimKD).where(VictimKD.owner_id == me.id)
        )
        all_kd = result.scalars().all()
    kd_dict = {k.victim_id: k.kd_expire for k in all_kd}

    victims = []
    for line in text.splitlines():
        # ===== УНИВЕРСАЛЬНЫЙ ПАРСИНГ =====
        victim_id = None
        total_exp = 0
        
        # Формат 1: user_id=123
        user_id_match = re.search(r"user_id=(\d{6,16})", line)
        if user_id_match:
            victim_id = int(user_id_match.group(1))
            exp_match = re.search(r"\|\s*([\d,\.]+)(k|к|M|м|K|К)?\s*опыт", line)
            if exp_match:
                exp_value = exp_match.group(1).replace(",", ".")
                try:
                    total_exp = float(exp_value)
                    suffix = exp_match.group(2)
                    if suffix and suffix.lower() in ["k", "к"]:
                        total_exp *= 1000
                    elif suffix and suffix.lower() in ["m", "м"]:
                        total_exp *= 1000000
                    total_exp = int(total_exp)
                except:
                    total_exp = 0
            else:
                simple = re.search(r"\|\s*([\d,]{1,64})\s*опыт", line)
                if simple:
                    total_exp = int(simple.group(1).replace(",", ""))
        else:
            # Формат 2: "1. @826461867 | 10485075"
            file_match = re.search(r"\d+\.\s*@(\d{6,16})\s*\|\s*(\d+)", line)
            if file_match:
                victim_id = int(file_match.group(1))
                total_exp = int(file_match.group(2))
            else:
                simple_file = re.search(r"@(\d{6,16})\s*\|\s*(\d+)", line)
                if simple_file:
                    victim_id = int(simple_file.group(1))
                    total_exp = int(simple_file.group(2))
                else:
                    at_id = re.search(r"@(\d{6,16})", line)
                    if at_id:
                        victim_id = int(at_id.group(1))
                        total_exp = 0
        
        if not victim_id:
            continue
        
        if len(str(victim_id)) < 6 or len(str(victim_id)) > 16:
            continue
        
        if int(victim_id) == me.id:
            continue

        # Берём из кэша (без запроса к БД)
        current_earn = victims_dict.get(victim_id, 0)
        potential_earn = int(total_exp * 0.10)
        diff = potential_earn - current_earn

        if diff > 0:
            victims.append((victim_id, total_exp, current_earn, potential_earn, diff))

    if not victims:
        err = await msg.reply("📝 Нет выгодных жертв в этом списке.")
        return

    victims.sort(key=lambda x: x[4], reverse=True)

    now = int(time.time())

    # УСКОРЕНО: получаем имена только для топ-10
    victims_list = []
    for i, (vid, total, current, potential, diff) in enumerate(victims[:10], 1):
        # Только ID, без запроса к БД
        mention = base_func.entity_create(vid, str(vid))

        # КД из кэша
        kd_str = ""
        kd_expire = kd_dict.get(vid)
        if kd_expire:
            kd_expire = int(kd_expire)
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

    from .random_commands import generate_random_code, save_random_command
    code = generate_random_code(5)
    victim_ids = [v[0] for v in victims]
    await save_random_command(redis, me.id, code, 'infect_plus', {'victims': victim_ids})

    # Если больше 50 выгодных — отправляем ФАЙЛОМ
    if len(victims) > 50:
        # Создаём файл с ID
        file_content = "\n".join([str(vid) for vid in victim_ids])
        file_path = f"/tmp/victims_plus_{me.id}_{code}.txt"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(file_content)
        
        try:
            # Отправляем файл
            with open(file_path, 'rb') as f:
                await msg.reply_document(
                    document=f,
                    file_name=f"victims_{len(victims)}_{code}.txt",
                    caption=f"🎯 Выгодные жертвы ({len(victims)})\n\nНапиши /{code} для заражения"
                )
            import os
            os.remove(file_path)
            print(f"[FILE] Отправил {len(victims)} ID")
        except Exception as e:
            print(f"[FILE ERROR] {e}")
            err = await msg.reply(f"❌ Ошибка отправки файла: {e}")
        
        # Отправляем первые 10 в сообщении
        top_10 = victims_list[:10]
        await msg.reply_to_message.reply(
            f"🎯 <b>Выгодные жертвы (топ-10 из {len(victims)}):</b>\n\n" + "\n".join(top_10) + f"\n\n<i>Остальные в файле выше. Код: /{code}</i>"
        )
    else:
        # Маленький список — отправляем сообщением
        result = (
            f"🎯 <b>Выгодные жертвы ({len(victims)}):</b>\n\n"
            + "\n".join(victims_list)
        )
        result += f"\n\n/{code}"
        
        await msg.reply(result)
