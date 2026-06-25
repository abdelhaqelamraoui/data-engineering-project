"""Brand palette and Slide Master setup.

Colors come straight from the brief: a gold accent, two near-black/black
tones, and a cyan/teal pair. Backgrounds stay white/light throughout -
the dark tones are reserved for text and small accent shapes, not full
slide backgrounds.
"""

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.util import Emu, Pt

GOLD = RGBColor(0xF3, 0xC8, 0x16)
BLACK = RGBColor(0x00, 0x00, 0x00)
CHARCOAL = RGBColor(0x23, 0x1F, 0x20)
CYAN = RGBColor(0x0A, 0xF0, 0xF4)
TEAL = RGBColor(0x02, 0x98, 0x8D)

WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT_BG = RGBColor(0xF7, 0xF8, 0xF9)
MUTED_TEXT = RGBColor(0x6B, 0x72, 0x80)
BORDER = RGBColor(0xE3, 0xE6, 0xEB)

FONT_TITLE = "Calibri"
FONT_BODY = "Calibri"

SLIDE_W = Emu(12192000)  # 16:9, 13.33in
SLIDE_H = Emu(6858000)  # 7.5in


def set_theme_colors(prs) -> None:
    """Rewrite the theme's clrScheme so PowerPoint's Design > Colors and
    every "theme color" swatch in the deck matches the brand palette.

    The theme part is loaded by python-pptx as an opaque blob (no parsed
    oxml element of its own), so this parses it with lxml directly and
    writes the modified bytes back onto the part.
    """
    from lxml import etree

    master = prs.slide_masters[0]
    theme_part = master.part.part_related_by(RT.THEME)
    theme_el = etree.fromstring(theme_part.blob)
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    clr_scheme = theme_el.find(".//a:clrScheme", ns)

    mapping = {
        "dk1": "231F20",
        "lt1": "FFFFFF",
        "dk2": "000000",
        "lt2": "F7F8F9",
        "accent1": "02988D",
        "accent2": "F3C816",
        "accent3": "0AF0F4",
        "accent4": "231F20",
        "accent5": "000000",
        "accent6": "02988D",
        "hlink": "02988D",
        "folHlink": "231F20",
    }
    for child in list(clr_scheme):
        tag = child.tag.split("}")[1]
        if tag not in mapping:
            continue
        for sub in list(child):
            child.remove(sub)
        color_tag = "{http://schemas.openxmlformats.org/drawingml/2006/main}srgbClr"
        el = child.makeelement(color_tag, {"val": mapping[tag]})
        child.append(el)

    theme_part._blob = etree.tostring(theme_el, xml_declaration=True, encoding="UTF-8", standalone=True)


def _add_text(slide, left, top, width, height, text, *, size=18, color=CHARCOAL,
               bold=False, align=PP_ALIGN.LEFT, font=FONT_BODY, italic=False,
               line_spacing=None):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    lines = text.split("\n")
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if line_spacing:
            p.line_spacing = line_spacing
        run = p.add_run()
        run.text = line
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = color
        run.font.name = font
    return box


def _transplant_shapes_to(prs, target_shapes, build_fn) -> None:
    """python-pptx's MasterShapes/LayoutShapes don't expose add_shape() /
    add_textbox() the way a real slide's SlideShapes does - only slides can
    build arbitrary shapes through the high-level API. To put decorative
    shapes on the master/layout anyway (so every slide inherits them), this
    builds them on a slide in a throwaway *separate* Presentation (never
    saved, just discarded once done) and moves the resulting XML elements
    onto the real target. Building in a separate presentation - rather than
    adding then deleting a slide in the real one - sidesteps python-pptx
    having no public "delete slide" API (removing a slide's `<p:sldId>`
    entry alone leaves its part in the package, which then collides with
    the next slide's auto-assigned partname).
    """
    from pptx import Presentation as _Presentation

    scratch_prs = _Presentation()
    scratch_slide = scratch_prs.slides.add_slide(scratch_prs.slide_layouts[6])

    build_fn(scratch_slide)

    sp_tree = target_shapes.element
    for shape in list(scratch_slide.shapes):
        el = shape._element
        el.getparent().remove(el)
        sp_tree.append(el)


def setup_master(prs) -> None:
    """Add brand elements directly on the Slide Master: white background,
    a thin top accent bar, a footer rule, and a page-number placeholder.
    Every slide built from this master inherits these automatically.
    """
    master = prs.slide_masters[0]

    master.background.fill.solid()
    master.background.fill.fore_color.rgb = WHITE

    def build(slide):
        # top accent bar (gold + teal + cyan triptych, thin, not a full dark band)
        bar_h = Emu(91440)  # 0.1in
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, bar_h)
        bar.fill.solid()
        bar.fill.fore_color.rgb = TEAL
        bar.line.fill.background()
        bar.shadow.inherit = False

        seg_w = Emu(int(SLIDE_W * 0.18))
        gold_seg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, seg_w, bar_h)
        gold_seg.fill.solid()
        gold_seg.fill.fore_color.rgb = GOLD
        gold_seg.line.fill.background()
        gold_seg.shadow.inherit = False

        cyan_seg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, seg_w, 0, Emu(45720), bar_h)
        cyan_seg.fill.solid()
        cyan_seg.fill.fore_color.rgb = CYAN
        cyan_seg.line.fill.background()
        cyan_seg.shadow.inherit = False

        # footer rule
        foot_y = SLIDE_H - Emu(274320)
        rule = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Emu(457200), foot_y, SLIDE_W - Emu(914400), Emu(9525)
        )
        rule.fill.solid()
        rule.fill.fore_color.rgb = BORDER
        rule.line.fill.background()
        rule.shadow.inherit = False

        _add_text(
            slide, Emu(457200), foot_y + Emu(27432), Emu(6000000), Emu(190500),
            "Trending Topics Detection Pipeline", size=10, color=MUTED_TEXT,
        )

    _transplant_shapes_to(prs, master.shapes, build)


def add_page_number(slide, number: int) -> None:
    foot_y = SLIDE_H - Emu(274320)
    _add_text(
        slide, SLIDE_W - Emu(914400), foot_y + Emu(27432), Emu(457200), Emu(190500),
        str(number), size=10, color=MUTED_TEXT, align=PP_ALIGN.RIGHT,
    )
