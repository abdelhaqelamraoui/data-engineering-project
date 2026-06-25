"""Builds the project presentation: Trending_Topics_Pipeline.pptx

Run with:
    python3 build.py
(needs python-pptx and pillow - see ../presentation/README.md)
"""

import os

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Pt

import diagrams
import slides
import theme
from theme import BORDER, CHARCOAL, GOLD, MUTED_TEXT, TEAL, WHITE, _add_text

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
OUTPUT = os.path.join(os.path.dirname(__file__), "Trending_Topics_Pipeline.pptx")

page = 0


def next_page():
    global page
    page += 1
    return page


def build():
    prs = Presentation()
    prs.slide_width = theme.SLIDE_W
    prs.slide_height = theme.SLIDE_H
    theme.set_theme_colors(prs)
    theme.setup_master(prs)

    # 1. Title
    slides.title_slide(
        prs,
        title="Real-Time Trending Topics Detection Pipeline",
        subtitle="A Data Engineering Pipeline on the Bluesky Firehose",
        authors=["[Author Name 1]", "[Author Name 2]"],
        module_name="[Module Name] — Data Engineering",
        date_text="June 2026",
        page_no=next_page(),
    )

    # 2. Agenda
    slides.agenda_slide(prs, next_page(), [
        "Context & Problem",
        "Objectives & Key Decisions",
        "System Architecture",
        "Real-Time Pipeline & Cleaning",
        "Storage, Serving & Dashboard",
        "Search & Exploration",
        "Results, Engineering Rigor & Conclusion",
    ])

    # 3. Introduction
    s = slides.content_slide(prs, next_page(), "Introduction", "The Problem We Solve")
    slides.bullets(s, slides.MARGIN, slides.CONTENT_TOP + Emu(550000), slides.CONTENT_W, [
        "Social platforms produce a continuous, unbounded stream of public posts",
        "“Frequent” is not “trending”: common words are stable, not interesting",
        "We need acceleration: a term's rise versus its own recent baseline, not raw counts",
        "Spam, bots, and noisy/clock-skewed clients must not be mistaken for real spikes",
        "All of this must happen continuously and at low latency, not as a nightly batch job",
    ], size=16)

    # 4. Objectives & key decisions
    s = slides.content_slide(prs, next_page(), "Introduction", "Objectives & Key Decisions")
    slides.bullets(s, slides.MARGIN, slides.CONTENT_TOP + Emu(550000), slides.CONTENT_W, [
        "End-to-end pipeline: ingest → clean → score → store → serve → visualize",
        "Source: Bluesky Jetstream firehose — public, real-time, no authentication",
        "Trend score: ratio to the term's own trailing baseline (acceleration, not frequency)",
        "Window: 5-minute sliding window, 1-minute slide, 2-minute watermark",
        "HBase for low-latency serving; Elasticsearch/Kibana added for full-text exploration",
        "Every component is its own Docker service, cleanly separated, configured by env files",
    ], size=16)

    # 5. Section: Architecture
    slides.section_break_slide(prs, next_page(), "01", "Architecture", "How the system is put together")

    # 6. Global architecture diagram
    s = slides.content_slide(prs, next_page(), "Architecture", "Global System Architecture", title_size=28)
    diagrams.architecture_diagram(s, slides.MARGIN, Emu(1850000), slides.CONTENT_W, Emu(1700000))
    slides.bullets(s, slides.MARGIN, Emu(4650000), slides.CONTENT_W, [
        "One Kafka topic, two independent downstream readers — neither blocks the other",
        "Trending pipeline (teal): scores and ranks terms, served by HBase + the API",
        "Search branch (cyan): indexes raw posts for full-text search, additive only",
    ], size=14, gap=Emu(90000))

    # 7. Tech stack
    s = slides.content_slide(prs, next_page(), "Architecture", "Technology Stack")
    tech_items = [
        ("Python", "Producer, Indexer"),
        ("Apache Kafka", "Ingestion & buffering (KRaft)"),
        ("Apache Spark", "Structured Streaming"),
        ("Apache HBase", "Low-latency serving store"),
        ("FastAPI", "REST API"),
        ("Next.js", "Dashboard UI"),
        ("Elasticsearch", "Full-text search index"),
        ("Kibana", "Exploration UI"),
        ("Docker Compose", "9 containers, 1 network"),
    ]
    diagrams.tech_grid(s, slides.MARGIN, Emu(1850000), slides.CONTENT_W, Emu(3200000), tech_items, cols=3)

    # 8. Section: Real-time pipeline
    slides.section_break_slide(prs, next_page(), "02", "Real-Time Pipeline",
                                "Ingestion, cleaning, windowing, and scoring")

    # 9. Ingestion
    s = slides.content_slide(prs, next_page(), "Real-Time Pipeline", "Ingestion: Firehose to Kafka")
    slides.bullets(s, slides.MARGIN, slides.CONTENT_TOP + Emu(550000), slides.CONTENT_W, [
        "Producer opens a WebSocket to the Bluesky Jetstream firehose (no auth required)",
        "Keeps only post-creation events, filtered to English language",
        "Reconnects automatically with exponential backoff, resuming from its last cursor",
        "Publishes each surviving post as a small JSON record to Kafka topic bluesky-posts",
    ], size=16)

    # 10. Cleaning pipeline steps
    s = slides.content_slide(prs, next_page(), "Real-Time Pipeline", "Real-Time Cleaning Pipeline", title_size=27)
    diagrams.cleaning_pipeline_diagram(s, slides.MARGIN, Emu(2050000), slides.CONTENT_W, Emu(1200000))
    diagrams.label(s, slides.MARGIN, Emu(3500000), slides.CONTENT_W, Emu(300000),
                    "One shared, pure-Python module — reused as-is by 3 independent services",
                    size=13, color=TEAL, italic=True, align=PP_ALIGN.CENTER)

    # 11. Cleaning in action
    s = slides.content_slide(prs, next_page(), "Real-Time Pipeline", "Cleaning in Action", title_size=27)
    diagrams.before_after_diagram(
        s, slides.MARGIN, Emu(1900000), slides.CONTENT_W, Emu(1750000),
        raw_text="Just published my research on #DataEngineering \U0001F680 Check it out at "
                 "https://example.com/article cc @johndoe isn't this exciting??",
        cleaned_text="just published my research on check it out at cc isnt this exciting",
        hashtags=["#dataengineering"],
        words=["published", "research", "check", "exciting"],
    )
    diagrams.label(s, slides.MARGIN, Emu(3850000), slides.CONTENT_W, Emu(300000),
                    "Same input → same output on spark-processor, api, and indexer — by construction",
                    size=13, color=TEAL, italic=True, align=PP_ALIGN.CENTER)

    # 12. Windowing & scoring
    s = slides.content_slide(prs, next_page(), "Real-Time Pipeline", "Windowing & Trend Scoring", title_size=27)
    diagrams.window_scoring_diagram(s, slides.MARGIN, Emu(1750000), slides.CONTENT_W, Emu(3500000))

    # 13. Section: storage & serving
    slides.section_break_slide(prs, next_page(), "03", "Storage, Serving & Dashboard",
                                "From ranked terms to a live UI")

    # 14. HBase schema
    s = slides.content_slide(prs, next_page(), "Storage", "HBase Schema")
    diagrams.schema_table(s, slides.MARGIN, Emu(1850000), slides.CONTENT_W, Emu(1800000), [
        ("trends", "bucket#rank", "rank, term, count, score, distinct_authors", "spark-processor", "api"),
        ("term_history", "term#bucket", "count, score", "spark-processor", "api"),
        ("term_baseline", "t#term", "avg", "spark-processor", "spark-processor"),
        ("pipeline_meta", "latest_bucket", "value, updated_at", "spark-processor", "api"),
    ])
    diagrams.label(s, slides.MARGIN, Emu(3850000), slides.CONTENT_W, Emu(300000),
                    "TTL on trends/term_history enforces 24h retention automatically — no cleanup job",
                    size=13, color=MUTED_TEXT, italic=True, align=PP_ALIGN.LEFT)

    # 15. API & Dashboard (two screenshots)
    s = slides.content_slide(prs, next_page(), "Serving", "REST API & Dashboard", title_size=27)
    _side_by_side_images(
        s, [
            (os.path.join(ASSETS, "dashboard-trending.png"), "Trending Now"),
            (os.path.join(ASSETS, "dashboard-live.png"), "Live Posts"),
        ],
    )

    # 16. Section: search & exploration
    slides.section_break_slide(prs, next_page(), "04", "Search & Exploration",
                                "Elasticsearch + Kibana, additive to the trending path")

    # 17. Kibana
    s = slides.image_slide(prs, next_page(), "Search & Exploration", "Kibana: Full-Text Exploration",
                            os.path.join(ASSETS, "kibana-discover.png"),
                            caption="Full-text search, faceting on hashtags/words/lang, post-volume histogram")

    # 18. Section: results
    slides.section_break_slide(prs, next_page(), "05", "Engineering Rigor & Results",
                                "What broke, what we learned, what we shipped")

    # 19. Real issues found & fixed
    s = slides.content_slide(prs, next_page(), "Engineering Rigor", "Real Issues Found & Fixed", title_size=27)
    _issue_cards(s, [
        ("Watermark poisoning", "A clock-skewed client posted a timestamp ~6.5h in the future, "
         "permanently advancing Spark's watermark and silently dropping all later events.",
         "Fixed: reject events whose timestamp is implausibly far in the future."),
        ("HBase pagination bug", "HBase REST's scanner caps cells per page, not rows — a 5-column "
         "row could be split across pages and returned incomplete.",
         "Fixed: merge cells by row key across pages before truncating to the limit."),
        ("Sequential bottleneck", "One HTTP call per candidate term made large windows (5000+ terms) "
         "fall behind their 30s trigger under real load.",
         "Fixed: batched multiget/multi-row PUT — verified at 5241 candidates, zero restarts."),
    ])

    # 20. Project implementation
    s = slides.content_slide(prs, next_page(), "Results", "Project Implementation")
    _stat_row(s, [
        ("9", "Dockerized services"),
        ("3", "Independent Kafka consumers"),
        ("4", "Real bugs found in production-like testing"),
        ("100%", "Configured via .env files"),
    ])
    slides.bullets(s, slides.MARGIN, Emu(3050000), slides.CONTENT_W, [
        "Every service: its own Dockerfile, its own .env, clean separation of concerns",
        "Shared preprocessing module vendored at build time into 3 services from one source file",
        "Verified against the real, live Bluesky firehose throughout — not just unit tests",
    ], size=15)

    # 21. Conclusion
    s = slides.content_slide(prs, next_page(), "Conclusion", "Conclusion")
    slides.bullets(s, slides.MARGIN, slides.CONTENT_TOP + Emu(550000), slides.CONTENT_W, [
        "Built a complete, real-time trending-detection pipeline on a live public data source",
        "Acceleration-based scoring (ratio to baseline) surfaces real spikes, not just frequent words",
        "Clean separation of services, shared rules vendored from one source, fully containerized",
        "Hardened by real engineering issues found and fixed under real load, not just in theory",
        "Extensible: the same architecture pattern (independent Kafka consumers) added Kibana search "
        "without touching the existing trending path",
    ], size=16)

    # 22. Thank you
    slides.closing_slide(prs, next_page(), title="Thank You", subtitle="Questions?")

    prs.save(OUTPUT)
    print(f"Saved {OUTPUT} ({page} slides)")


def _side_by_side_images(slide, items):
    from PIL import Image as _PILImage

    gap = Emu(300000)
    col_w = (slides.CONTENT_W - gap) // 2
    y = Emu(1850000)
    max_h = Emu(3700000)
    cx = slides.MARGIN
    for path, caption in items:
        with _PILImage.open(path) as im:
            px_w, px_h = im.size
        ratio = min(col_w / px_w, max_h / px_h)
        w = Emu(int(px_w * ratio))
        h = Emu(int(px_h * ratio))
        ix = cx + (col_w - w) // 2
        frame = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, ix - Emu(18000), y - Emu(18000),
                                         w + Emu(36000), h + Emu(36000))
        frame.fill.solid()
        frame.fill.fore_color.rgb = WHITE
        frame.line.color.rgb = BORDER
        frame.line.width = Pt(1)
        frame.shadow.inherit = False
        slide.shapes.add_picture(path, ix, y, width=w, height=h)
        _add_text(slide, cx, y + h + Emu(80000), col_w, Emu(300000), caption,
                   size=13, bold=True, color=TEAL, align=PP_ALIGN.CENTER)
        cx += col_w + gap


def _issue_cards(slide, items):
    gap = Emu(220000)
    card_w = (slides.CONTENT_W - 2 * gap) // 3
    card_h = Emu(3600000)
    y = Emu(1850000)
    cx = slides.MARGIN
    for title, problem, fix in items:
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, y, card_w, card_h)
        card.adjustments[0] = 0.05
        card.fill.solid()
        card.fill.fore_color.rgb = WHITE
        card.line.color.rgb = BORDER
        card.line.width = Pt(1)
        card.shadow.inherit = False

        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, cx, y, card_w, Emu(70000))
        bar.fill.solid()
        bar.fill.fore_color.rgb = GOLD
        bar.line.fill.background()
        bar.shadow.inherit = False

        pad = Emu(180000)
        _add_text(slide, cx + pad, y + Emu(220000), card_w - 2 * pad, Emu(500000),
                   title, size=15, bold=True, color=CHARCOAL, line_spacing=1.05)
        _add_text(slide, cx + pad, y + Emu(820000), card_w - 2 * pad, Emu(1450000),
                   problem, size=11.5, color=MUTED_TEXT, line_spacing=1.2)
        _add_text(slide, cx + pad, y + card_h - Emu(950000), card_w - 2 * pad, Emu(900000),
                   fix, size=11.5, color=TEAL, bold=True, line_spacing=1.2)
        cx += card_w + gap


def _stat_row(slide, items):
    gap = Emu(220000)
    n = len(items)
    card_w = (slides.CONTENT_W - gap * (n - 1)) // n
    card_h = Emu(1000000)
    y = Emu(1850000)
    cx = slides.MARGIN
    for number, lbl in items:
        slides.stat_card(slide, cx, y, card_w, card_h, number, lbl)
        cx += card_w + gap


if __name__ == "__main__":
    build()
