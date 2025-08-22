
from typing import Protocol, List, Any
from datetime import datetime

class Event(dict):
    pass

class TimeBlock(dict):
    pass

class CalendarProvider(Protocol):
    async def list_events(self, user: Any, start: datetime, end: datetime) -> List[Event]: ...
    async def create_block(self, user: Any, block: TimeBlock) -> str: ...
    async def update_block(self, user: Any, block_id: str, patch: dict) -> None: ...

class MsGraphProvider:
    async def list_events(self, user, start, end):
        # TODO: implement Graph calls
        return []
    async def create_block(self, user, block):
        # TODO: implement Graph calls
        return "external-id"
    async def update_block(self, user, block_id, patch):
        # TODO: implement Graph calls
        return None
