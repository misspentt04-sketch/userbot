import asyncio
import os
import sys

from pyrogram import Client

# Добавляем путь к проекту
sys.path.insert(0, os.path.abspath('.'))

from core.utils.db_api import UserUserBot, UserUserBotData
from core.settings import settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.sql import insert, select
from datetime import datetime, timedelta


async def add_userbot_to_db(owner_id: int, api_id: int, api_hash: str, phone: str):
    """Добавляет юзербота в БД"""
    engine = create_async_engine(url=settings.db_url.get_secret_value(), echo=False)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    
    async with sessionmaker() as session:
        async with session.begin():
            # Проверяем, есть ли уже такой юзербот
            existing = await session.execute(
                select(UserUserBot).where(UserUserBot.owner_id == owner_id)
            )
            existing = existing.scalars().first()
            
            if existing:
                print(f"⚠️ Юзербот для {owner_id} уже есть в БД (id={existing.id})")
                # Обновляем данные
                await session.execute(
                    select(UserUserBotData).where(UserUserBotData.ub_id == existing.id)
                )
                return existing.id
            
            # Создаём нового
            result = await session.execute(
                insert(UserUserBot).values(owner_id=owner_id, status=True)
            )
            ub_id = result.lastrowid
            
            await session.execute(
                insert(UserUserBotData).values(
                    ub_id=ub_id,
                    api_id=api_id,
                    api_hash=api_hash,
                    phone_number=phone,
                    time_expire=datetime.utcnow() + timedelta(days=365)
                )
            )
    
    await engine.dispose()
    print(f"✅ Юзербот добавлен в БД (ub_id={ub_id})")
    return ub_id


async def create_session(owner_id: int, api_id: int, api_hash: str, phone: str):
    """Создаёт сессию Pyrogram"""
    session_path = f"core/sessions/{owner_id}"
    
    # Создаём папку
    os.makedirs("core/sessions", exist_ok=True)
    
    # Проверяем, есть ли уже сессия
    if os.path.exists(f"{session_path}.session"):
        answer = input(f"⚠️ Сессия {session_path}.session уже существует. Пересоздать? (y/n): ")
        if answer.lower() != 'y':
            print("❌ Отменено")
            return False
        os.remove(f"{session_path}.session")
    
    app = Client(
        session_path,
        api_id=api_id,
        api_hash=api_hash,
        phone_number=phone
    )
    
    try:
        print()
        print("🔄 Подключаемся к Telegram...")
        print("   (Введите код из Telegram)")
        print()
        
        await app.start()
        me = await app.get_me()
        
        print()
        print(f"✅ Сессия создана!")
        print(f"   Имя: {me.first_name}")
        print(f"   Username: @{me.username}")
        print(f"   ID: {me.id}")
        
        await app.stop()
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


async def main():
    print("=" * 50)
    print("🎮 ДОБАВЛЕНИЕ ЮЗЕРБОТА")
    print("=" * 50)
    print()
    
    # 1. ID владельца
    owner_id_input = input("👤 Введите ID владельца (например, 7972320837): ").strip()
    if not owner_id_input.isdigit():
        print("❌ ID должен быть числом!")
        return
    owner_id = int(owner_id_input)
    
    # 2. API ID
    api_id_input = input("🔑 Введите API ID (с my.telegram.org): ").strip()
    if not api_id_input.isdigit():
        print("❌ API ID должен быть числом!")
        return
    api_id = int(api_id_input)
    
    # 3. API HASH
    api_hash = input("🔑 Введите API HASH: ").strip()
    if not api_hash:
        print("❌ API HASH не может быть пустым!")
        return
    
    # 4. Номер телефона
    phone = input("📱 Введите номер телефона (например, +79123456789): ").strip()
    if not phone.startswith('+'):
        print("❌ Номер должен начинаться с +")
        return
    
    print()
    print("=" * 50)
    print("📋 Проверьте данные:")
    print(f"   ID владельца: {owner_id}")
    print(f"   API ID: {api_id}")
    print(f"   API HASH: {api_hash[:8]}...")
    print(f"   Телефон: {phone}")
    print("=" * 50)
    
    confirm = input("Всё верно? (y/n): ")
    if confirm.lower() != 'y':
        print("❌ Отменено")
        return
    
    # Создаём сессию
    success = await create_session(owner_id, api_id, api_hash, phone)
    
    if success:
        # Добавляем в БД
        print()
        print("💾 Добавляем в БД...")
        try:
            await add_userbot_to_db(owner_id, api_id, api_hash, phone)
        except Exception as e:
            print(f"⚠️ Ошибка БД: {e}")
        
        print()
        print("=" * 50)
        print("✅ ГОТОВО!")
        print("=" * 50)
        print(f"📁 Сессия: core/sessions/{owner_id}.session")
        print(f"🚀 Запустите: python app.py")
    else:
        print()
        print("❌ Не удалось создать сессию")


if __name__ == "__main__":
    asyncio.run(main())
