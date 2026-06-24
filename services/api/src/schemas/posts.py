from pydantic import BaseModel


class PostItem(BaseModel):
    id: str
    did: str
    text: str
    timestamp: str | None = None
    lang: str | None = None
    received_at: str


class RecentPostsResponse(BaseModel):
    items: list[PostItem]
