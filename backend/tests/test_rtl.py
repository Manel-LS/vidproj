"""Right-to-left text: Arabic must stay shaped, joined and in reading order.

Arabic letters change form depending on their neighbours, so the naive way to apply
letter spacing — draw one glyph at a time — produces disconnected letters in reverse
order. These tests pin the behaviour that prevents that regression, and check that
the chosen font actually carries Arabic glyphs.
"""
from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from app.domain.enums import FontFamily, TextAnimation, TextBackground
from app.domain.plan import TextOverlay
from app.infrastructure.imaging.fonts import load_font, resolve_font_path
from app.infrastructure.imaging.text_renderer import is_rtl, render_text_layer

ARABIC = "قصة سيدنا يونس عليه السلام"
HEBREW = "שלום עולם"


@pytest.mark.parametrize(
    "text, expected",
    [
        (ARABIC, True),
        (HEBREW, True),
        ("Fini la course aux fournitures", False),
        ("MaktabtiMarket 2026", False),
        ("", False),
        ("Maktabti مكتبتي", True),  # mixed content counts as RTL
    ],
)
def test_rtl_detection(text: str, expected: bool):
    assert is_rtl(text) is expected


def test_arabic_ignores_letter_spacing():
    """Spacing must not widen Arabic — that would mean it was split per glyph."""
    font = load_font(FontFamily.SANS_BOLD, 800, 64, arabic=True)
    draw = ImageDraw.Draw(Image.new("RGBA", (8, 8)))

    from app.infrastructure.imaging.text_renderer import _text_width

    unspaced = _text_width(draw, ARABIC, font, 0.0)
    spaced = _text_width(draw, ARABIC, font, 12.0)
    assert unspaced == pytest.approx(spaced), "letter spacing leaked into a joining script"

    # The same call on Latin text must still honour spacing.
    latin_font = load_font(FontFamily.SANS_BOLD, 800, 64)
    assert _text_width(draw, "Hello", latin_font, 12.0) > _text_width(draw, "Hello", latin_font, 0.0)


def test_arabic_is_shaped_not_drawn_glyph_by_glyph():
    """A shaped run is narrower than the sum of its isolated glyphs.

    Joined Arabic letters overlap and lose their isolated tails, so if the render
    ever reverted to per-glyph drawing this width would jump.
    """
    font = load_font(FontFamily.SANS_BOLD, 800, 64, arabic=True)
    draw = ImageDraw.Draw(Image.new("RGBA", (8, 8)))

    shaped = draw.textlength(ARABIC, font=font, direction="rtl")
    isolated = sum(draw.textlength(char, font=font) for char in ARABIC)
    assert shaped < isolated * 0.95, "text does not appear to be shaped"


@pytest.mark.parametrize("family", list(FontFamily))
def test_every_family_resolves_to_a_font_with_arabic_glyphs(family: FontFamily):
    """A style whose font lacks Arabic would render every letter as an empty box."""
    fonttools = pytest.importorskip("fontTools.ttLib")

    path = resolve_font_path(family, True, True)
    font = fonttools.TTFont(str(path), fontNumber=0, lazy=True)
    try:
        cmap = font.getBestCmap()
    finally:
        font.close()

    # alef, beh, teh marbuta, lam, meem, yeh
    for code in (0x0627, 0x0628, 0x0629, 0x0644, 0x0645, 0x064A):
        assert code in cmap, f"{path.name} has no glyph for U+{code:04X} ({family.value})"


@pytest.mark.parametrize("animation", list(TextAnimation))
def test_arabic_renders_for_every_text_animation(tmp_path, animation: TextAnimation):
    overlay = TextOverlay(
        role="title",
        content=ARABIC,
        animation=animation,
        font_size=72,
        background=TextBackground.PILL,
        letter_spacing=6.0,  # would corrupt the script if it were applied
    )
    asset = render_text_layer(
        overlay,
        frame_size=(1080, 1920),
        output_dir=tmp_path,
        layer_id=f"ar-{animation.value}",
        fps=30,
        scene_duration=3.0,
    )
    assert asset.path.is_file()

    # The first frame of a fade or a pop is transparent by design, so the resting
    # frame is what must carry the text.
    resting = asset.path
    if asset.is_sequence:
        resting = asset.path.parent / f"{asset.frame_count - 1:05d}.png"

    with Image.open(resting) as image:
        assert image.mode == "RGBA"
        # Something was actually drawn: a blank layer means missing glyphs.
        assert image.getbbox() is not None, "the Arabic layer came out empty"


def test_arabic_layer_has_visible_ink(tmp_path):
    """Guards against tofu: empty boxes still paint, so check the ink covers area."""
    overlay = TextOverlay(role="title", content=ARABIC, font_size=80, animation=TextAnimation.NONE)
    asset = render_text_layer(
        overlay,
        frame_size=(1080, 1920),
        output_dir=tmp_path,
        layer_id="ink",
        fps=30,
        scene_duration=2.0,
    )
    with Image.open(asset.path) as image:
        alpha = image.getchannel("A")
        opaque = sum(1 for value in alpha.getdata() if value > 40)
    assert opaque > 2000, "too little ink — the glyphs are probably missing"


# ---------------------------------------------------------------- download ---


@pytest.mark.parametrize(
    "filename, expected_ascii",
    [
        ("قصة-سيدنا-يونس.mp4", "video.mp4"),
        ("视频.mp4", "video.mp4"),
        ("Créer une vidéo.mp4", "Creer une video.mp4"),
        ("New school supplies.mp4", "New school supplies.mp4"),
        ("", "video.mp4"),
    ],
)
def test_content_disposition_survives_non_ascii_names(filename: str, expected_ascii: str):
    """HTTP headers are Latin-1: a non-ASCII project name must not break the download."""
    from app.api.v1.routes.renders import content_disposition

    value = content_disposition(filename)
    value.encode("latin-1")  # exactly what the ASGI server does; must not raise

    assert f'filename="{expected_ascii}"' in value
    assert "filename*=UTF-8''" in value


def test_arabic_named_project_can_be_downloaded(client, auth, sample_images):
    """End to end: an Arabic project name must not 500 on export."""
    project = client.post(
        "/api/v1/projects",
        json={"name": "قصة سيدنا يونس عليه السلام", "style": "luxury", "target_duration": 3},
        headers=auth["headers"],
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/media",
        files=sample_images(1),
        headers=auth["headers"],
    )
    job = client.post(f"/api/v1/projects/{project['id']}/render", headers=auth["headers"]).json()

    import time

    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/render-jobs/{job['id']}", headers=auth["headers"]).json()
        if job["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.5)
    assert job["status"] == "completed", job

    download = client.get(
        f"/api/v1/render-jobs/{job['id']}/download", headers=auth["headers"]
    )
    assert download.status_code == 200
    assert b"ftyp" in download.content[:32]
    assert "filename*=UTF-8''" in download.headers["content-disposition"]
