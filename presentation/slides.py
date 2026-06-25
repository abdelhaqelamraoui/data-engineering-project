"""Reusable slide-building blocks on top of the branded Slide Master.

Every function here returns the slide it built so the caller can keep
adding content (diagrams, images, extra shapes) on top.
"""

from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

from theme import (
    BORDER,
    CHARCOAL,
    CYAN,
    FONT_BODY,
    FONT_TITLE,
    GOLD,
    LIGHT_BG,
    MUTED_TEXT,
    SLIDE_H,
    SLIDE_W,
    TEAL,
    WHITE,
    _add_text,
    add_page_number,
)

MARGIN = Emu(548640)  # 0.6in
CONTENT_TOP = Emu(1120000)
CONTENT_BOTTOM = SLIDE_H - Emu(420000)
CONTENT_W = SLIDE_W - 2 * MARGIN


def new_slide(prs):
    return prs.slides.add_slide(prs.slide_masters[0].slide_layouts[6])


def _no_line(shape):
    shape.line.fill.background()
    shape.shadow.inherit = False


def _rect(slide, x, y, w, h, color):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    _no_line(shp)
    return shp


def kicker_and_title(slide, kicker: str, title: str, *, title_size=30):
    """Small caps colored label + big slide title, in the standard spot."""
    _add_text(
        slide, MARGIN, Emu(620000), CONTENT_W, Emu(260000),
        kicker.upper(), size=13, bold=True, color=TEAL, font=FONT_BODY,
    )
    _add_text(
        slide, MARGIN, Emu(860000), CONTENT_W, Emu(560000),
        title, size=title_size, bold=True, color=CHARCOAL, font=FONT_TITLE,
    )
    underline = _rect(slide, MARGIN, Emu(1430000), Emu(900000), Emu(36000), GOLD)
    return underline


def content_slide(prs, page_no, kicker, title, *, title_size=30):
    slide = new_slide(prs)
    kicker_and_title(slide, kicker, title, title_size=title_size)
    add_page_number(slide, page_no)
    return slide


def bullets(slide, x, y, w, items, *, size=16, gap=Emu(140000), color=CHARCOAL,
            bold_lead=False, line_h=Emu(360000), marker_color=TEAL):
    """A clean list - colored square marker + text, no native PowerPoint
    bullet glyphs (keeps full control over spacing and avoids overflow
    surprises from inherited bullet formatting).
    """
    cy = y
    marker_w = Emu(70000)
    text_x = x + marker_w + Emu(120000)
    text_w = w - marker_w - Emu(120000)
    for item in items:
        marker = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, cy + Emu(70000), marker_w, marker_w)
        marker.fill.solid()
        marker.fill.fore_color.rgb = marker_color
        _no_line(marker)
        box = _add_text(slide, text_x, cy, text_w, line_h, item, size=size, color=color, line_spacing=1.08)
        # measure-free auto height: estimate lines needed for wrapped text
        approx_chars_per_line = max(1, int(text_w / Emu(60000)))
        n_lines = max(1, -(-len(item) // approx_chars_per_line))
        cy += Emu(int(size * 12700 * 1.35)) * n_lines + gap
    return cy


def stat_card(slide, x, y, w, h, number: str, label: str, *, number_color=TEAL):
    card = _rect(slide, x, y, w, h, WHITE)
    card.line.color.rgb = BORDER
    card.line.width = Pt(1)
    card.shadow.inherit = False
    _add_text(slide, x + Emu(120000), y + Emu(100000), w - Emu(240000), Emu(500000),
               number, size=30, bold=True, color=number_color, align=PP_ALIGN.LEFT)
    _add_text(slide, x + Emu(120000), y + h - Emu(420000), w - Emu(240000), Emu(380000),
               label, size=12, color=MUTED_TEXT, align=PP_ALIGN.LEFT, line_spacing=1.05)
    return card


def title_slide(prs, *, title, subtitle, authors, module_name, date_text, page_no):
    slide = new_slide(prs)

    # big soft accent shape, bottom-right corner - decorative, not a dark bg
    deco = slide.shapes.add_shape(MSO_SHAPE.OVAL, SLIDE_W - Emu(2300000), SLIDE_H - Emu(1700000),
                                    Emu(2600000), Emu(2600000))
    deco.fill.solid()
    deco.fill.fore_color.rgb = LIGHT_BG
    _no_line(deco)
    deco2 = slide.shapes.add_shape(MSO_SHAPE.OVAL, SLIDE_W - Emu(1500000), SLIDE_H - Emu(2200000),
                                     Emu(1200000), Emu(1200000))
    deco2.fill.solid()
    deco2.fill.fore_color.rgb = CYAN
    _no_line(deco2)

    # university logo placeholder
    logo_w, logo_h = Emu(1900000), Emu(900000)
    logo = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, MARGIN, Emu(500000), logo_w, logo_h)
    logo.fill.solid()
    logo.fill.fore_color.rgb = WHITE
    logo.line.color.rgb = BORDER
    logo.line.width = Pt(1.25)
    logo.shadow.inherit = False
    _add_text(slide, MARGIN, Emu(500000) + (logo_h - Emu(280000)) // 2, logo_w, Emu(280000),
               "[ University Logo ]", size=11, color=MUTED_TEXT, align=PP_ALIGN.CENTER)

    _add_text(slide, MARGIN + logo_w + Emu(300000), Emu(500000) + (logo_h - Emu(280000)) // 2,
               Emu(6000000), Emu(280000),
               module_name, size=14, bold=True, color=TEAL, align=PP_ALIGN.LEFT)

    _add_text(slide, MARGIN, Emu(2350000), Emu(9500000), Emu(1300000),
               title, size=40, bold=True, color=CHARCOAL, font=FONT_TITLE, line_spacing=1.05)
    bar = _rect(slide, MARGIN, Emu(3550000), Emu(1100000), Emu(45000), GOLD)

    _add_text(slide, MARGIN, Emu(3700000), Emu(9500000), Emu(600000),
               subtitle, size=18, color=CHARCOAL, italic=True)

    # authors + date/module row near the bottom
    row_y = SLIDE_H - Emu(1550000)
    label_w = Emu(1400000)
    col_w = Emu(3400000)
    _add_text(slide, MARGIN, row_y, label_w, Emu(300000), "AUTHORS", size=11, bold=True, color=MUTED_TEXT)
    _add_text(slide, MARGIN, row_y + Emu(320000), col_w, Emu(700000),
               "\n".join(authors), size=15, color=CHARCOAL, line_spacing=1.2)

    _add_text(slide, MARGIN + col_w + Emu(400000), row_y, label_w, Emu(300000),
               "DATE", size=11, bold=True, color=MUTED_TEXT)
    _add_text(slide, MARGIN + col_w + Emu(400000), row_y + Emu(320000), col_w, Emu(400000),
               date_text, size=15, color=CHARCOAL)

    add_page_number(slide, page_no)
    return slide


def agenda_slide(prs, page_no, items: list[str]):
    slide = new_slide(prs)
    kicker_and_title(slide, "Agenda", "Plan of the Presentation", title_size=30)

    y = CONTENT_TOP + Emu(550000)
    row_h = Emu(560000)
    for i, item in enumerate(items, start=1):
        ny = y + Emu(int((i - 1) * row_h))
        num_box = slide.shapes.add_shape(MSO_SHAPE.OVAL, MARGIN, ny, Emu(420000), Emu(420000))
        num_box.fill.solid()
        num_box.fill.fore_color.rgb = TEAL if i % 2 else GOLD
        _no_line(num_box)
        tf = num_box.text_frame
        tf.word_wrap = False
        tf.margin_left = 0
        tf.margin_right = 0
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = str(i)
        run.font.size = Pt(16)
        run.font.bold = True
        run.font.color.rgb = WHITE if i % 2 else CHARCOAL
        num_box.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE

        _add_text(slide, MARGIN + Emu(560000), ny + Emu(70000), CONTENT_W - Emu(560000), Emu(360000),
                   item, size=17, color=CHARCOAL, bold=True)

    add_page_number(slide, page_no)
    return slide


def section_break_slide(prs, page_no, number: str, title: str, subtitle: str = ""):
    """A lightweight divider between major parts - bold but still a light
    background, per the brief's "avoid dark backgrounds" instruction.
    """
    slide = new_slide(prs)
    band = _rect(slide, 0, Emu(2400000), SLIDE_W, Emu(2058000), LIGHT_BG)

    _add_text(slide, MARGIN, Emu(2520000), Emu(1700000), Emu(1400000),
               number, size=64, bold=True, color=TEAL, font=FONT_TITLE)
    _add_text(slide, MARGIN + Emu(1750000), Emu(2620000), CONTENT_W - Emu(1750000), Emu(700000),
               title, size=32, bold=True, color=CHARCOAL, font=FONT_TITLE)
    if subtitle:
        _add_text(slide, MARGIN + Emu(1750000), Emu(3260000), CONTENT_W - Emu(1750000), Emu(700000),
                   subtitle, size=15, color=MUTED_TEXT, line_spacing=1.2)

    accent = _rect(slide, MARGIN + Emu(1750000), Emu(2480000), Emu(700000), Emu(30000), GOLD)
    add_page_number(slide, page_no)
    return slide


def image_slide(prs, page_no, kicker, title, image_path, *, caption=None, img_width=None):
    slide = content_slide(prs, page_no, kicker, title)
    from PIL import Image as _PILImage

    with _PILImage.open(image_path) as im:
        px_w, px_h = im.size
    max_w = img_width or CONTENT_W
    max_h = CONTENT_BOTTOM - Emu(1750000) - (Emu(300000) if caption else Emu(0))
    ratio = min(max_w / px_w, max_h / px_h)
    w = Emu(int(px_w * ratio))
    h = Emu(int(px_h * ratio))
    x = MARGIN + (CONTENT_W - w) // 2
    y = Emu(1750000)

    frame = _rect(slide, x - Emu(18000), y - Emu(18000), w + Emu(36000), h + Emu(36000), WHITE)
    frame.line.color.rgb = BORDER
    frame.line.width = Pt(1)
    slide.shapes.add_picture(image_path, x, y, width=w, height=h)

    if caption:
        _add_text(slide, MARGIN, y + h + Emu(60000), CONTENT_W, Emu(300000),
                   caption, size=12, italic=True, color=MUTED_TEXT, align=PP_ALIGN.CENTER)
    return slide


def closing_slide(prs, page_no, *, title, subtitle):
    slide = new_slide(prs)
    deco = slide.shapes.add_shape(MSO_SHAPE.OVAL, Emu(-900000), Emu(150000), Emu(2600000), Emu(2600000))
    deco.fill.solid()
    deco.fill.fore_color.rgb = LIGHT_BG
    _no_line(deco)
    deco2 = slide.shapes.add_shape(MSO_SHAPE.OVAL, SLIDE_W - Emu(1700000), SLIDE_H - Emu(1700000),
                                     Emu(2600000), Emu(2600000))
    deco2.fill.solid()
    deco2.fill.fore_color.rgb = LIGHT_BG
    _no_line(deco2)

    _add_text(slide, MARGIN, Emu(2700000), CONTENT_W, Emu(900000),
               title, size=44, bold=True, color=CHARCOAL, align=PP_ALIGN.CENTER, font=FONT_TITLE)
    bar_w = Emu(900000)
    _rect(slide, (SLIDE_W - bar_w) // 2, Emu(3550000), bar_w, Emu(40000), GOLD)
    _add_text(slide, MARGIN, Emu(3700000), CONTENT_W, Emu(500000),
               subtitle, size=17, color=TEAL, align=PP_ALIGN.CENTER)

    add_page_number(slide, page_no)
    return slide
