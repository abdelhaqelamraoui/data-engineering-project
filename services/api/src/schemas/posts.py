from pydantic import BaseModel


class PostItem(BaseModel):
    id: str
    did: str
    text: str
    timestamp: str | None = None
    lang: str | None = None
    received_at: str
    # "after" preprocessing - computed once when the post enters the buffer,
    # see services/live_posts.py and shared/preprocessing/
    cleaned_text: str = ""
    hashtags: list[str] = []
    words: list[str] = []


class RecentPostsResponse(BaseModel):
    items: list[PostItem]
