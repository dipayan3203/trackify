from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

mongo_client: AsyncIOMotorClient | None = None


async def get_mongo_client(close: bool = False) -> AsyncIOMotorClient | None:
    """Initialize or close the shared MongoDB client."""
    global mongo_client

    if close:
        if mongo_client is not None:
            mongo_client.close()
            mongo_client = None
        return None

    if mongo_client is None:
        mongo_client = AsyncIOMotorClient(settings.MONGO_URI)
        await mongo_client.admin.command("ping")

    return mongo_client


def get_notes_collection():
    """Return the MongoDB collection for job notes."""
    if mongo_client is None:
        raise RuntimeError("MongoDB client has not been initialized")
    return mongo_client.trackify.notes
