from fastapi import APIRouter, Depends, Query, Request

from schemas.posts import PostItem, RecentPostsResponse
from services.live_posts import LivePostsFeed

router = APIRouter()


def get_feed(request: Request) -> LivePostsFeed:
    return request.app.state.live_feed


@router.get("/posts/recent", response_model=RecentPostsResponse)
async def get_recent_posts(
    limit: int = Query(default=50, ge=1, le=200),
    feed: LivePostsFeed = Depends(get_feed),
) -> RecentPostsResponse:
    items = [PostItem(**post) for post in feed.recent(limit)]
    return RecentPostsResponse(items=items)
