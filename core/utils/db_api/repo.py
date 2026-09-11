from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy.sql import select, insert, delete, update

from core.utils.db_api import UserbotVictims, UserbotUserSettings, Victims, User, VictimKD

from datetime import datetime, timedelta


class Repo:

    async def get_user(session: AsyncSession, link: [int, str]):
        async with session.begin():
            user = (await session.execute(
                select(User).where(User.id == link)
            )).scalars().all()
            if not user:
                user = (await session.execute(
                    select(User).where(User.username == link)
                )).scalars().all()
            if user:
                return user
            else:
                return None

    async def get_victim(session: AsyncSession, infecter_id: int, victimer_id: int):
        async with session.begin():
            return (await session.execute(
                select(Victims).where(Victims.victims_owner_id == infecter_id, Victims.victim_id == victimer_id)
            )).scalars().all()

    async def get_all_victims(session: AsyncSession, infecter_id: int):
        async with session.begin():
            return (await session.execute(
                select(Victims).where(Victims.victims_owner_id == infecter_id).order_by(Victims.victim_bio_resource_earn.desc())
            )).scalars().all()

    async def change_prefix(session: AsyncSession, id: int, prefix: str):
        async with session.begin():
            await session.execute(update(UserbotUserSettings).where(UserbotUserSettings.user_id==id).values(prefix=prefix))

    async def save_victim_kd(session: AsyncSession, owner_id: int, victim_id: int):
        """Сохраняет КД жертвы на 2 часа"""
        import time
        kd_expire = int(time.time()) + 2 * 60 * 60
        
        async with session.begin():
            await session.execute(
                delete(VictimKD).where(
                    VictimKD.owner_id == owner_id,
                    VictimKD.victim_id == victim_id
                )
            )
            await session.execute(
                insert(VictimKD).values(
                    owner_id=owner_id,
                    victim_id=victim_id,
                    kd_expire=kd_expire
                )
            )

    async def get_victim_kd(session: AsyncSession, owner_id: int, victim_id: int):
        """Получает КД жертвы"""
        async with session.begin():
            result = await session.execute(
                select(VictimKD).where(
                    VictimKD.owner_id == owner_id,
                    VictimKD.victim_id == victim_id
                )
            )
            return result.scalars().first()


from core.utils.db_api import UserbotExceptions
from sqlalchemy.sql import select, delete, insert


class ExceptionsRepo:
    
    @staticmethod
    async def add_exception(session: AsyncSession, owner_id: int, victim_id: int, victim_name: str = None):
        """Добавляет жертву в исключения"""
        async with session.begin():
            # Проверяем, есть ли уже
            existing = (await session.execute(
                select(UserbotExceptions).where(
                    UserbotExceptions.owner_id == owner_id,
                    UserbotExceptions.victim_id == victim_id
                )
            )).scalars().first()
            
            if existing:
                return False  # Уже есть
            
            await session.execute(
                insert(UserbotExceptions).values(
                    owner_id=owner_id,
                    victim_id=victim_id,
                    victim_name=victim_name
                )
            )
            return True
    
    @staticmethod
    async def remove_exception(session: AsyncSession, owner_id: int, victim_id: int):
        """Удаляет жертву из исключений"""
        async with session.begin():
            await session.execute(
                delete(UserbotExceptions).where(
                    UserbotExceptions.owner_id == owner_id,
                    UserbotExceptions.victim_id == victim_id
                )
            )
    
    @staticmethod
    async def get_all_exceptions(session: AsyncSession, owner_id: int):
        """Получает все исключения"""
        async with session.begin():
            return (await session.execute(
                select(UserbotExceptions).where(
                    UserbotExceptions.owner_id == owner_id
                ).order_by(UserbotExceptions.id.desc())
            )).scalars().all()
    
    @staticmethod
    async def is_exception(session: AsyncSession, owner_id: int, victim_id: int) -> bool:
        """Проверяет, в исключениях ли жертва"""
        async with session.begin():
            result = (await session.execute(
                select(UserbotExceptions).where(
                    UserbotExceptions.owner_id == owner_id,
                    UserbotExceptions.victim_id == victim_id
                )
            )).scalars().first()
            return result is not None
