from typing import Dict, Optional
from pyrogram import Client

# Глобальный словарь клиентов: {owner_id: Client}
ACTIVE_CLIENTS: Dict[int, Client] = {}


def set_clients(clients: Dict[int, Client]):
    global ACTIVE_CLIENTS
    ACTIVE_CLIENTS.clear()
    ACTIVE_CLIENTS.update(clients)
    print(f"[USERBOT_MANAGER] Загружено {len(ACTIVE_CLIENTS)} клиентов")


def get_client(owner_id: int) -> Optional[Client]:
    return ACTIVE_CLIENTS.get(owner_id)


def get_all_clients() -> Dict[int, Client]:
    return ACTIVE_CLIENTS.copy()


def get_trusted_clients(trusted_ids: list) -> Dict[int, Client]:
    result = {}
    for tid in trusted_ids:
        try:
            tid_int = int(tid)
            if tid_int in ACTIVE_CLIENTS:
                result[tid_int] = ACTIVE_CLIENTS[tid_int]
        except:
            continue
    return result
