"""
Syroce PMS mobile — asset generator.

Üretilen dosyalar:
  mobile/assets/
    icon.png                 1024x1024  (iOS + genel)
    adaptive-icon.png        1024x1024  (Android adaptive foreground, transparent)
    splash-light.png         1242x2436  (light şema açılış)
    splash-dark.png          1242x2436  (dark şema açılış)
    notification-icon.png    96x96      (Android notification, beyaz monochrome)
    favicon.png              48x48
  mobile/store/screenshots/
    ios/<flow>_<size>.png            koyu tema (varsayılan)
        boyutlar: 6_7 (1290x2796), 6_5 (1284x2778), 5_5 (1242x2208),
                  12_9 (2048x2732 — iPad 12.9"), 11 (1668x2388 — iPad 11")
    ios/<flow>_<size>_light.png      light tema (aynı boyutlar)
    android/<flow>_phone.png         1080x1920 telefon — koyu
    android/<flow>_phone_light.png   1080x1920 telefon — light
    android/<flow>_tablet_7.png      1200x1920 tablet 7" — koyu
    android/<flow>_tablet_10.png     1600x2560 tablet 10" — koyu
    android/<flow>_tablet_*_light.png  light varyantları

Tüm görseller Syroce kurumsal kimliğine (lacivert + mavi vurgu) uygundur ve
hem koyu hem light şemada Türkçe başlıklar kullanılır.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SHOTS = ROOT / "store" / "screenshots"
ASSETS.mkdir(parents=True, exist_ok=True)
(SHOTS / "ios").mkdir(parents=True, exist_ok=True)
(SHOTS / "android").mkdir(parents=True, exist_ok=True)

# --- Marka palette (sabit accent renkleri) ---------------------------------
BG_DARK = (11, 15, 26)
SURFACE = (18, 24, 38)
SURFACE_ALT = (26, 34, 54)
BORDER = (36, 48, 73)
TEXT = (244, 246, 251)
MUTED = (154, 166, 191)
PRIMARY = (59, 130, 246)
PRIMARY_DEEP = (37, 99, 235)
SUCCESS = (22, 163, 74)
WARNING = (245, 158, 11)
DANGER = (239, 68, 68)
INFO = (14, 165, 233)
VIP = (168, 85, 247)
WHITE = (255, 255, 255)

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


# --- Tema sistemi ----------------------------------------------------------
@dataclass(frozen=True)
class Theme:
    name: str
    bg: tuple
    surface: tuple
    surface_alt: tuple
    border: tuple
    text: tuple
    muted: tuple
    bezel: tuple                # cihaz çerçevesi (compose_marketing)
    grad_top_offset: tuple      # marketing arka plan gradient offseti


DARK = Theme(
    name="dark",
    bg=BG_DARK,
    surface=SURFACE,
    surface_alt=SURFACE_ALT,
    border=BORDER,
    text=TEXT,
    muted=MUTED,
    bezel=(30, 35, 50),
    grad_top_offset=(20, 25, 50),
)

LIGHT = Theme(
    name="light",
    bg=(247, 248, 251),
    surface=(255, 255, 255),
    surface_alt=(235, 240, 248),
    border=(215, 222, 235),
    text=(15, 23, 42),
    muted=(91, 100, 120),
    bezel=(190, 196, 210),
    grad_top_offset=(8, 7, 4),
)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


def text_size(draw: ImageDraw.ImageDraw, txt: str, fnt: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), txt, font=fnt)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def rounded_rect(draw: ImageDraw.ImageDraw, xy, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


# --- Logo / Icon -----------------------------------------------------------
def draw_logo_mark(im: Image.Image, cx: int, cy: int, size: int, *, transparent_bg: bool = False):
    """
    Syroce mark: yuvarlatılmış kare üzerinde stilize "S" + altın anahtar vurgusu.
    """
    d = ImageDraw.Draw(im, "RGBA")
    half = size // 2
    box = (cx - half, cy - half, cx + half, cy + half)

    if not transparent_bg:
        # Gradyan arkaplan: koyu lacivert -> mavi
        grad = Image.new("RGB", (size, size), BG_DARK)
        gd = ImageDraw.Draw(grad)
        for y in range(size):
            t = y / max(size - 1, 1)
            r = int(BG_DARK[0] + (PRIMARY_DEEP[0] - BG_DARK[0]) * t * 0.55)
            g = int(BG_DARK[1] + (PRIMARY_DEEP[1] - BG_DARK[1]) * t * 0.55)
            b = int(BG_DARK[2] + (PRIMARY_DEEP[2] - BG_DARK[2]) * t * 0.55)
            gd.line([(0, y), (size, y)], fill=(r, g, b))
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius=int(size * 0.22), fill=255)
        im.paste(grad, (cx - half, cy - half), mask)

    # Stilize S (üst yay + alt yay)
    stroke = max(int(size * 0.12), 6)
    pad = int(size * 0.22)
    s_box = (cx - half + pad, cy - half + pad, cx + half - pad, cy + half - pad)
    sx0, sy0, sx1, sy1 = s_box
    sw = sx1 - sx0
    sh = sy1 - sy0
    # Üst yay (sağdan sola)
    d.arc((sx0, sy0, sx1, sy0 + sh * 0.65), start=200, end=350, fill=PRIMARY, width=stroke)
    # Alt yay (soldan sağa)
    d.arc((sx0, sy0 + sh * 0.35, sx1, sy1), start=20, end=170, fill=PRIMARY, width=stroke)
    # Bağlantı diagonal
    d.line(
        [(sx0 + sw * 0.18, sy0 + sh * 0.55), (sx1 - sw * 0.18, sy0 + sh * 0.45)],
        fill=PRIMARY,
        width=stroke,
    )
    # Beyaz vurgu (parlak)
    highlight = max(stroke // 3, 2)
    d.arc(
        (sx0 + 4, sy0 + 4, sx1 + 4, sy0 + sh * 0.65 + 4),
        start=210,
        end=260,
        fill=WHITE,
        width=highlight,
    )


def make_icon():
    size = 1024
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw_logo_mark(im, size // 2, size // 2, size)
    im.convert("RGB").save(ASSETS / "icon.png", "PNG")

    # Adaptive foreground (transparent bg, mark daha küçük — safe zone 66%)
    # Android adaptive background, app.json içindeki backgroundColor
    # ("#0b0f1a") ile sağlanır; ayrı bir PNG'e ihtiyaç yoktur.
    fg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw_logo_mark(fg, size // 2, size // 2, int(size * 0.62), transparent_bg=True)
    fg.save(ASSETS / "adaptive-icon.png", "PNG")

    # Notification icon (Android — beyaz silüet, 96x96)
    nt = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    nd = ImageDraw.Draw(nt)
    sw = 10
    pad = 18
    sx0, sy0, sx1, sy1 = pad, pad, 96 - pad, 96 - pad
    sh = sy1 - sy0
    sw_ = sx1 - sx0
    nd.arc((sx0, sy0, sx1, sy0 + sh * 0.65), start=200, end=350, fill=WHITE, width=sw)
    nd.arc((sx0, sy0 + sh * 0.35, sx1, sy1), start=20, end=170, fill=WHITE, width=sw)
    nd.line(
        [(sx0 + sw_ * 0.18, sy0 + sh * 0.55), (sx1 - sw_ * 0.18, sy0 + sh * 0.45)],
        fill=WHITE,
        width=sw,
    )
    nt.save(ASSETS / "notification-icon.png", "PNG")

    # Favicon
    fav = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    draw_logo_mark(fav, 24, 24, 48)
    fav.save(ASSETS / "favicon.png", "PNG")


# --- Splash ---------------------------------------------------------------
def make_splash():
    w, h = 1242, 2436
    for variant in ("dark", "light"):
        bg_color = BG_DARK if variant == "dark" else (247, 248, 251)
        text_color = TEXT if variant == "dark" else (15, 23, 42)
        muted_color = MUTED if variant == "dark" else (91, 100, 120)
        im = Image.new("RGB", (w, h), bg_color)
        d = ImageDraw.Draw(im)
        # Hafif radial benzeri vurgu
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse((-300, h // 2 - 700, w + 300, h // 2 + 700), fill=(*PRIMARY, 35))
        glow = glow.filter(ImageFilter.GaussianBlur(140))
        im.paste(Image.alpha_composite(im.convert("RGBA"), glow).convert("RGB"))

        draw_logo_mark(im, w // 2, h // 2 - 120, 420, transparent_bg=False)

        f_title = font(96, bold=True)
        f_sub = font(46)
        title = "Syroce PMS"
        sub = "Otelinizi cebinizden yönetin"
        tw, _ = text_size(d, title, f_title)
        sw_, _ = text_size(d, sub, f_sub)
        d.text(((w - tw) // 2, h // 2 + 200), title, fill=text_color, font=f_title)
        d.text(((w - sw_) // 2, h // 2 + 320), sub, fill=muted_color, font=f_sub)

        out_name = "splash-dark.png" if variant == "dark" else "splash-light.png"
        im.save(ASSETS / out_name, "PNG")


# --- Mockup screen helpers ------------------------------------------------
def base_screen(w: int, h: int, theme: Theme) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (w, h), theme.bg)
    d = ImageDraw.Draw(im)
    return im, d


def status_bar(d: ImageDraw.ImageDraw, w: int, theme: Theme, time: str = "09:41"):
    fnt = font(34, bold=True)
    d.text((48, 28), time, fill=theme.text, font=fnt)
    # sağ: sinyal/wifi/batarya — basit bar'lar
    bx = w - 48
    # batarya
    d.rounded_rectangle((bx - 70, 38, bx, 64), radius=4, outline=theme.text, width=2)
    d.rounded_rectangle((bx - 67, 41, bx - 18, 61), radius=2, fill=theme.text)
    d.rectangle((bx, 46, bx + 4, 56), fill=theme.text)
    # wifi (üç bar)
    for i, hh in enumerate([10, 16, 22]):
        d.rectangle((bx - 110 + i * 8, 64 - hh, bx - 104 + i * 8, 64), fill=theme.text)
    # sinyal
    for i, hh in enumerate([8, 14, 20, 26]):
        d.rectangle((bx - 180 + i * 9, 64 - hh, bx - 174 + i * 9, 64), fill=theme.text)


def app_header(d: ImageDraw.ImageDraw, w: int, theme: Theme, title: str, subtitle: str | None = None):
    d.text((48, 110), title, fill=theme.text, font=font(54, bold=True))
    if subtitle:
        d.text((48, 178), subtitle, fill=theme.muted, font=font(32))


def chip(d, x, y, label, color=PRIMARY, bg=None):
    fnt = font(28, bold=True)
    pad = 18
    tw, th = text_size(d, label, fnt)
    box = (x, y, x + tw + pad * 2, y + th + 16)
    fill = bg if bg else (color[0], color[1], color[2])
    d.rounded_rectangle(box, radius=20, fill=fill)
    d.text((x + pad, y + 8), label, fill=WHITE, font=fnt)
    return box[2] - x


def card(d, x, y, w, h, theme: Theme, *, fill=None, border=None):
    d.rounded_rectangle(
        (x, y, x + w, y + h),
        radius=24,
        fill=fill if fill is not None else theme.surface,
        outline=border if border is not None else theme.border,
        width=2,
    )


def tab_bar(d: ImageDraw.ImageDraw, w: int, h: int, theme: Theme, items: list[tuple[str, bool]]):
    bar_h = 160
    y0 = h - bar_h
    d.rectangle((0, y0, w, h), fill=theme.surface)
    d.rectangle((0, y0, w, y0 + 2), fill=theme.border)
    n = len(items)
    cell = w // n
    for i, (label, active) in enumerate(items):
        cx = i * cell + cell // 2
        # ikon olarak basit daire/yuvarlak
        color = PRIMARY if active else theme.muted
        d.ellipse((cx - 22, y0 + 32, cx + 22, y0 + 76), outline=color, width=4)
        if active:
            d.ellipse((cx - 8, y0 + 46, cx + 8, y0 + 62), fill=color)
        f = font(24, bold=active)
        tw_, _ = text_size(d, label, f)
        d.text((cx - tw_ // 2, y0 + 90), label, fill=color, font=f)


# --- Specific screens -----------------------------------------------------
def screen_login(w, h, theme: Theme, kind: str = "phone"):
    if kind == "tablet":
        return _screen_login_tablet(w, h, theme)
    im, d = base_screen(w, h, theme)
    status_bar(d, w, theme)
    # logo merkez üst
    draw_logo_mark(im, w // 2, h // 2 - 480, 260)
    d_ = ImageDraw.Draw(im)
    title = "Syroce PMS"
    sub = "Otelinizi cebinizden yönetin"
    tw, _ = text_size(d_, title, font(64, bold=True))
    sw_, _ = text_size(d_, sub, font(34))
    d_.text(((w - tw) // 2, h // 2 - 290), title, fill=theme.text, font=font(64, bold=True))
    d_.text(((w - sw_) // 2, h // 2 - 210), sub, fill=theme.muted, font=font(34))

    # Form kartı
    cx, cy, cw, ch = 80, h // 2 - 100, w - 160, 760
    card(d_, cx, cy, cw, ch, theme)
    d_.text((cx + 40, cy + 40), "E-posta", fill=theme.muted, font=font(28))
    d_.rounded_rectangle((cx + 40, cy + 80, cx + cw - 40, cy + 160), radius=14, fill=theme.surface_alt)
    d_.text((cx + 60, cy + 102), "info@syroce.com", fill=theme.text, font=font(34))
    d_.text((cx + 40, cy + 200), "Parola", fill=theme.muted, font=font(28))
    d_.rounded_rectangle((cx + 40, cy + 240, cx + cw - 40, cy + 320), radius=14, fill=theme.surface_alt)
    d_.text((cx + 60, cy + 262), "•••••••••••", fill=theme.text, font=font(34))
    # buton
    d_.rounded_rectangle((cx + 40, cy + 400, cx + cw - 40, cy + 500), radius=18, fill=PRIMARY)
    f = font(38, bold=True)
    btxt = "Giriş yap"
    btw, bth = text_size(d_, btxt, f)
    d_.text((cx + cw // 2 - btw // 2, cy + 430), btxt, fill=WHITE, font=f)
    # Biyometri
    d_.rounded_rectangle((cx + 40, cy + 540, cx + cw - 40, cy + 640), radius=18, outline=PRIMARY, width=3)
    btxt2 = "Face ID ile giriş"
    btw2, _ = text_size(d_, btxt2, f)
    d_.text((cx + cw // 2 - btw2 // 2, cy + 570), btxt2, fill=PRIMARY, font=f)

    d_.text((80, h - 200), "Demo: info@syroce.com / Syroce2026", fill=theme.muted, font=font(26))
    return im


def screen_today(w, h, theme: Theme, kind: str = "phone"):
    if kind == "tablet":
        return _screen_today_tablet(w, h, theme)
    im, d = base_screen(w, h, theme)
    status_bar(d, w, theme)
    app_header(d, w, theme, "Bugün", "5 Mayıs 2026 · Resepsiyon")

    # Özet kartları (3'lü grid)
    y = 240
    box_w = (w - 48 * 2 - 32) // 3
    summaries = [("12", "Check-in", PRIMARY), ("8", "Check-out", INFO), ("3", "No-show", WARNING)]
    for i, (val, lbl, col) in enumerate(summaries):
        x = 48 + i * (box_w + 16)
        card(d, x, y, box_w, 200, theme)
        d.text((x + 24, y + 24), val, fill=col, font=font(72, bold=True))
        d.text((x + 24, y + 130), lbl, fill=theme.muted, font=font(28))

    # Bölüm başlığı
    y2 = y + 240
    d.text((48, y2), "Bekleyen check-in'ler", fill=theme.text, font=font(40, bold=True))
    d.text((48, y2 + 60), "Bugünün önceliği", fill=theme.muted, font=font(28))

    # Liste
    rows = [
        ("Aydın Yılmaz", "Oda 412 · 2 yetişkin", "VIP", VIP),
        ("Selin Demir", "Oda 207 · 1 yetişkin", "Erken giriş", INFO),
        ("Mert Karaca", "Oda 318 · 2 yetişkin · 1 çocuk", "Standart", MUTED),
        ("Hannah Becker", "Oda 521 · 2 yetişkin", "Geç kalmış", WARNING),
    ]
    ry = y2 + 130
    for name, sub, tag, color in rows:
        card(d, 48, ry, w - 96, 180, theme)
        # avatar
        d.ellipse((72, ry + 30, 192, ry + 150), fill=theme.surface_alt)
        ini = "".join(p[0] for p in name.split()[:2])
        iw, ih = text_size(d, ini, font(48, bold=True))
        d.text((132 - iw // 2, 90 + ry - ih // 2), ini, fill=PRIMARY, font=font(48, bold=True))
        d.text((220, ry + 30), name, fill=theme.text, font=font(36, bold=True))
        d.text((220, ry + 80), sub, fill=theme.muted, font=font(28))
        chip(d, 220, ry + 120, tag, color=color)
        # check-in butonu
        d.rounded_rectangle((w - 320, ry + 60, w - 80, ry + 140), radius=16, fill=PRIMARY)
        f = font(30, bold=True)
        bt = "Check-in"
        bw, bh = text_size(d, bt, f)
        d.text((w - 200 - bw // 2, ry + 100 - bh // 2), bt, fill=WHITE, font=f)
        ry += 200

    # FAB
    d.ellipse((w - 200, h - 360, w - 60, h - 220), fill=PRIMARY)
    d.text((w - 158, h - 332), "+", fill=WHITE, font=font(72, bold=True))

    tab_bar(d, w, h, theme, [("Bugün", True), ("Misafirler", False), ("Walk-in", False), ("Daha", False)])
    return im


def screen_quick_checkin(w, h, theme: Theme, kind: str = "phone"):
    if kind == "tablet":
        return _screen_quick_checkin_tablet(w, h, theme)
    im, d = base_screen(w, h, theme)
    status_bar(d, w, theme)
    app_header(d, w, theme, "Hızlı Check-in", "QR + kimlik tarama")

    # Kamera frame mock — kameranın görüntüsü gerçekçi olması için her temada koyu kalır
    cy0 = 280
    ch = 1100
    card(d, 48, cy0, w - 96, ch, theme, fill=(8, 12, 20), border=theme.border)
    # köşe ayraçları
    pad = 80
    L = 60
    th = 8
    for (cx_, cy_) in [
        (48 + pad, cy0 + pad),
        (w - 48 - pad, cy0 + pad),
        (48 + pad, cy0 + ch - pad),
        (w - 48 - pad, cy0 + ch - pad),
    ]:
        # L şekli
        sx = -1 if cx_ > w // 2 else 1
        sy = -1 if cy_ > cy0 + ch // 2 else 1
        d.line([(cx_, cy_), (cx_ + sx * L, cy_)], fill=PRIMARY, width=th)
        d.line([(cx_, cy_), (cx_, cy_ + sy * L)], fill=PRIMARY, width=th)

    # QR mock (merkez)
    qx, qy, qs = w // 2 - 220, cy0 + ch // 2 - 220, 440
    d.rectangle((qx, qy, qx + qs, qy + qs), fill=WHITE)
    # rastgele desen
    import random
    random.seed(42)
    cell = qs // 25
    for i in range(25):
        for j in range(25):
            if (i, j) in [(0, 0), (0, 24), (24, 0)]:
                continue
            if random.random() > 0.55:
                d.rectangle(
                    (qx + i * cell, qy + j * cell, qx + (i + 1) * cell, qy + (j + 1) * cell),
                    fill=(15, 23, 42),
                )
    # konumlandırma kareleri
    for (cx_, cy_) in [(qx + 8, qy + 8), (qx + qs - 70 - 8, qy + 8), (qx + 8, qy + qs - 70 - 8)]:
        d.rectangle((cx_, cy_, cx_ + 70, cy_ + 70), outline=(15, 23, 42), width=10)
        d.rectangle((cx_ + 24, cy_ + 24, cx_ + 46, cy_ + 46), fill=(15, 23, 42))

    # Kamera viewfinder beyaz kalır (her zaman koyu kamera arka planı üstünde)
    d.text((48 + pad, cy0 + ch - pad - 80), "QR'ı çerçeveye hizalayın", fill=WHITE, font=font(32, bold=True))

    # Alt panel
    py = cy0 + ch + 40
    card(d, 48, py, w - 96, 300, theme)
    d.text((48 + 32, py + 28), "Misafir bulundu", fill=SUCCESS, font=font(32, bold=True))
    d.text((48 + 32, py + 80), "Aydın Yılmaz", fill=theme.text, font=font(44, bold=True))
    d.text((48 + 32, py + 140), "TR · Doğum 12.04.1987", fill=theme.muted, font=font(28))
    chip(d, 48 + 32, py + 200, "VIP", color=VIP)
    chip(d, 48 + 32 + 130, py + 200, "Tekrar misafir", color=INFO)
    # Onay butonu
    d.rounded_rectangle((w - 360, py + 100, w - 80, py + 200), radius=18, fill=SUCCESS)
    bt = "Onayla"
    f = font(34, bold=True)
    bw, bh = text_size(d, bt, f)
    d.text((w - 220 - bw // 2, py + 150 - bh // 2), bt, fill=WHITE, font=f)

    tab_bar(d, w, h, theme, [("Bugün", False), ("Misafirler", False), ("Walk-in", True), ("Daha", False)])
    return im


def screen_housekeeping(w, h, theme: Theme, kind: str = "phone"):
    if kind == "tablet":
        return _screen_housekeeping_tablet(w, h, theme)
    im, d = base_screen(w, h, theme)
    status_bar(d, w, theme)
    app_header(d, w, theme, "Kat hizmetleri", "Kat 4 · 14 oda")

    # Filtre çipleri
    y = 240
    x = 48
    for label, active in [("Tüm katlar", False), ("4. kat", True), ("Kirli", False), ("Temiz", False), ("Bakım", False)]:
        f = font(28, bold=True)
        tw, th = text_size(d, label, f)
        pad = 24
        bw = tw + pad * 2
        if active:
            d.rounded_rectangle((x, y, x + bw, y + th + 20), radius=24, fill=PRIMARY)
            d.text((x + pad, y + 10), label, fill=WHITE, font=f)
        else:
            d.rounded_rectangle((x, y, x + bw, y + th + 20), radius=24, outline=theme.border, width=2)
            d.text((x + pad, y + 10), label, fill=theme.muted, font=f)
        x += bw + 16

    # Oda grid (3 sütun)
    rooms = [
        ("401", "Temiz", SUCCESS),
        ("402", "Kirli", WARNING),
        ("403", "Temizleniyor", INFO),
        ("404", "Bakım", DANGER),
        ("405", "Temiz", SUCCESS),
        ("406", "Dolu", PRIMARY),
        ("407", "Kirli", WARNING),
        ("408", "Temiz", SUCCESS),
        ("409", "İnceleme", INFO),
        ("410", "Temiz", SUCCESS),
        ("411", "Kirli", WARNING),
        ("412", "Dolu", PRIMARY),
        ("414", "Temiz", SUCCESS),
        ("415", "Bakım", DANGER),
        ("416", "Temiz", SUCCESS),
    ]
    gy = 380
    cols = 3
    cell_w = (w - 48 * 2 - 24 * (cols - 1)) // cols
    cell_h = 240
    for idx, (no, status, color) in enumerate(rooms):
        col = idx % cols
        row = idx // cols
        cx = 48 + col * (cell_w + 24)
        cy = gy + row * (cell_h + 20)
        if cy + cell_h > h - 200:
            break
        card(d, cx, cy, cell_w, cell_h, theme)
        # status dot
        d.ellipse((cx + cell_w - 60, cy + 24, cx + cell_w - 28, cy + 56), fill=color)
        d.text((cx + 28, cy + 28), no, fill=theme.text, font=font(58, bold=True))
        d.text((cx + 28, cy + 110), status, fill=color, font=font(28, bold=True))
        d.text((cx + 28, cy + 160), "Standart", fill=theme.muted, font=font(24))

    tab_bar(d, w, h, theme, [("Odalar", True), ("Hasar", False), ("Daha", False)])
    return im


def screen_guest_bookings(w, h, theme: Theme, kind: str = "phone"):
    if kind == "tablet":
        return _screen_guest_bookings_tablet(w, h, theme)
    im, d = base_screen(w, h, theme)
    status_bar(d, w, theme)
    app_header(d, w, theme, "Rezervasyonlarım", "Aydın · Sadakat: Altın")

    # Aktif rezervasyon
    y = 260
    card(d, 48, y, w - 96, 600, theme)
    chip(d, 80, y + 32, "Aktif", color=SUCCESS)
    d.text((80, y + 100), "Bodrum Sahil Suite", fill=theme.text, font=font(46, bold=True))
    d.text((80, y + 170), "10 – 14 Mayıs 2026", fill=theme.muted, font=font(32))
    d.text((80, y + 220), "Oda 521 · 2 yetişkin", fill=theme.muted, font=font(28))

    # Detay grid
    items = [
        ("Toplam", "₺18.400"),
        ("Ödenen", "₺9.200"),
        ("Bakiye", "₺9.200"),
        ("Konuk", "2"),
    ]
    iy = y + 290
    iw = (w - 96 - 64) // 4
    for i, (lbl, val) in enumerate(items):
        ix = 80 + i * (iw + 16)
        d.text((ix, iy), lbl, fill=theme.muted, font=font(24))
        d.text((ix, iy + 32), val, fill=theme.text, font=font(34, bold=True))

    # Aksiyonlar
    bx = 80
    by = y + 440
    for i, (label, color) in enumerate([("Dijital anahtar", PRIMARY), ("Mesaj gönder", INFO), ("Erken giriş", WARNING)]):
        f = font(26, bold=True)
        tw, _ = text_size(d, label, f)
        bw = tw + 60
        d.rounded_rectangle((bx, by, bx + bw, by + 70), radius=20, fill=color)
        d.text((bx + 30, by + 22), label, fill=WHITE, font=f)
        bx += bw + 16

    # Geçmiş
    y2 = y + 660
    d.text((48, y2), "Geçmiş konaklamalar", fill=theme.text, font=font(38, bold=True))
    past = [
        ("İstanbul Boğaz", "12 – 14 Eylül 2025", "Tamamlandı"),
        ("Antalya Riviera", "01 – 08 Temmuz 2025", "Tamamlandı"),
    ]
    py = y2 + 80
    for title, date, status in past:
        card(d, 48, py, w - 96, 160, theme)
        d.text((80, py + 30), title, fill=theme.text, font=font(34, bold=True))
        d.text((80, py + 80), date, fill=theme.muted, font=font(28))
        d.text((80, py + 118), status, fill=SUCCESS, font=font(26, bold=True))
        py += 180

    tab_bar(d, w, h, theme, [("Ana", False), ("Rez.", True), ("Mesaj", False), ("Daha", False)])
    return im


def screen_digital_key(w, h, theme: Theme, kind: str = "phone"):
    if kind == "tablet":
        return _screen_digital_key_tablet(w, h, theme)
    im, d = base_screen(w, h, theme)
    status_bar(d, w, theme)
    app_header(d, w, theme, "Dijital anahtar", "Oda 521 · Bodrum Sahil Suite")

    # Büyük QR / NFC kartı
    cy0 = 320
    ch = 1400
    card(d, 48, cy0, w - 96, ch, theme)

    # QR
    qx, qy, qs = w // 2 - 380, cy0 + 100, 760
    d.rectangle((qx, qy, qx + qs, qy + qs), fill=WHITE)
    import random
    random.seed(7)
    cell = qs // 29
    for i in range(29):
        for j in range(29):
            if random.random() > 0.5:
                d.rectangle(
                    (qx + i * cell, qy + j * cell, qx + (i + 1) * cell, qy + (j + 1) * cell),
                    fill=(15, 23, 42),
                )
    for (cx_, cy_) in [(qx + 8, qy + 8), (qx + qs - 110, qy + 8), (qx + 8, qy + qs - 110)]:
        d.rectangle((cx_, cy_, cx_ + 100, cy_ + 100), outline=(15, 23, 42), width=14)
        d.rectangle((cx_ + 30, cy_ + 30, cx_ + 70, cy_ + 70), fill=(15, 23, 42))

    # Süre + bilgi
    iy = qy + qs + 60
    d.text((qx, iy), "Geçerlilik", fill=theme.muted, font=font(28))
    d.text((qx, iy + 40), "14 Mayıs 11:00'a kadar", fill=theme.text, font=font(38, bold=True))

    # Bluetooth/NFC indicator
    d.rounded_rectangle((48 + 60, cy0 + ch - 220, w - 48 - 60, cy0 + ch - 80), radius=24, fill=theme.surface_alt)
    d.ellipse((48 + 100, cy0 + ch - 200, 48 + 200, cy0 + ch - 100), fill=PRIMARY)
    d.text((48 + 230, cy0 + ch - 195), "Bluetooth ile yaklaşın", fill=theme.text, font=font(34, bold=True))
    d.text((48 + 230, cy0 + ch - 145), "Kapı kilidini otomatik açar", fill=theme.muted, font=font(26))

    # Aksiyon butonları
    by = cy0 + ch + 40
    d.rounded_rectangle((48, by, w // 2 - 16, by + 110), radius=22, fill=PRIMARY)
    bt = "Anahtarı paylaş"
    f = font(32, bold=True)
    bw, bh = text_size(d, bt, f)
    d.text(((w // 2 - 16) // 2 + 24 - bw // 2, by + 55 - bh // 2), bt, fill=WHITE, font=f)

    d.rounded_rectangle((w // 2 + 16, by, w - 48, by + 110), radius=22, outline=PRIMARY, width=4)
    bt2 = "Yardım"
    bw2, _ = text_size(d, bt2, f)
    d.text(((w // 2 + 16 + w - 48) // 2 - bw2 // 2, by + 55 - bh // 2), bt2, fill=PRIMARY, font=f)

    tab_bar(d, w, h, theme, [("Ana", False), ("Rez.", False), ("Anahtar", True), ("Daha", False)])
    return im


# --- Tablet (iPad / Android tablet) varyantları ---------------------------
# Tablet baz çözünürlüğü 1668x2224 (3:4 portrait). Telefon ekranlarını
# büyütmek yerine gerçek tablet düzeni kullanırız: solda iPadOS tarzı
# yan navigasyon, sağda master-detail iki sütun.
TABLET_RAIL_W = 220
TABLET_PAD = 32


def _tablet_side_rail(
    im: Image.Image,
    d: ImageDraw.ImageDraw,
    h: int,
    theme: Theme,
    items: list[tuple[str, bool]],
) -> int:
    """iPadOS tarzı sol navigasyon. Aktif öğe vurgulanır."""
    rail_w = TABLET_RAIL_W
    d.rectangle((0, 0, rail_w, h), fill=theme.surface)
    d.rectangle((rail_w - 2, 0, rail_w, h), fill=theme.border)
    # Logo + marka adı
    draw_logo_mark(im, rail_w // 2, 130, 110)
    f_brand = font(30, bold=True)
    bw, _ = text_size(d, "Syroce", f_brand)
    d.text(((rail_w - bw) // 2, 210), "Syroce", fill=theme.text, font=f_brand)
    # Navigasyon öğeleri
    y = 320
    for label, active in items:
        if active:
            d.rounded_rectangle((16, y, rail_w - 16, y + 96), radius=20, fill=PRIMARY)
            color = WHITE
        else:
            color = theme.muted
        d.ellipse((44, y + 26, 104, y + 86), outline=color, width=4)
        if active:
            d.ellipse((62, y + 44, 86, y + 68), fill=color)
        d.text((124, y + 38), label, fill=color, font=font(28, bold=active))
        y += 112
    # Alt: kullanıcı kartı
    uy = h - 160
    d.ellipse((44, uy, 124, uy + 80), fill=theme.surface_alt)
    d.text((68, uy + 18), "AY", fill=PRIMARY, font=font(36, bold=True))
    d.text((140, uy + 8), "Aydın Y.", fill=theme.text, font=font(26, bold=True))
    d.text((140, uy + 46), "Resepsiyon", fill=theme.muted, font=font(22))
    return rail_w


def _tablet_header(
    d: ImageDraw.ImageDraw,
    rail_w: int,
    theme: Theme,
    title: str,
    subtitle: str,
    *,
    chip_label: str | None = None,
) -> int:
    """Sağ alanın üstüne büyük başlık + opsiyonel durum çipi koyar."""
    x0 = rail_w + TABLET_PAD
    d.text((x0, 70), title, fill=theme.text, font=font(64, bold=True))
    d.text((x0, 158), subtitle, fill=theme.muted, font=font(32))
    if chip_label:
        chip(d, x0 + text_size(d, title, font(64, bold=True))[0] + 28, 92, chip_label, color=PRIMARY)
    return 240  # content y_start


def _screen_login_tablet(w: int, h: int, theme: Theme) -> Image.Image:
    im, d = base_screen(w, h, theme)
    # Sol marketing alanı
    left_w = int(w * 0.55)
    # Hafif gradyan vurgusu
    grad = Image.new("RGBA", (left_w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    gd.ellipse((-200, h // 3 - 350, left_w + 200, h // 3 + 350), fill=(*PRIMARY, 38))
    grad = grad.filter(ImageFilter.GaussianBlur(110))
    im.paste(grad, (0, 0), grad)
    d = ImageDraw.Draw(im)
    draw_logo_mark(im, 220, 260, 240)
    d.text((400, 220), "Syroce PMS", fill=theme.text, font=font(72, bold=True))
    d.text((400, 320), "iPad için optimize edilmiş", fill=theme.muted, font=font(34))
    # Slogan
    d.text((140, 540), "Otelinizi cebinizden", fill=theme.text, font=font(72, bold=True))
    d.text((140, 630), "ve iPad'inizden yönetin.", fill=theme.text, font=font(72, bold=True))
    # Özellik listesi
    feats = [
        ("Split View", "Misafir listesi ve detayını yan yana"),
        ("Apple Pencil", "Hızlı imza ve notlar"),
        ("Klavye kısayolları", "30 saniyede check-in"),
        ("Çoklu görev", "Slide Over desteği"),
    ]
    fy = 800
    for title_, sub in feats:
        d.ellipse((140, fy + 12, 188, fy + 60), outline=PRIMARY, width=4)
        d.line([(152, fy + 38), (164, fy + 50), (180, fy + 22)], fill=PRIMARY, width=5)
        d.text((220, fy), title_, fill=theme.text, font=font(36, bold=True))
        d.text((220, fy + 50), sub, fill=theme.muted, font=font(28))
        fy += 110

    # Sağ form kartı
    cw = w - left_w - 120
    cx = left_w + 60
    ch = 1100
    cy = (h - ch) // 2
    card(d, cx, cy, cw, ch, theme)
    d.text((cx + 48, cy + 56), "Hoş geldiniz", fill=theme.text, font=font(52, bold=True))
    d.text((cx + 48, cy + 130), "Lütfen hesabınızla giriş yapın", fill=theme.muted, font=font(28))

    d.text((cx + 48, cy + 230), "E-posta", fill=theme.muted, font=font(28))
    d.rounded_rectangle((cx + 48, cy + 270, cx + cw - 48, cy + 360), radius=16, fill=theme.surface_alt)
    d.text((cx + 70, cy + 296), "info@syroce.com", fill=theme.text, font=font(34))
    d.text((cx + 48, cy + 410), "Parola", fill=theme.muted, font=font(28))
    d.rounded_rectangle((cx + 48, cy + 450, cx + cw - 48, cy + 540), radius=16, fill=theme.surface_alt)
    d.text((cx + 70, cy + 476), "•••••••••••", fill=theme.text, font=font(34))

    d.rounded_rectangle((cx + 48, cy + 620, cx + cw - 48, cy + 730), radius=20, fill=PRIMARY)
    f = font(38, bold=True)
    bt = "Giriş yap"
    btw, bth = text_size(d, bt, f)
    d.text((cx + cw // 2 - btw // 2, cy + 655), bt, fill=WHITE, font=f)

    d.rounded_rectangle((cx + 48, cy + 760, cx + cw - 48, cy + 870), radius=20, outline=PRIMARY, width=3)
    bt2 = "Touch ID ile giriş"
    btw2, _ = text_size(d, bt2, f)
    d.text((cx + cw // 2 - btw2 // 2, cy + 795), bt2, fill=PRIMARY, font=f)

    d.text((cx + 48, cy + ch - 90), "Demo: info@syroce.com / Syroce2026", fill=theme.muted, font=font(26))
    return im


def _screen_today_tablet(w: int, h: int, theme: Theme) -> Image.Image:
    im, d = base_screen(w, h, theme)
    rail_w = _tablet_side_rail(
        im, d, h, theme,
        [("Bugün", True), ("Misafirler", False), ("Walk-in", False),
         ("Mesajlar", False), ("Raporlar", False), ("Daha", False)],
    )
    d = ImageDraw.Draw(im)
    y0 = _tablet_header(d, rail_w, theme, "Bugün", "5 Mayıs 2026 · Resepsiyon · Aydın Y.")

    x0 = rail_w + TABLET_PAD
    content_w = w - x0 - TABLET_PAD

    # Üst özet kartları (4'lü grid)
    summaries = [
        ("12", "Check-in", PRIMARY),
        ("8", "Check-out", INFO),
        ("3", "No-show", WARNING),
        ("87%", "Doluluk", SUCCESS),
    ]
    sw = (content_w - 16 * 3) // 4
    for i, (val, lbl, col) in enumerate(summaries):
        sx = x0 + i * (sw + 16)
        card(d, sx, y0, sw, 200, theme)
        d.text((sx + 24, y0 + 24), val, fill=col, font=font(72, bold=True))
        d.text((sx + 24, y0 + 130), lbl, fill=theme.muted, font=font(28))

    # Master-detail
    md_y = y0 + 240
    md_h = h - md_y - TABLET_PAD
    left_w = int(content_w * 0.58)
    right_x = x0 + left_w + 24
    right_w = content_w - left_w - 24

    # Sol: bekleyen check-in listesi
    card(d, x0, md_y, left_w, md_h, theme)
    d.text((x0 + 32, md_y + 28), "Bekleyen check-in'ler", fill=theme.text, font=font(40, bold=True))
    d.text((x0 + 32, md_y + 88), "Bugünün önceliği · 4 misafir", fill=theme.muted, font=font(26))
    rows = [
        ("Aydın Yılmaz", "Oda 412 · 2 yetişkin", "VIP", VIP, True),
        ("Selin Demir", "Oda 207 · 1 yetişkin", "Erken giriş", INFO, False),
        ("Mert Karaca", "Oda 318 · 2 yet · 1 ç.", "Standart", MUTED, False),
        ("Hannah Becker", "Oda 521 · 2 yetişkin", "Geç kalmış", WARNING, False),
    ]
    ry = md_y + 150
    for name, sub, tag, color, selected in rows:
        # Satır arka planı (seçili olan vurgulanır)
        if selected:
            d.rounded_rectangle((x0 + 16, ry, x0 + left_w - 16, ry + 160), radius=18, fill=theme.surface_alt)
            d.rounded_rectangle((x0 + 16, ry, x0 + 22, ry + 160), radius=4, fill=PRIMARY)
        d.ellipse((x0 + 48, ry + 30, x0 + 148, ry + 130), fill=theme.surface)
        ini = "".join(p[0] for p in name.split()[:2])
        iw, ih = text_size(d, ini, font(40, bold=True))
        d.text((x0 + 98 - iw // 2, ry + 80 - ih // 2), ini, fill=PRIMARY, font=font(40, bold=True))
        d.text((x0 + 180, ry + 30), name, fill=theme.text, font=font(32, bold=True))
        d.text((x0 + 180, ry + 76), sub, fill=theme.muted, font=font(26))
        chip(d, x0 + 180, ry + 112, tag, color=color)
        ry += 175

    # Sağ: seçili misafir detayı
    card(d, right_x, md_y, right_w, md_h, theme)
    d.text((right_x + 28, md_y + 28), "Misafir detayı", fill=theme.muted, font=font(26))
    d.ellipse((right_x + 28, md_y + 80, right_x + 188, md_y + 240), fill=theme.surface_alt)
    iw, ih = text_size(d, "AY", font(64, bold=True))
    d.text((right_x + 108 - iw // 2, md_y + 160 - ih // 2), "AY", fill=PRIMARY, font=font(64, bold=True))
    d.text((right_x + 220, md_y + 92), "Aydın Yılmaz", fill=theme.text, font=font(40, bold=True))
    d.text((right_x + 220, md_y + 148), "Sadakat: Altın · Tekrar misafir", fill=theme.muted, font=font(26))
    chip(d, right_x + 220, md_y + 188, "VIP", color=VIP)

    # Detay grid (2x2)
    items = [
        ("Oda", "412 · Deluxe"),
        ("Konuk", "2 yetişkin"),
        ("Konaklama", "5 – 10 May"),
        ("Toplam", "₺22.400"),
    ]
    iy = md_y + 290
    iw_ = (right_w - 80) // 2
    for i, (lbl, val) in enumerate(items):
        ix = right_x + 28 + (i % 2) * (iw_ + 24)
        iiy = iy + (i // 2) * 110
        d.text((ix, iiy), lbl, fill=theme.muted, font=font(24))
        d.text((ix, iiy + 32), val, fill=theme.text, font=font(32, bold=True))

    # Bugünün notları
    ny = iy + 240
    d.text((right_x + 28, ny), "Bugünün notları", fill=theme.text, font=font(30, bold=True))
    notes = [
        ("Erken giriş onaylandı", SUCCESS),
        ("Yüksek katı tercih ediyor", INFO),
        ("Pasta hazırlığı 19:00", WARNING),
    ]
    for i, (n, c) in enumerate(notes):
        ny2 = ny + 60 + i * 60
        d.ellipse((right_x + 28, ny2 + 12, right_x + 56, ny2 + 40), fill=c)
        d.text((right_x + 76, ny2 + 6), n, fill=theme.text, font=font(26))

    # Aksiyon butonları (alt)
    by = md_y + md_h - 220
    d.rounded_rectangle((right_x + 28, by, right_x + right_w - 28, by + 96), radius=20, fill=PRIMARY)
    f = font(34, bold=True)
    bt = "Check-in başlat"
    bw, bh = text_size(d, bt, f)
    d.text((right_x + right_w // 2 - bw // 2, by + 48 - bh // 2), bt, fill=WHITE, font=f)
    by2 = by + 116
    d.rounded_rectangle((right_x + 28, by2, right_x + right_w - 28, by2 + 86), radius=20, outline=PRIMARY, width=3)
    bt2 = "Misafire mesaj"
    bw2, _ = text_size(d, bt2, f)
    d.text((right_x + right_w // 2 - bw2 // 2, by2 + 42 - bh // 2), bt2, fill=PRIMARY, font=f)
    return im


def _screen_quick_checkin_tablet(w: int, h: int, theme: Theme) -> Image.Image:
    im, d = base_screen(w, h, theme)
    rail_w = _tablet_side_rail(
        im, d, h, theme,
        [("Bugün", False), ("Misafirler", False), ("Walk-in", True),
         ("Mesajlar", False), ("Raporlar", False), ("Daha", False)],
    )
    d = ImageDraw.Draw(im)
    y0 = _tablet_header(d, rail_w, theme, "Hızlı Check-in", "QR + kimlik tarama · Walk-in")

    x0 = rail_w + TABLET_PAD
    content_w = w - x0 - TABLET_PAD
    left_w = int(content_w * 0.56)
    right_x = x0 + left_w + 24
    right_w = content_w - left_w - 24
    panel_h = h - y0 - TABLET_PAD

    # Sol: kamera viewfinder
    card(d, x0, y0, left_w, panel_h, theme, fill=(8, 12, 20), border=theme.border)
    pad = 70
    L = 70
    th = 8
    cy0 = y0
    ch = panel_h
    for (cx_, cy_) in [
        (x0 + pad, cy0 + pad),
        (x0 + left_w - pad, cy0 + pad),
        (x0 + pad, cy0 + ch - pad),
        (x0 + left_w - pad, cy0 + ch - pad),
    ]:
        sx = -1 if cx_ > x0 + left_w // 2 else 1
        sy = -1 if cy_ > cy0 + ch // 2 else 1
        d.line([(cx_, cy_), (cx_ + sx * L, cy_)], fill=PRIMARY, width=th)
        d.line([(cx_, cy_), (cx_, cy_ + sy * L)], fill=PRIMARY, width=th)

    # QR (merkez)
    qs = 540
    qx = x0 + left_w // 2 - qs // 2
    qy = cy0 + ch // 2 - qs // 2 - 60
    d.rectangle((qx, qy, qx + qs, qy + qs), fill=WHITE)
    import random
    random.seed(42)
    cell = qs // 25
    for i in range(25):
        for j in range(25):
            if (i, j) in [(0, 0), (0, 24), (24, 0)]:
                continue
            if random.random() > 0.55:
                d.rectangle(
                    (qx + i * cell, qy + j * cell, qx + (i + 1) * cell, qy + (j + 1) * cell),
                    fill=(15, 23, 42),
                )
    for (cx_, cy_) in [(qx + 8, qy + 8), (qx + qs - 78, qy + 8), (qx + 8, qy + qs - 78)]:
        d.rectangle((cx_, cy_, cx_ + 70, cy_ + 70), outline=(15, 23, 42), width=10)
        d.rectangle((cx_ + 24, cy_ + 24, cx_ + 46, cy_ + 46), fill=(15, 23, 42))

    d.text((x0 + pad, cy0 + ch - pad - 50), "QR'ı çerçeveye hizalayın",
           fill=WHITE, font=font(34, bold=True))
    # Mod düğmeleri
    mb_y = qy + qs + 60
    mods = [("QR", True), ("Kimlik", False), ("Pasaport", False)]
    mx = x0 + left_w // 2 - 350
    for label, active in mods:
        bw_ = 220
        if active:
            d.rounded_rectangle((mx, mb_y, mx + bw_, mb_y + 70), radius=18, fill=PRIMARY)
            color = WHITE
        else:
            d.rounded_rectangle((mx, mb_y, mx + bw_, mb_y + 70), radius=18, outline=WHITE, width=3)
            color = WHITE
        f_ = font(28, bold=True)
        tw_, th_ = text_size(d, label, f_)
        d.text((mx + bw_ // 2 - tw_ // 2, mb_y + 35 - th_ // 2), label, fill=color, font=f_)
        mx += bw_ + 16

    # Sağ: bulunan misafir paneli
    card(d, right_x, y0, right_w, panel_h, theme)
    d.text((right_x + 32, y0 + 28), "Misafir bulundu", fill=SUCCESS, font=font(32, bold=True))
    d.text((right_x + 32, y0 + 80), "Aydın Yılmaz", fill=theme.text, font=font(50, bold=True))
    d.text((right_x + 32, y0 + 150), "TR · Doğum 12.04.1987", fill=theme.muted, font=font(28))
    chip(d, right_x + 32, y0 + 210, "VIP", color=VIP)
    chip(d, right_x + 32 + 130, y0 + 210, "Tekrar misafir", color=INFO)

    # Bilgi blokları
    info = [
        ("Rezervasyon", "RES-2026-0541"),
        ("Oda", "412 · Deluxe"),
        ("Konaklama", "5 – 10 Mayıs 2026"),
        ("Toplam", "₺22.400"),
        ("Ödenmiş", "₺11.200"),
        ("Bakiye", "₺11.200"),
    ]
    iy = y0 + 300
    for i, (lbl, val) in enumerate(info):
        d.text((right_x + 32, iy), lbl, fill=theme.muted, font=font(24))
        d.text((right_x + 32, iy + 32), val, fill=theme.text, font=font(32, bold=True))
        iy += 92

    # Geçmiş konaklama özeti
    hy = iy + 30
    d.text((right_x + 32, hy), "Geçmiş konaklamalar: 4", fill=theme.text, font=font(28, bold=True))
    d.text((right_x + 32, hy + 44), "Son: 12 – 14 Eylül 2025", fill=theme.muted, font=font(26))

    # Aksiyon butonları (alt)
    by = y0 + panel_h - 230
    d.rounded_rectangle((right_x + 32, by, right_x + right_w - 32, by + 100), radius=20, fill=SUCCESS)
    f = font(36, bold=True)
    bt = "Onayla ve check-in"
    bw, bh = text_size(d, bt, f)
    d.text((right_x + right_w // 2 - bw // 2, by + 50 - bh // 2), bt, fill=WHITE, font=f)
    by2 = by + 120
    d.rounded_rectangle((right_x + 32, by2, right_x + right_w - 32, by2 + 86), radius=20, outline=theme.border, width=3)
    bt2 = "Manuel kayıt"
    bw2, _ = text_size(d, bt2, f)
    d.text((right_x + right_w // 2 - bw2 // 2, by2 + 42 - bh // 2), bt2, fill=theme.text, font=f)
    return im


def _screen_housekeeping_tablet(w: int, h: int, theme: Theme) -> Image.Image:
    im, d = base_screen(w, h, theme)
    rail_w = _tablet_side_rail(
        im, d, h, theme,
        [("Odalar", True), ("Hasar", False), ("Stok", False),
         ("Görevler", False), ("Raporlar", False), ("Daha", False)],
    )
    d = ImageDraw.Draw(im)
    y0 = _tablet_header(d, rail_w, theme, "Kat hizmetleri", "Kat 4 · 14 oda · 6 temiz · 3 kirli")

    x0 = rail_w + TABLET_PAD
    content_w = w - x0 - TABLET_PAD
    left_w = int(content_w * 0.62)
    right_x = x0 + left_w + 24
    right_w = content_w - left_w - 24
    panel_h = h - y0 - TABLET_PAD

    # Sol: filtre çipleri + 4 sütun oda grid
    card(d, x0, y0, left_w, panel_h, theme)
    fy = y0 + 24
    fx = x0 + 24
    for label, active in [("Tüm katlar", False), ("4. kat", True), ("Kirli", False),
                          ("Temiz", False), ("Bakım", False)]:
        f = font(26, bold=True)
        tw, th = text_size(d, label, f)
        pad = 22
        bw = tw + pad * 2
        if active:
            d.rounded_rectangle((fx, fy, fx + bw, fy + th + 20), radius=24, fill=PRIMARY)
            d.text((fx + pad, fy + 10), label, fill=WHITE, font=f)
        else:
            d.rounded_rectangle((fx, fy, fx + bw, fy + th + 20), radius=24, outline=theme.border, width=2)
            d.text((fx + pad, fy + 10), label, fill=theme.muted, font=f)
        fx += bw + 14

    rooms = [
        ("401", "Temiz", SUCCESS, "Standart", False),
        ("402", "Kirli", WARNING, "Standart", False),
        ("403", "Temizleniyor", INFO, "Standart", False),
        ("404", "Bakım", DANGER, "Suite", False),
        ("405", "Temiz", SUCCESS, "Standart", False),
        ("406", "Dolu", PRIMARY, "Deluxe", False),
        ("407", "Kirli", WARNING, "Standart", False),
        ("408", "Temiz", SUCCESS, "Standart", False),
        ("409", "İnceleme", INFO, "Standart", False),
        ("410", "Temiz", SUCCESS, "Standart", False),
        ("411", "Kirli", WARNING, "Suite", False),
        ("412", "Dolu", PRIMARY, "Deluxe", True),
        ("414", "Temiz", SUCCESS, "Standart", False),
        ("415", "Bakım", DANGER, "Standart", False),
        ("416", "Temiz", SUCCESS, "Standart", False),
        ("417", "Kirli", WARNING, "Standart", False),
    ]
    cols = 4
    grid_x = x0 + 24
    grid_y = y0 + 110
    cell_w = (left_w - 48 - (cols - 1) * 16) // cols
    cell_h = 220
    for idx, (no, status, color, kind_, selected) in enumerate(rooms):
        col = idx % cols
        row = idx // cols
        cx = grid_x + col * (cell_w + 16)
        cy = grid_y + row * (cell_h + 16)
        if cy + cell_h > y0 + panel_h - 20:
            break
        if selected:
            d.rounded_rectangle((cx, cy, cx + cell_w, cy + cell_h), radius=22, fill=theme.surface_alt, outline=PRIMARY, width=4)
        else:
            card(d, cx, cy, cell_w, cell_h, theme)
        d.ellipse((cx + cell_w - 50, cy + 22, cx + cell_w - 22, cy + 50), fill=color)
        d.text((cx + 24, cy + 24), no, fill=theme.text, font=font(56, bold=True))
        d.text((cx + 24, cy + 110), status, fill=color, font=font(26, bold=True))
        d.text((cx + 24, cy + 152), kind_, fill=theme.muted, font=font(22))

    # Sağ: seçili oda detay paneli
    card(d, right_x, y0, right_w, panel_h, theme)
    d.text((right_x + 28, y0 + 28), "Oda 412", fill=theme.text, font=font(64, bold=True))
    d.text((right_x + 28, y0 + 110), "Deluxe · Kat 4 · Bahçe manzaralı", fill=theme.muted, font=font(28))
    chip(d, right_x + 28, y0 + 160, "Dolu", color=PRIMARY)
    chip(d, right_x + 28 + 140, y0 + 160, "Konuk içeride", color=INFO)

    # Görev listesi
    ty = y0 + 240
    d.text((right_x + 28, ty), "Bekleyen görevler", fill=theme.text, font=font(32, bold=True))
    tasks = [
        ("Yatak değiştir", True),
        ("Banyo dezenfekte", True),
        ("Mini bar yenile", False),
        ("Havlu yenile", False),
        ("Karşılama jesti", False),
    ]
    for i, (task, done) in enumerate(tasks):
        ty2 = ty + 60 + i * 64
        d.rounded_rectangle((right_x + 28, ty2 + 6, right_x + 70, ty2 + 48), radius=8,
                            outline=PRIMARY if done else theme.border, width=3,
                            fill=PRIMARY if done else None)
        if done:
            d.line([(right_x + 38, ty2 + 28), (right_x + 48, ty2 + 38), (right_x + 62, ty2 + 18)],
                   fill=WHITE, width=4)
        d.text((right_x + 90, ty2 + 8), task,
               fill=theme.muted if done else theme.text,
               font=font(28, bold=not done))

    # Atanan personel
    ay = ty + 60 + len(tasks) * 64 + 30
    d.text((right_x + 28, ay), "Atanan personel", fill=theme.text, font=font(28, bold=True))
    d.ellipse((right_x + 28, ay + 50, right_x + 108, ay + 130), fill=theme.surface_alt)
    iw, ih = text_size(d, "ED", font(36, bold=True))
    d.text((right_x + 68 - iw // 2, ay + 90 - ih // 2), "ED", fill=PRIMARY, font=font(36, bold=True))
    d.text((right_x + 130, ay + 56), "Elif Doğan", fill=theme.text, font=font(32, bold=True))
    d.text((right_x + 130, ay + 100), "Tahmini bitiş: 11:45", fill=theme.muted, font=font(24))

    # Aksiyon
    by = y0 + panel_h - 200
    d.rounded_rectangle((right_x + 28, by, right_x + right_w - 28, by + 96), radius=20, fill=SUCCESS)
    f = font(32, bold=True)
    bt = "Temiz olarak işaretle"
    bw, bh = text_size(d, bt, f)
    d.text((right_x + right_w // 2 - bw // 2, by + 48 - bh // 2), bt, fill=WHITE, font=f)
    by2 = by + 116
    d.rounded_rectangle((right_x + 28, by2, right_x + right_w - 28, by2 + 86), radius=20, outline=PRIMARY, width=3)
    bt2 = "Bakım talep et"
    bw2, _ = text_size(d, bt2, f)
    d.text((right_x + right_w // 2 - bw2 // 2, by2 + 42 - bh // 2), bt2, fill=PRIMARY, font=f)
    return im


def _screen_guest_bookings_tablet(w: int, h: int, theme: Theme) -> Image.Image:
    im, d = base_screen(w, h, theme)
    rail_w = _tablet_side_rail(
        im, d, h, theme,
        [("Ana sayfa", False), ("Rezervasyonlar", True), ("Mesajlar", False),
         ("Anahtar", False), ("Hesap", False), ("Daha", False)],
    )
    d = ImageDraw.Draw(im)
    y0 = _tablet_header(d, rail_w, theme, "Rezervasyonlarım", "Aydın · Sadakat: Altın · 4 geçmiş konaklama")

    x0 = rail_w + TABLET_PAD
    content_w = w - x0 - TABLET_PAD
    left_w = int(content_w * 0.42)
    right_x = x0 + left_w + 24
    right_w = content_w - left_w - 24
    panel_h = h - y0 - TABLET_PAD

    # Sol: rezervasyon listesi
    card(d, x0, y0, left_w, panel_h, theme)
    d.text((x0 + 28, y0 + 24), "Rezervasyonlarım", fill=theme.text, font=font(32, bold=True))
    bookings = [
        ("Bodrum Sahil Suite", "10 – 14 May 2026", "Aktif", SUCCESS, True),
        ("Kapadokya Cave Hotel", "22 – 25 Haz 2026", "Onaylandı", PRIMARY, False),
        ("İstanbul Boğaz", "12 – 14 Eyl 2025", "Tamamlandı", MUTED, False),
        ("Antalya Riviera", "01 – 08 Tem 2025", "Tamamlandı", MUTED, False),
        ("İzmir Marina", "14 – 16 Mar 2025", "İptal", DANGER, False),
    ]
    by = y0 + 90
    for title_, date, status, color, selected in bookings:
        if selected:
            d.rounded_rectangle((x0 + 16, by, x0 + left_w - 16, by + 150),
                                radius=20, fill=theme.surface_alt)
            d.rounded_rectangle((x0 + 16, by, x0 + 22, by + 150), radius=4, fill=PRIMARY)
        d.text((x0 + 40, by + 22), title_, fill=theme.text, font=font(30, bold=True))
        d.text((x0 + 40, by + 70), date, fill=theme.muted, font=font(26))
        chip(d, x0 + 40, by + 108, status, color=color)
        by += 165

    # Sağ: aktif rezervasyon detayı
    card(d, right_x, y0, right_w, panel_h, theme)
    chip(d, right_x + 28, y0 + 28, "Aktif", color=SUCCESS)
    d.text((right_x + 28, y0 + 90), "Bodrum Sahil Suite", fill=theme.text, font=font(56, bold=True))
    d.text((right_x + 28, y0 + 170), "10 – 14 Mayıs 2026 · Oda 521 · 2 yetişkin",
           fill=theme.muted, font=font(30))

    # Konaklama bilgi grid (4 sütun)
    items = [
        ("Toplam", "₺18.400"),
        ("Ödenen", "₺9.200"),
        ("Bakiye", "₺9.200"),
        ("Konuk", "2 yetişkin"),
    ]
    iy = y0 + 250
    iw_ = (right_w - 80) // 4
    for i, (lbl, val) in enumerate(items):
        ix = right_x + 28 + i * (iw_ + 12)
        d.rounded_rectangle((ix, iy, ix + iw_, iy + 130), radius=18, fill=theme.surface_alt)
        d.text((ix + 18, iy + 18), lbl, fill=theme.muted, font=font(22))
        d.text((ix + 18, iy + 56), val, fill=theme.text, font=font(34, bold=True))

    # Aksiyonlar
    ay_ = iy + 170
    actions = [("Dijital anahtar", PRIMARY), ("Mesaj gönder", INFO),
               ("Erken giriş", WARNING), ("Faturayı gör", MUTED)]
    ax = right_x + 28
    for label, color in actions:
        f_ = font(26, bold=True)
        tw_, _ = text_size(d, label, f_)
        bw_ = tw_ + 56
        d.rounded_rectangle((ax, ay_, ax + bw_, ay_ + 76), radius=22,
                            fill=color if color != MUTED else None,
                            outline=theme.border if color == MUTED else None,
                            width=2 if color == MUTED else 0)
        d.text((ax + 28, ay_ + 24), label,
               fill=WHITE if color != MUTED else theme.text, font=f_)
        ax += bw_ + 14

    # Konaklama zaman çizelgesi
    ty = ay_ + 130
    d.text((right_x + 28, ty), "Konaklama planı", fill=theme.text, font=font(30, bold=True))
    timeline = [
        ("10 May · 15:00", "Check-in", PRIMARY),
        ("11 May · 09:00", "Kahvaltı dahil", INFO),
        ("12 May · 19:00", "Restoran rezervasyonu", VIP),
        ("13 May · 10:00", "Spa randevusu", SUCCESS),
        ("14 May · 11:00", "Check-out", WARNING),
    ]
    for i, (when, what, color) in enumerate(timeline):
        ly = ty + 60 + i * 60
        d.ellipse((right_x + 28, ly + 12, right_x + 56, ly + 40), fill=color)
        if i < len(timeline) - 1:
            d.line([(right_x + 42, ly + 40), (right_x + 42, ly + 90)], fill=theme.border, width=3)
        d.text((right_x + 76, ly + 6), when, fill=theme.muted, font=font(22))
        d.text((right_x + 220, ly + 4), what, fill=theme.text, font=font(26, bold=True))
    return im


def _screen_digital_key_tablet(w: int, h: int, theme: Theme) -> Image.Image:
    im, d = base_screen(w, h, theme)
    rail_w = _tablet_side_rail(
        im, d, h, theme,
        [("Ana sayfa", False), ("Rezervasyonlar", False), ("Mesajlar", False),
         ("Anahtar", True), ("Hesap", False), ("Daha", False)],
    )
    d = ImageDraw.Draw(im)
    y0 = _tablet_header(d, rail_w, theme, "Dijital anahtar", "Oda 521 · Bodrum Sahil Suite")

    x0 = rail_w + TABLET_PAD
    content_w = w - x0 - TABLET_PAD
    left_w = int(content_w * 0.52)
    right_x = x0 + left_w + 24
    right_w = content_w - left_w - 24
    panel_h = h - y0 - TABLET_PAD

    # Sol: büyük QR kartı
    card(d, x0, y0, left_w, panel_h, theme)
    d.text((x0 + 32, y0 + 28), "QR ile aç", fill=theme.text, font=font(36, bold=True))
    d.text((x0 + 32, y0 + 80), "Kapı okuyucusuna gösterin", fill=theme.muted, font=font(26))
    qs = min(left_w - 120, panel_h - 600)
    qx = x0 + (left_w - qs) // 2
    qy = y0 + 180
    d.rectangle((qx, qy, qx + qs, qy + qs), fill=WHITE)
    import random
    random.seed(7)
    cell = qs // 29
    for i in range(29):
        for j in range(29):
            if random.random() > 0.5:
                d.rectangle(
                    (qx + i * cell, qy + j * cell, qx + (i + 1) * cell, qy + (j + 1) * cell),
                    fill=(15, 23, 42),
                )
    for (cx_, cy_) in [(qx + 8, qy + 8), (qx + qs - 110, qy + 8), (qx + 8, qy + qs - 110)]:
        d.rectangle((cx_, cy_, cx_ + 100, cy_ + 100), outline=(15, 23, 42), width=14)
        d.rectangle((cx_ + 30, cy_ + 30, cx_ + 70, cy_ + 70), fill=(15, 23, 42))

    # Geçerlilik
    iy = qy + qs + 40
    d.text((x0 + 32, iy), "Geçerlilik", fill=theme.muted, font=font(26))
    d.text((x0 + 32, iy + 36), "14 Mayıs 11:00'a kadar", fill=theme.text, font=font(36, bold=True))

    # Aksiyon (alt)
    by = y0 + panel_h - 130
    d.rounded_rectangle((x0 + 32, by, x0 + left_w - 32, by + 96), radius=22, fill=PRIMARY)
    f = font(32, bold=True)
    bt = "Anahtarı paylaş"
    bw, bh = text_size(d, bt, f)
    d.text((x0 + left_w // 2 - bw // 2, by + 48 - bh // 2), bt, fill=WHITE, font=f)

    # Sağ: bilgi paneli
    card(d, right_x, y0, right_w, panel_h, theme)
    d.text((right_x + 28, y0 + 28), "Konaklama özeti", fill=theme.text, font=font(36, bold=True))
    info = [
        ("Otel", "Bodrum Sahil Suite"),
        ("Oda", "521 · Deluxe"),
        ("Konaklama", "10 – 14 Mayıs 2026"),
        ("Konuk", "2 yetişkin"),
        ("Kat", "5 · Asansör B"),
    ]
    iy = y0 + 100
    for lbl, val in info:
        d.text((right_x + 28, iy), lbl, fill=theme.muted, font=font(24))
        d.text((right_x + 28, iy + 32), val, fill=theme.text, font=font(32, bold=True))
        iy += 90

    # Bluetooth NFC bilgi
    by2 = iy + 30
    d.rounded_rectangle((right_x + 28, by2, right_x + right_w - 28, by2 + 200),
                        radius=22, fill=theme.surface_alt)
    d.ellipse((right_x + 60, by2 + 50, right_x + 160, by2 + 150), fill=PRIMARY)
    d.text((right_x + 88, by2 + 76), "B", fill=WHITE, font=font(48, bold=True))
    d.text((right_x + 200, by2 + 50), "Bluetooth ile yaklaşın",
           fill=theme.text, font=font(32, bold=True))
    d.text((right_x + 200, by2 + 100), "Kapı kilidini otomatik açar",
           fill=theme.muted, font=font(26))
    d.text((right_x + 200, by2 + 138), "iOS Cüzdan ve Apple Watch desteği",
           fill=theme.muted, font=font(24))

    # İpuçları
    ty = by2 + 240
    d.text((right_x + 28, ty), "Hızlı ipuçları", fill=theme.text, font=font(28, bold=True))
    tips = [
        "Telefonu kilitliyken bile çalışır",
        "Apple Watch ile bileğinizden açın",
        "Anahtarı eşinizle paylaşabilirsiniz",
    ]
    for i, tip in enumerate(tips):
        ty2 = ty + 50 + i * 56
        d.ellipse((right_x + 28, ty2 + 12, right_x + 50, ty2 + 34), outline=PRIMARY, width=3)
        d.line([(right_x + 34, ty2 + 22), (right_x + 39, ty2 + 28), (right_x + 46, ty2 + 18)],
               fill=PRIMARY, width=3)
        d.text((right_x + 70, ty2 + 6), tip, fill=theme.text, font=font(24))

    # Yardım butonu (alt)
    by3 = y0 + panel_h - 130
    d.rounded_rectangle((right_x + 28, by3, right_x + right_w - 28, by3 + 96),
                        radius=22, outline=PRIMARY, width=3)
    f = font(32, bold=True)
    bt = "Yardım & SSS"
    bw, bh = text_size(d, bt, f)
    d.text((right_x + right_w // 2 - bw // 2, by3 + 48 - bh // 2), bt, fill=PRIMARY, font=f)
    return im


SCREENS = {
    "01_login": ("Tek dokunuşla güvenli giriş", screen_login),
    "02_today": ("Bugünü tek bakışta yönet", screen_today),
    "03_quick_checkin": ("30 saniyede check-in", screen_quick_checkin),
    "04_housekeeping": ("Kat hizmetlerini canlı takip et", screen_housekeeping),
    "05_guest_bookings": ("Misafirin rezervasyonları cebinde", screen_guest_bookings),
    "06_digital_key": ("Dijital anahtarla anında erişim", screen_digital_key),
}

# Mağaza boyutları
# iPhone (mevcut) — telefon çerçevesi
IOS_PHONE_SIZES = {
    "6_7": (1290, 2796),
    "6_5": (1284, 2778),
    "5_5": (1242, 2208),
}
# iPad (yeni) — tablet çerçevesi
IOS_TABLET_SIZES = {
    "12_9": (2048, 2732),
    "11": (1668, 2388),
}
# Android telefon (mevcut) ve tabletler (yeni)
ANDROID_PHONE_SIZE = (1080, 1920)
ANDROID_TABLET_SIZES = {
    "tablet_7": (1200, 1920),
    "tablet_10": (1600, 2560),
}

# Telefon ve tablet için ayrı baz çözünürlükler — frame içinde stretch olmasın diye
PHONE_BASE = (1242, 2688)     # 9:19.5 portrait
TABLET_BASE = (1668, 2224)    # 3:4 portrait


def compose_marketing(
    screen: Image.Image,
    headline: str,
    target_size: tuple[int, int],
    theme: Theme,
    kind: str = "phone",
) -> Image.Image:
    """
    Cihaz mockup + üstte Türkçe başlık + altta cihazın içine yerleşmiş ekran.
    `kind` = "phone" (9:19.5, çentikli) ya da "tablet" (3:4, çentiksiz).
    Tema, başlık metni / arka plan / bezel rengini belirler.
    """
    tw, th_ = target_size
    canvas = Image.new("RGB", (tw, th_), theme.bg)
    d = ImageDraw.Draw(canvas)

    # Hafif gradient arka plan
    grad = Image.new("RGB", (tw, th_), theme.bg)
    gd = ImageDraw.Draw(grad)
    off = theme.grad_top_offset
    for y in range(th_):
        t = y / max(th_ - 1, 1)
        r = max(0, min(255, int(theme.bg[0] + off[0] * (1 - t))))
        g = max(0, min(255, int(theme.bg[1] + off[1] * (1 - t))))
        b = max(0, min(255, int(theme.bg[2] + off[2] * (1 - t))))
        gd.line([(0, y), (tw, y)], fill=(r, g, b))
    canvas.paste(grad)
    d = ImageDraw.Draw(canvas)

    # Başlık alanı (üst %18)
    title_h = int(th_ * 0.18)
    f_title = font(int(tw * 0.06), bold=True)
    # Auto-wrap basitçe iki satır
    words = headline.split()
    lines = [headline]
    if text_size(d, headline, f_title)[0] > tw - 120:
        mid = len(words) // 2
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]
    line_h = text_size(d, "Aj", f_title)[1] + 16
    total_h = line_h * len(lines)
    ty = (title_h - total_h) // 2 + 80
    for ln in lines:
        lw, _ = text_size(d, ln, f_title)
        d.text(((tw - lw) // 2, ty), ln, fill=theme.text, font=f_title)
        ty += line_h
    # Vurgu çubuğu
    d.rounded_rectangle(((tw - 120) // 2, title_h + 50, (tw + 120) // 2, title_h + 62), radius=6, fill=PRIMARY)

    # Cihaz çerçevesi
    device_top = title_h + 110
    device_bottom = th_ - 80
    device_h = device_bottom - device_top
    aspect = (9 / 19.5) if kind == "phone" else (3 / 4)
    device_w = int(device_h * aspect)
    if device_w > tw - 160:
        device_w = tw - 160
        device_h = int(device_w / aspect)
        device_top = (th_ - device_h) // 2 + title_h // 2
        device_bottom = device_top + device_h
    device_x = (tw - device_w) // 2

    # Frame
    if kind == "phone":
        bezel = max(int(device_w * 0.025), 14)
        radius = int(device_w * 0.13)
    else:
        bezel = max(int(device_w * 0.018), 12)
        radius = int(device_w * 0.05)
    # Outer (gümüş veya koyu metalik — temaya göre)
    d.rounded_rectangle(
        (device_x - bezel, device_top - bezel, device_x + device_w + bezel, device_bottom + bezel),
        radius=radius + bezel,
        fill=theme.bezel,
    )
    # Inner ekran çerçevesi
    d.rounded_rectangle((device_x, device_top, device_x + device_w, device_bottom), radius=radius, fill=(0, 0, 0))

    # Ekran içeriği — orijinalden resize
    inner = screen.resize((device_w - 4, device_h - 4), Image.LANCZOS)
    # Yuvarlatılmış maske
    mask = Image.new("L", (device_w - 4, device_h - 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, device_w - 4, device_h - 4), radius=max(radius - 2, 1), fill=255)
    canvas.paste(inner, (device_x + 2, device_top + 2), mask)

    # Çentik (notch) sadece telefonda
    if kind == "phone":
        notch_w = int(device_w * 0.32)
        notch_h = int(device_w * 0.06)
        nx = device_x + (device_w - notch_w) // 2
        d.rounded_rectangle((nx, device_top + 6, nx + notch_w, device_top + 6 + notch_h), radius=notch_h // 2, fill=(0, 0, 0))

    return canvas


def make_screenshots():
    """
    Her flow için iki tema × (telefon + tablet baz) render edilir; ardından her
    mağaza boyutu için cihaz mockup'lı pazarlama görseli üretilir.
    """
    themes = (DARK, LIGHT)
    for key, (headline, builder) in SCREENS.items():
        for theme in themes:
            theme_suffix = "" if theme.name == "dark" else "_light"
            phone_base = builder(*PHONE_BASE, theme, kind="phone")
            tablet_base = builder(*TABLET_BASE, theme, kind="tablet")

            # iOS telefon
            for size_key, sz in IOS_PHONE_SIZES.items():
                out = compose_marketing(phone_base, headline, sz, theme, "phone")
                out.save(SHOTS / "ios" / f"{key}_{size_key}{theme_suffix}.png", "PNG")
            # iOS iPad
            for size_key, sz in IOS_TABLET_SIZES.items():
                out = compose_marketing(tablet_base, headline, sz, theme, "tablet")
                out.save(SHOTS / "ios" / f"{key}_{size_key}{theme_suffix}.png", "PNG")

            # Android telefon
            out = compose_marketing(phone_base, headline, ANDROID_PHONE_SIZE, theme, "phone")
            out.save(SHOTS / "android" / f"{key}_phone{theme_suffix}.png", "PNG")
            # Android tabletler
            for size_key, sz in ANDROID_TABLET_SIZES.items():
                out = compose_marketing(tablet_base, headline, sz, theme, "tablet")
                out.save(SHOTS / "android" / f"{key}_{size_key}{theme_suffix}.png", "PNG")

        print(f"  + {key} — {headline} (dark + light, telefon + tablet)")


def main():
    print("Generating icons …")
    make_icon()
    print("Generating splash …")
    make_splash()
    print("Generating store screenshots …")
    make_screenshots()
    print("Done.")


if __name__ == "__main__":
    main()
