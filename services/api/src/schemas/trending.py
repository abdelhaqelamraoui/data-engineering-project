from pydantic import BaseModel


class TrendingItem(BaseModel):
    rank: int
    term: str
    count: int
    score: float
    distinct_authors: int


class TrendingResponse(BaseModel):
    bucket: str | None
    items: list[TrendingItem]


class HistoryPoint(BaseModel):
    bucket: str
    count: int
    score: float


class TermHistoryResponse(BaseModel):
    term: str
    points: list[HistoryPoint]
