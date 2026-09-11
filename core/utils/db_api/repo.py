from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy.sql import select, insert, delete, update

from core.utils.db_api import UserbotVictims, UserbotUserSettings, Victims, User

from datetime import datetime


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
