from pydantic import BaseModel


class PublishRequest(BaseModel):
    message: str


class PublishResponse(BaseModel):
    channel: str
    subscriber_count: int
