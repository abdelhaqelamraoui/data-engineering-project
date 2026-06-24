from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import Config
from routers.posts import router as posts_router
from routers.trending import router as trending_router
from services.hbase_client import HBaseRestClient
from services.live_posts import LivePostsFeed


_config = Config.from_env()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.config = _config
    app.state.hbase = HBaseRestClient(_config.hbase_rest_url)
    app.state.live_feed = LivePostsFeed(
        _config.kafka_bootstrap_servers, _config.kafka_topic, _config.live_posts_buffer_size
    )
    app.state.live_feed.start()
    yield
    await app.state.live_feed.stop()
    await app.state.hbase.aclose()


app = FastAPI(title="Trending Topics API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_config.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(trending_router)
app.include_router(posts_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
