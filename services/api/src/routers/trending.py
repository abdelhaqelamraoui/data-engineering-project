import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from config import Config
from schemas.trending import HistoryPoint, TermHistoryResponse, TrendingItem, TrendingResponse
from services.hbase_client import HBaseRestClient

router = APIRouter()

BUCKET_PATTERN = re.compile(r"^\d{12}$")


def get_hbase(request: Request) -> HBaseRestClient:
    return request.app.state.hbase


def get_config(request: Request) -> Config:
    return request.app.state.config


@router.get("/trending", response_model=TrendingResponse)
async def get_trending(
    at: str | None = Query(default=None, description="yyyyMMddHHmm bucket; omit for the latest"),
    limit: int = Query(default=20, ge=1, le=100),
    hbase: HBaseRestClient = Depends(get_hbase),
    config: Config = Depends(get_config),
) -> TrendingResponse:
    bucket = at
    if bucket is not None and not BUCKET_PATTERN.match(bucket):
        raise HTTPException(400, "`at` must be formatted as yyyyMMddHHmm")

    if bucket is None:
        pointer = await hbase.get_row(config.table_meta, "latest_bucket")
        bucket = pointer.get("meta:value") if pointer else None

    if bucket is None:
        return TrendingResponse(bucket=None, items=[])

    rows = await hbase.scan_bucket_prefix(config.table_trends, bucket, limit=limit)
    items = [
        TrendingItem(
            rank=int(cells["trends:rank"]),
            term=cells["trends:term"],
            count=int(cells["trends:count"]),
            score=float(cells["trends:score"]),
            distinct_authors=int(cells.get("trends:distinct_authors", 0)),
        )
        for _, cells in rows
    ]
    items.sort(key=lambda item: item.rank)
    return TrendingResponse(bucket=bucket, items=items[:limit])


@router.get("/trending/history", response_model=TermHistoryResponse)
async def get_term_history(
    term: str = Query(..., min_length=1),
    limit: int = Query(default=288, ge=1, le=2000),
    hbase: HBaseRestClient = Depends(get_hbase),
    config: Config = Depends(get_config),
) -> TermHistoryResponse:
    rows = await hbase.scan_term_prefix(config.table_term_history, term, limit=limit)
    points = [
        HistoryPoint(
            bucket=key.split("#", 1)[1],
            count=int(cells["history:count"]),
            score=float(cells["history:score"]),
        )
        for key, cells in rows
    ]
    points.sort(key=lambda point: point.bucket)
    return TermHistoryResponse(term=term, points=points)
