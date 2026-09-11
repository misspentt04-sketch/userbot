from pyrogram import Client, filters
from dispyro import Dispatcher, Router

from typing import List, Tuple

from core.data.tricks.tricks import tricks
from core.data import triggers as trg
from core.filters.is_infect import infect

from .main_skills import main_skills
from .helpers import helper
from .infect_manager import self_victim_infect, auto_write_infect, stop_infect
from .zarlist import zarlist_command, zarlist_plus_command
from .random_commands import random_command_handler, vaccine_all_command
from .exceptions import exceptions_list_command, exception_add_command


async def setup_handlers(apps_dp: Tuple[List[Client], List[Dispatcher]]) -> None:
    for dp in apps_dp[1]:
        router = Router(name=f"router_{id(dp)}")

        router.message.register(main_skills)
        router.message.register(helper)
        router.message.register(self_victim_infect, filters.me & infect)
        router.message.register(auto_write_infect, filters.user(tricks['game']['bot_id']))
        router.message.register(stop_infect, filters.regex('б стоп'))
        router.message.register(zarlist_command)
        router.message.register(zarlist_plus_command)
        router.message.register(random_command_handler)
        router.message.register(exceptions_list_command)
        router.message.register(exception_add_command)
        router.message.register(vaccine_all_command)

        dp.add_router(router)
