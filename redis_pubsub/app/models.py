from pydantic import BaseModel, Field

CHANNEL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"


class PublishRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)


class PublishResponse(BaseModel):
    channel: str
    subscriber_count: int
