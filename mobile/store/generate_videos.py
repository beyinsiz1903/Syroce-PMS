"""
Syroce PMS mobile — App Store / Play Store tanıtım (preview) videoları üretici.

Üretilen dosyalar:
  mobile/store/videos/
    ios/<flow>_6_7.mp4          1080x1920  iPhone 6.7" preview (App Store HD spec)
    ios/<flow>_12_9.mp4         1200x1600  iPad Pro 12.9" preview (App Store spec)
    android/<flow>_phone.mp4    1080x1920  Telefon (Play / YouTube 9:16)
    android/<flow>_tablet_10.mp4  1200x1920  10" tablet (5:8 portrait)

Her video 18 saniye uzunluğundadır (App Store'un 15-30 sn aralığında) ve aynı 6
ekran akışını animasyonlu (intro → spotlight gezintisi → CTA) olarak gösterir.
Ekranlar `generate_assets.py` içindeki `screen_*` fonksiyonları ile tek seferde
üretilir; sonra her kare için sadece animasyon katmanı yeniden çizilir, böylece
çıktılar deterministik ve tekrar üretilebilir kalır.

Kullanım:
    cd mobile
    python3 store/generate_videos.py             # tüm 24 video (dark tema)
    python3 store/generate_videos.py --light     # ek olarak light tema da
    python3 store/generate_videos.py --smoke     # tek küçük test videosu

Bağımlılıklar:
    - Pillow (zaten generate_assets.py için gerekli)
    - ffmpeg (libx264) sistemde kurulu olmalı
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from generate_assets import (
    DARK,
    LIGHT,
    PHONE_BASE,
    TABLET_BASE,
    PRIMARY,
    PRIMARY_DEEP,
    SCREENS,
    Theme,
    WHITE,
    font,
    text_size,
)

ROOT = Path(__file__).resolve().parents[1]
VIDEOS = ROOT / "store" / "videos"
(VIDEOS / "ios").mkdir(parents=True, exist_ok=True)
(VIDEOS / "android").mkdir(parents=True, exist_ok=True)

FPS = 30
DURATION_SECONDS = 18
TOTAL_FRAMES = FPS * DURATION_SECONDS

# Faz sınırları (frame indexleri)
INTRO_END = int(FPS * 2.5)              # 0.0 - 2.5 sn  intro animasyonu
SPOTLIGHT_START = int(FPS * 3.0)        # 3.0 sn'den itibaren spotlight bandı
OUTRO_START = int(FPS * 15.5)           # 15.5 sn'den itibaren CTA paneli
SPOTLIGHT_END = OUTRO_START

# Mağaza için video çıkış boyutları. App Store Connect 6.7" iPhone ve 12.9"
# iPad için "App Preview" video boyutlarını kabul eder. Play Store doğrudan
# MP4 yüklemese de aynı dosyalar tanıtım, YouTube ve sosyal medya için kullanılır.
VIDEO_SIZES = {
    ("ios", "6_7"): {"target": (1080, 1920), "kind": "phone"},
    ("ios", "12_9"): {"target": (1200, 1600), "kind": "tablet"},
    ("android", "phone"): {"target": (1080, 1920), "kind": "phone"},
    ("android", "tablet_10"): {"target": (1200, 1920), "kind": "tablet"},
}


# --- Easing yardımcıları ---------------------------------------------------
def _clamp01(v: float) -> float:
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def ease_in_out(t: float) -> float:
    t = _clamp01(t)
    return 0.5 - 0.5 * math.cos(math.pi * t)


def ease_out(t: float) -> float:
    t = _clamp01(t)
    return 1 - (1 - t) * (1 - t)


# --- Çizim yardımcıları ----------------------------------------------------
def draw_text_alpha(canvas: Image.Image, pos, text: str, fnt, color, alpha: float):
    """RGB canvas üzerine alpha'lı metin çizer (alpha=1 ise direkt, daha az ise blend)."""
    if alpha <= 0.005:
        return
    if alpha >= 0.995:
        ImageDraw.Draw(canvas).text(pos, text, fill=color, font=fnt)
        return
    # Sadece metnin bbox'ı kadar küçük katman
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    tw, th = text_size(measure, text, fnt)
    pad = 4
    layer = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((pad, pad), text, fill=(*color, int(255 * alpha)), font=fnt)
    canvas.paste(layer, (pos[0] - pad, pos[1] - pad), layer)


def overlay_rounded_rect(canvas: Image.Image, box, radius: int, color, alpha: float):
    if alpha <= 0.005:
        return
    x0, y0, x1, y1 = [int(v) for v in box]
    if x1 <= x0 or y1 <= y0:
        return
    pad = max(radius, 2)
    lw = x1 - x0 + pad * 2
    lh = y1 - y0 + pad * 2
    layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(
        (pad, pad, pad + (x1 - x0), pad + (y1 - y0)),
        radius=radius,
        fill=(*color, int(255 * alpha)),
    )
    canvas.paste(layer, (x0 - pad, y0 - pad), layer)


def fade_rgba(img: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 0.995:
        return img
    if alpha <= 0.005:
        return Image.new("RGBA", img.size, (0, 0, 0, 0))
    out = img.copy()
    a = out.split()[3].point(lambda v: int(v * alpha))
    out.putalpha(a)
    return out


# --- Statik katmanlar ------------------------------------------------------
def build_background(target_size, theme: Theme) -> Image.Image:
    """Hafif gradientli arka plan — tüm video boyunca sabit kalır."""
    tw, th = target_size
    bg = Image.new("RGB", (tw, th), theme.bg)
    gd = ImageDraw.Draw(bg)
    off = theme.grad_top_offset
    for y in range(th):
        t = y / max(th - 1, 1)
        r = max(0, min(255, int(theme.bg[0] + off[0] * (1 - t))))
        g = max(0, min(255, int(theme.bg[1] + off[1] * (1 - t))))
        b = max(0, min(255, int(theme.bg[2] + off[2] * (1 - t))))
        gd.line([(0, y), (tw, y)], fill=(r, g, b))
    return bg


def wrap_headline(headline: str, fnt, max_w: int) -> list[str]:
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    if text_size(measure, headline, fnt)[0] <= max_w:
        return [headline]
    words = headline.split()
    mid = len(words) // 2
    return [" ".join(words[:mid]), " ".join(words[mid:])]


def build_device_image(screen_base: Image.Image, target_size, kind: str, theme: Theme) -> dict:
    """Cihaz çerçevesi + içine yerleştirilmiş ekran (constant per video)."""
    tw, th = target_size
    title_h = int(th * 0.18)
    device_top = title_h + 110
    device_bottom = th - 80
    device_h = device_bottom - device_top
    aspect = (9 / 19.5) if kind == "phone" else (3 / 4)
    device_w = int(device_h * aspect)
    if device_w > tw - 160:
        device_w = tw - 160
        device_h = int(device_w / aspect)
        device_top = (th - device_h) // 2 + title_h // 2
        device_bottom = device_top + device_h
    device_x = (tw - device_w) // 2

    if kind == "phone":
        bezel = max(int(device_w * 0.025), 14)
        radius = int(device_w * 0.13)
    else:
        bezel = max(int(device_w * 0.018), 12)
        radius = int(device_w * 0.05)

    full_w = device_w + bezel * 2
    full_h = device_h + bezel * 2
    img = Image.new("RGBA", (full_w, full_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, full_w, full_h), radius=radius + bezel, fill=(*theme.bezel, 255))
    d.rounded_rectangle(
        (bezel, bezel, full_w - bezel, full_h - bezel),
        radius=radius,
        fill=(0, 0, 0, 255),
    )

    inner_w = device_w - 4
    inner_h = device_h - 4
    inner = screen_base.resize((inner_w, inner_h), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (inner_w, inner_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, inner_w, inner_h), radius=max(radius - 2, 1), fill=255)
    img.paste(inner, (bezel + 2, bezel + 2), mask)

    if kind == "phone":
        notch_w = int(device_w * 0.32)
        notch_h = int(device_w * 0.06)
        nx = bezel + (device_w - notch_w) // 2
        ImageDraw.Draw(img).rounded_rectangle(
            (nx, bezel + 6, nx + notch_w, bezel + 6 + notch_h),
            radius=notch_h // 2,
            fill=(0, 0, 0, 255),
        )

    return {
        "image": img,
        "offset_final": (device_x - bezel, device_top - bezel),
        "device_inner_rect": (device_x, device_top, device_x + device_w, device_bottom),
        "bezel": bezel,
    }


def build_device_shadow(device_info: dict) -> tuple[Image.Image, tuple[int, int]]:
    """Cihaz altında yumuşak bir gölge — animasyon boyunca sadece alfa değişir."""
    img = device_info["image"]
    w, h = img.size
    pad = 60
    shadow = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        (pad + 10, pad + 30, pad + w - 10, pad + h + 10),
        radius=80,
        fill=(0, 0, 0, 140),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(36))
    fx, fy = device_info["offset_final"]
    return shadow, (fx - pad, fy - pad)


# --- Sahne kompozisyonu ----------------------------------------------------
def draw_headline_block(
    canvas: Image.Image,
    target_size,
    theme: Theme,
    headline: str,
    headline_alpha: float,
    bar_alpha: float,
):
    tw, th = target_size
    title_h = int(th * 0.18)
    f_head = font(int(tw * 0.06), bold=True)
    lines = wrap_headline(headline, f_head, tw - 120)
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    line_h = text_size(measure, "Aj", f_head)[1] + 16
    total_h = line_h * len(lines)
    ty = (title_h - total_h) // 2 + 80
    for ln in lines:
        lw, _ = text_size(measure, ln, f_head)
        draw_text_alpha(canvas, ((tw - lw) // 2, ty), ln, f_head, theme.text, headline_alpha)
        ty += line_h
    overlay_rounded_rect(
        canvas,
        ((tw - 120) // 2, title_h + 50, (tw + 120) // 2, title_h + 62),
        radius=6,
        color=PRIMARY,
        alpha=bar_alpha,
    )


def paste_device(
    canvas: Image.Image,
    device_info: dict,
    shadow_data: tuple[Image.Image, tuple[int, int]],
    slide_offset: int,
    alpha: float,
):
    if alpha <= 0.005:
        return
    shadow, (sx, sy) = shadow_data
    fx, fy = device_info["offset_final"]
    shadow_eff = fade_rgba(shadow, alpha * 0.85)
    canvas.paste(shadow_eff, (sx, sy + slide_offset), shadow_eff)
    dev = device_info["image"]
    dev_eff = fade_rgba(dev, alpha)
    canvas.paste(dev_eff, (fx, fy + slide_offset), dev_eff)


def apply_spotlight(canvas: Image.Image, device_info: dict, phase: float):
    """Cihaz ekranı boyunca aşağıya inen yumuşak parlaklık bandı."""
    rx0, ry0, rx1, ry1 = device_info["device_inner_rect"]
    inner_w = rx1 - rx0
    inner_h = ry1 - ry0
    cycles = 2
    cycle = (phase * cycles) % 1.0
    band_h = max(int(inner_h * 0.18), 80)
    band_y0 = int(ry0 + (inner_h - band_h) * cycle)
    band = Image.new("RGBA", (inner_w, band_h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    mid = band_h / 2
    for i in range(band_h):
        d = abs(i - mid) / mid
        a = int((1 - d) ** 1.4 * 90)
        if a > 0:
            bd.line([(0, i), (inner_w, i)], fill=(*PRIMARY, a))
    # Hafif beyaz çizgi vurgusu (en parlak nokta)
    bd.line([(0, int(mid)), (inner_w, int(mid))], fill=(*WHITE, 60))
    canvas.paste(band, (rx0, band_y0), band)


def apply_cta(canvas: Image.Image, device_info: dict, target_size, theme: Theme, phase: float):
    """Outro: aşağıdan yukarı süzülen 'App Store ve Play'de' rozeti."""
    tw, th = target_size
    eased = ease_out(phase)
    rx0, ry0, rx1, ry1 = device_info["device_inner_rect"]
    cta_w = int(min(tw * 0.78, (rx1 - rx0) * 1.05))
    cta_h = int(th * 0.085)
    cta_x = (tw - cta_w) // 2
    target_y = ry1 - cta_h - int(th * 0.04)
    start_y = ry1 + int(th * 0.05)
    cta_y = int(start_y + (target_y - start_y) * eased)

    overlay_rounded_rect(
        canvas,
        (cta_x, cta_y, cta_x + cta_w, cta_y + cta_h),
        radius=cta_h // 4,
        color=PRIMARY_DEEP,
        alpha=min(0.92, eased),
    )
    text = "App Store ve Google Play'de"
    f_cta = font(int(tw * 0.042), bold=True)
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    ctw, cth = text_size(measure, text, f_cta)
    draw_text_alpha(
        canvas,
        (cta_x + (cta_w - ctw) // 2, cta_y + (cta_h - cth) // 2 - 4),
        text,
        f_cta,
        WHITE,
        min(1.0, eased * 1.2),
    )


# --- Frame akışı -----------------------------------------------------------
def render_intro_frame(
    f: int,
    bg_layer: Image.Image,
    settled: Image.Image,
    device_info: dict,
    shadow_data: tuple[Image.Image, tuple[int, int]],
    target_size,
    theme: Theme,
    headline: str,
) -> Image.Image:
    tw, th = target_size
    canvas = bg_layer.copy()

    # Headline opacity: 0.5..1.5 sn
    head_alpha = ease_out((f - FPS * 0.5) / (FPS * 1.0))
    bar_alpha = ease_out((f - FPS * 0.9) / (FPS * 0.8))
    draw_headline_block(canvas, target_size, theme, headline, head_alpha, bar_alpha)

    # Cihaz: 1.0..2.5 sn arası slayt + fade
    dev_t = (f - FPS * 1.0) / (FPS * 1.5)
    dev_eased = ease_out(dev_t)
    slide = int((1 - dev_eased) * th * 0.18)
    paste_device(canvas, device_info, shadow_data, slide_offset=slide, alpha=dev_eased)
    return canvas


def make_one_video(
    flow_key: str,
    headline: str,
    screen_builder,
    target_size,
    kind: str,
    theme: Theme,
    output_path: Path,
    *,
    quiet: bool = False,
):
    tw, th = target_size

    # 1) Ekran içeriği: telefon ya da tablet baz çözünürlüğünde tek seferde üret
    base_size = PHONE_BASE if kind == "phone" else TABLET_BASE
    screen_base = screen_builder(*base_size, theme)

    # 2) Statik katmanlar
    bg_layer = build_background(target_size, theme)
    device_info = build_device_image(screen_base, target_size, kind, theme)
    shadow_data = build_device_shadow(device_info)

    # 3) "Settled" (intro sonrası, henüz spotlight/CTA yok) çerçeveyi pre-render
    settled = bg_layer.copy()
    draw_headline_block(settled, target_size, theme, headline, 1.0, 1.0)
    paste_device(settled, device_info, shadow_data, slide_offset=0, alpha=1.0)

    # 4) ffmpeg pipe başlat
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg bulunamadı. Lütfen ffmpeg'i kurun.")
    cmd = [
        ffmpeg_bin,
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{tw}x{th}",
        "-r", str(FPS),
        "-i", "-",
        "-an",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "medium",
        "-crf", "20",
        "-movflags", "+faststart",
        "-loglevel", "error",
        str(output_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    try:
        for f in range(TOTAL_FRAMES):
            if f < INTRO_END:
                frame = render_intro_frame(
                    f, bg_layer, settled, device_info, shadow_data, target_size, theme, headline
                )
            else:
                frame = settled.copy()
                if SPOTLIGHT_START <= f < SPOTLIGHT_END:
                    span = max(SPOTLIGHT_END - SPOTLIGHT_START - 1, 1)
                    apply_spotlight(frame, device_info, (f - SPOTLIGHT_START) / span)
                if f >= OUTRO_START:
                    span = max(TOTAL_FRAMES - OUTRO_START - 1, 1)
                    apply_cta(frame, device_info, target_size, theme, (f - OUTRO_START) / span)
            assert proc.stdin is not None
            proc.stdin.write(frame.tobytes())
    finally:
        if proc.stdin is not None:
            proc.stdin.close()

    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg hatası ({output_path}, exit={rc})")

    if not quiet:
        size_kb = output_path.stat().st_size // 1024
        print(f"  ✓ {output_path.relative_to(ROOT)}  ({size_kb} KB)")


def make_all_videos(themes: tuple[Theme, ...] = (DARK,), only_flows: list[str] | None = None) -> None:
    flows = [k for k in SCREENS if not only_flows or k in only_flows]
    total = len(flows) * len(VIDEO_SIZES) * len(themes)
    n = 0
    for key in flows:
        headline, builder = SCREENS[key]
        for theme in themes:
            theme_suffix = "" if theme.name == "dark" else "_light"
            for (platform, size_key), spec in VIDEO_SIZES.items():
                n += 1
                out = VIDEOS / platform / f"{key}_{size_key}{theme_suffix}.mp4"
                print(f"[{n}/{total}] {out.relative_to(ROOT)} — {headline}")
                make_one_video(
                    flow_key=key,
                    headline=headline,
                    screen_builder=builder,
                    target_size=spec["target"],
                    kind=spec["kind"],
                    theme=theme,
                    output_path=out,
                )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--light", action="store_true", help="Light tema videolarını da üret")
    parser.add_argument("--smoke", action="store_true", help="Sadece tek küçük test videosu üret")
    parser.add_argument(
        "--flow",
        action="append",
        choices=list(SCREENS.keys()),
        help="Sadece belirtilen flow(lar) için video üret (birden fazla kez kullanılabilir).",
    )
    args = parser.parse_args(argv)

    if args.smoke:
        # Hızlı doğrulama: 540x960, 1 flow
        global TOTAL_FRAMES, INTRO_END, SPOTLIGHT_START, OUTRO_START, SPOTLIGHT_END
        TOTAL_FRAMES = FPS * 6  # 6 sn
        INTRO_END = int(FPS * 1.0)
        SPOTLIGHT_START = int(FPS * 1.2)
        OUTRO_START = int(FPS * 5.0)
        SPOTLIGHT_END = OUTRO_START
        out = VIDEOS / "smoke_test.mp4"
        key = "02_today"
        headline, builder = SCREENS[key]
        print(f"Smoke test → {out.relative_to(ROOT)}")
        make_one_video(
            flow_key=key,
            headline=headline,
            screen_builder=builder,
            target_size=(540, 960),
            kind="phone",
            theme=DARK,
            output_path=out,
        )
        return 0

    themes = (DARK, LIGHT) if args.light else (DARK,)
    flows = args.flow or list(SCREENS.keys())
    print(
        f"Generating store preview videos ({len(themes)} tema, {len(flows)} flow, {len(VIDEO_SIZES)} boyut) …"
    )
    make_all_videos(themes=themes, only_flows=flows)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
