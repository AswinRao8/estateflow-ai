from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db_session

# Usage: def my_endpoint(settings: SettingsDep): ...
SettingsDep = Annotated[Settings, Depends(get_settings)]

# Usage: async def my_handler(db: DbSessionDep): ...
# Services must call await db.commit() explicitly after write operations.
DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
