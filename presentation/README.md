# Presentation

`Trending_Topics_Pipeline.pptx` — generated, not hand-built, from the
scripts in this folder. Editing the generated file directly is fine (it's
a normal .pptx), but to regenerate it after a content change, edit
`build.py` (or `theme.py`/`slides.py`/`diagrams.py` for styling/layout
building blocks) and rerun the build.

## Regenerating

```bash
python3 -m venv .venv && .venv/bin/pip install python-pptx pillow
.venv/bin/python3 build.py
```

Produces `Trending_Topics_Pipeline.pptx` in this folder.

## Layout

- `theme.py` — brand colors, the Slide Master setup (background, accent
  bar, footer, page numbers), and the theme color XML edit.
- `slides.py` — reusable slide types: title, agenda, section break,
  content (kicker + title + bullets), image, closing.
- `diagrams.py` — the native (shape-based, not images) diagrams: global
  architecture, the cleaning pipeline, a before/after example, windowing
  & scoring, the tech-stack grid, and the HBase schema table.
- `build.py` — the actual slide-by-slide content; this is what you edit
  to change wording, add/remove slides, or swap screenshots.
- `assets/` — dashboard/Kibana screenshots, captured from the live
  running stack (`docker compose up`) and lightly cropped to avoid
  showing unpredictable raw-firehose content (profanity, etc.) on slides.

## Before presenting

Fill in the placeholders on the title slide (`build.py`, near the top of
`build()`): university logo, author names, module name, date.
