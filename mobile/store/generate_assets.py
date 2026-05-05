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
    ios/<flow>_<size>.png            koyu tema (varsayılan, Türkçe)
        boyutlar: 6_7 (1290x2796), 6_5 (1284x2778), 5_5 (1242x2208),
                  12_9 (2048x2732 — iPad 12.9"), 11 (1668x2388 — iPad 11")
    ios/<flow>_<size>_light.png      light tema (aynı boyutlar)
    ios/en/<flow>_<size>.png         koyu tema, İngilizce yerelleştirme
    ios/en/<flow>_<size>_light.png   light tema, İngilizce yerelleştirme
    android/<flow>_phone.png         1080x1920 telefon — koyu (Türkçe)
    android/<flow>_phone_light.png   1080x1920 telefon — light (Türkçe)
    android/<flow>_tablet_7.png      1200x1920 tablet 7" — koyu (Türkçe)
    android/<flow>_tablet_10.png     1600x2560 tablet 10" — koyu (Türkçe)
    android/<flow>_tablet_*_light.png  light varyantları
    android/en/...                   tüm boyutlar için İngilizce yerelleştirme

Tüm görseller Syroce kurumsal kimliğine (lacivert + mavi vurgu) uygundur ve
hem koyu hem light şemada Türkçe (varsayılan) ya da İngilizce başlıklarla
üretilir. Türkçe çıktıların yolu/içeriği değişmez; İngilizce varyantlar
mevcut yapının altında ayrı `en/` klasörlerine yazılır.
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
(SHOTS / "ios" / "en").mkdir(parents=True, exist_ok=True)
(SHOTS / "android" / "en").mkdir(parents=True, exist_ok=True)

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


# --- Lokalizasyon ----------------------------------------------------------
# Tüm ekranlardaki UI metinleri sabit anahtarlar altında saklanır. Yeni bir
# dil eklemek için aynı anahtarlarla yeni bir COPY_<lang> sözlüğü oluşturup
# LOCALES listesine eklemek yeterlidir.

COPY_TR: dict[str, str] = {
    # Ortak / marka
    "brand.app_name": "Syroce PMS",
    "brand.tagline_short": "Otelinizi cebinizden yönetin",
    "common.email": "E-posta",
    "common.password": "Parola",
    "common.signin": "Giriş yap",
    "common.welcome": "Hoş geldiniz",
    "common.signin_prompt": "Lütfen hesabınızla giriş yapın",
    "common.faceid": "Face ID ile giriş",
    "common.touchid": "Touch ID ile giriş",
    "common.demo": "Demo: info@syroce.com / Syroce2026",

    # Login tablet
    "login.ipad_optimized": "iPad için optimize edilmiş",
    "login.tagline_l1": "Otelinizi cebinizden",
    "login.tagline_l2": "ve iPad'inizden yönetin.",
    "login.feature_split_view_t": "Split View",
    "login.feature_split_view_d": "Misafir listesi ve detayını yan yana",
    "login.feature_pencil_t": "Apple Pencil",
    "login.feature_pencil_d": "Hızlı imza ve notlar",
    "login.feature_keyboard_t": "Klavye kısayolları",
    "login.feature_keyboard_d": "30 saniyede check-in",
    "login.feature_multitask_t": "Çoklu görev",
    "login.feature_multitask_d": "Slide Over desteği",

    # Today
    "today.title": "Bugün",
    "today.subtitle_phone": "5 Mayıs 2026 · Resepsiyon",
    "today.subtitle_tablet": "5 Mayıs 2026 · Resepsiyon · Aydın Y.",
    "today.summary_checkin": "Check-in",
    "today.summary_checkout": "Check-out",
    "today.summary_noshow": "No-show",
    "today.summary_occupancy": "Doluluk",
    "today.pending_title": "Bekleyen check-in'ler",
    "today.pending_sub_phone": "Bugünün önceliği",
    "today.pending_sub_tablet": "Bugünün önceliği · 4 misafir",
    "today.row1_name": "Aydın Yılmaz",
    "today.row1_sub": "Oda 412 · 2 yetişkin",
    "today.row2_name": "Selin Demir",
    "today.row2_sub": "Oda 207 · 1 yetişkin",
    "today.row3_name": "Mert Karaca",
    "today.row3_sub": "Oda 318 · 2 yetişkin · 1 çocuk",
    "today.row3_sub_tablet": "Oda 318 · 2 yet · 1 ç.",
    "today.row4_name": "Hannah Becker",
    "today.row4_sub": "Oda 521 · 2 yetişkin",
    "today.tag_vip": "VIP",
    "today.tag_early": "Erken giriş",
    "today.tag_standard": "Standart",
    "today.tag_late": "Geç kalmış",
    "today.btn_checkin": "Check-in",
    "today.detail_title": "Misafir detayı",
    "today.detail_loyalty": "Sadakat: Altın · Tekrar misafir",
    "today.detail_room_lbl": "Oda",
    "today.detail_room_val": "412 · Deluxe",
    "today.detail_guest_lbl": "Konuk",
    "today.detail_guest_val": "2 yetişkin",
    "today.detail_stay_lbl": "Konaklama",
    "today.detail_stay_val": "5 – 10 May",
    "today.detail_total_lbl": "Toplam",
    "today.detail_total_val": "₺22.400",
    "today.notes_title": "Bugünün notları",
    "today.note1": "Erken giriş onaylandı",
    "today.note2": "Yüksek katı tercih ediyor",
    "today.note3": "Pasta hazırlığı 19:00",
    "today.btn_start_checkin": "Check-in başlat",
    "today.btn_message": "Misafire mesaj",

    # Navigasyon (tab bar + side rail)
    "nav.today": "Bugün",
    "nav.guests": "Misafirler",
    "nav.walkin": "Walk-in",
    "nav.more": "Daha",
    "nav.messages": "Mesajlar",
    "nav.reports": "Raporlar",
    "nav.rooms": "Odalar",
    "nav.damage": "Hasar",
    "nav.stock": "Stok",
    "nav.tasks": "Görevler",
    "nav.home_full": "Ana sayfa",
    "nav.home_short": "Ana",
    "nav.bookings_full": "Rezervasyonlar",
    "nav.bookings_short": "Rez.",
    "nav.messages_short": "Mesaj",
    "nav.key": "Anahtar",
    "nav.account": "Hesap",
    "rail.user_role": "Resepsiyon",

    # Quick check-in
    "qci.title": "Hızlı Check-in",
    "qci.sub_phone": "QR + kimlik tarama",
    "qci.sub_tablet": "QR + kimlik tarama · Walk-in",
    "qci.align": "QR'ı çerçeveye hizalayın",
    "qci.found": "Misafir bulundu",
    "qci.guest_name": "Aydın Yılmaz",
    "qci.guest_meta": "TR · Doğum 12.04.1987",
    "qci.tag_vip": "VIP",
    "qci.tag_returning": "Tekrar misafir",
    "qci.btn_confirm": "Onayla",
    "qci.mode_qr": "QR",
    "qci.mode_id": "Kimlik",
    "qci.mode_passport": "Pasaport",
    "qci.info_res_lbl": "Rezervasyon",
    "qci.info_res_val": "RES-2026-0541",
    "qci.info_room_lbl": "Oda",
    "qci.info_room_val": "412 · Deluxe",
    "qci.info_stay_lbl": "Konaklama",
    "qci.info_stay_val": "5 – 10 Mayıs 2026",
    "qci.info_total_lbl": "Toplam",
    "qci.info_total_val": "₺22.400",
    "qci.info_paid_lbl": "Ödenmiş",
    "qci.info_paid_val": "₺11.200",
    "qci.info_balance_lbl": "Bakiye",
    "qci.info_balance_val": "₺11.200",
    "qci.history_count": "Geçmiş konaklamalar: 4",
    "qci.history_last": "Son: 12 – 14 Eylül 2025",
    "qci.btn_confirm_checkin": "Onayla ve check-in",
    "qci.btn_manual": "Manuel kayıt",

    # Housekeeping
    "hk.title": "Kat hizmetleri",
    "hk.sub_phone": "Kat 4 · 14 oda",
    "hk.sub_tablet": "Kat 4 · 14 oda · 6 temiz · 3 kirli",
    "hk.chip_all": "Tüm katlar",
    "hk.chip_floor4": "4. kat",
    "hk.chip_dirty": "Kirli",
    "hk.chip_clean": "Temiz",
    "hk.chip_maintenance": "Bakım",
    "hk.status_clean": "Temiz",
    "hk.status_dirty": "Kirli",
    "hk.status_cleaning": "Temizleniyor",
    "hk.status_maintenance": "Bakım",
    "hk.status_occupied": "Dolu",
    "hk.status_inspection": "İnceleme",
    "hk.kind_standard": "Standart",
    "hk.kind_suite": "Suite",
    "hk.kind_deluxe": "Deluxe",
    "hk.detail_room": "Oda 412",
    "hk.detail_meta": "Deluxe · Kat 4 · Bahçe manzaralı",
    "hk.chip_occupied": "Dolu",
    "hk.chip_guest_in": "Konuk içeride",
    "hk.tasks_title": "Bekleyen görevler",
    "hk.task1": "Yatak değiştir",
    "hk.task2": "Banyo dezenfekte",
    "hk.task3": "Mini bar yenile",
    "hk.task4": "Havlu yenile",
    "hk.task5": "Karşılama jesti",
    "hk.assigned": "Atanan personel",
    "hk.staff_name": "Elif Doğan",
    "hk.staff_eta": "Tahmini bitiş: 11:45",
    "hk.btn_mark_clean": "Temiz olarak işaretle",
    "hk.btn_request_maintenance": "Bakım talep et",

    # Guest bookings
    "gb.title": "Rezervasyonlarım",
    "gb.sub_phone": "Aydın · Sadakat: Altın",
    "gb.sub_tablet": "Aydın · Sadakat: Altın · 4 geçmiş konaklama",
    "gb.list_title": "Rezervasyonlarım",
    "gb.status_active": "Aktif",
    "gb.status_confirmed": "Onaylandı",
    "gb.status_completed": "Tamamlandı",
    "gb.status_cancelled": "İptal",
    "gb.hotel_bodrum": "Bodrum Sahil Suite",
    "gb.hotel_kapadokya": "Kapadokya Cave Hotel",
    "gb.hotel_istanbul": "İstanbul Boğaz",
    "gb.hotel_antalya": "Antalya Riviera",
    "gb.hotel_izmir": "İzmir Marina",
    "gb.dates_active_phone": "10 – 14 Mayıs 2026",
    "gb.dates_active_tablet": "10 – 14 Mayıs 2026 · Oda 521 · 2 yetişkin",
    "gb.dates_active_short": "10 – 14 May 2026",
    "gb.dates_kapadokya": "22 – 25 Haz 2026",
    "gb.dates_istanbul": "12 – 14 Eyl 2025",
    "gb.dates_istanbul_full": "12 – 14 Eylül 2025",
    "gb.dates_antalya": "01 – 08 Tem 2025",
    "gb.dates_antalya_full": "01 – 08 Temmuz 2025",
    "gb.dates_izmir": "14 – 16 Mar 2025",
    "gb.room_sub": "Oda 521 · 2 yetişkin",
    "gb.lbl_total": "Toplam",
    "gb.lbl_paid": "Ödenen",
    "gb.lbl_balance": "Bakiye",
    "gb.lbl_guest": "Konuk",
    "gb.val_count2": "2",
    "gb.val_guest2_full": "2 yetişkin",
    "gb.act_key": "Dijital anahtar",
    "gb.act_message": "Mesaj gönder",
    "gb.act_early": "Erken giriş",
    "gb.act_invoice": "Faturayı gör",
    "gb.past_title": "Geçmiş konaklamalar",
    "gb.timeline_title": "Konaklama planı",
    "gb.tl_checkin_when": "10 May · 15:00",
    "gb.tl_checkin_what": "Check-in",
    "gb.tl_breakfast_when": "11 May · 09:00",
    "gb.tl_breakfast_what": "Kahvaltı dahil",
    "gb.tl_dinner_when": "12 May · 19:00",
    "gb.tl_dinner_what": "Restoran rezervasyonu",
    "gb.tl_spa_when": "13 May · 10:00",
    "gb.tl_spa_what": "Spa randevusu",
    "gb.tl_checkout_when": "14 May · 11:00",
    "gb.tl_checkout_what": "Check-out",

    # Digital key
    "dk.title": "Dijital anahtar",
    "dk.sub": "Oda 521 · Bodrum Sahil Suite",
    "dk.valid_lbl": "Geçerlilik",
    "dk.valid_val": "14 Mayıs 11:00'a kadar",
    "dk.bt_title": "Bluetooth ile yaklaşın",
    "dk.bt_sub": "Kapı kilidini otomatik açar",
    "dk.btn_share": "Anahtarı paylaş",
    "dk.btn_help": "Yardım",
    "dk.btn_help_long": "Yardım & SSS",
    "dk.qr_title": "QR ile aç",
    "dk.qr_sub": "Kapı okuyucusuna gösterin",
    "dk.summary": "Konaklama özeti",
    "dk.info_hotel_lbl": "Otel",
    "dk.info_hotel_val": "Bodrum Sahil Suite",
    "dk.info_room_lbl": "Oda",
    "dk.info_room_val": "521 · Deluxe",
    "dk.info_stay_lbl": "Konaklama",
    "dk.info_stay_val": "10 – 14 Mayıs 2026",
    "dk.info_guest_lbl": "Konuk",
    "dk.info_guest_val": "2 yetişkin",
    "dk.info_floor_lbl": "Kat",
    "dk.info_floor_val": "5 · Asansör B",
    "dk.bt_extra": "iOS Cüzdan ve Apple Watch desteği",
    "dk.tips_title": "Hızlı ipuçları",
    "dk.tip1": "Telefonu kilitliyken bile çalışır",
    "dk.tip2": "Apple Watch ile bileğinizden açın",
    "dk.tip3": "Anahtarı eşinizle paylaşabilirsiniz",

    # Mağaza başlıkları
    "hl.01_login": "Tek dokunuşla güvenli giriş",
    "hl.02_today": "Bugünü tek bakışta yönet",
    "hl.03_quick_checkin": "30 saniyede check-in",
    "hl.04_housekeeping": "Kat hizmetlerini canlı takip et",
    "hl.05_guest_bookings": "Misafirin rezervasyonları cebinde",
    "hl.06_digital_key": "Dijital anahtarla anında erişim",
}

COPY_EN: dict[str, str] = {
    # Common / brand
    "brand.app_name": "Syroce PMS",
    "brand.tagline_short": "Manage your hotel from your pocket",
    "common.email": "Email",
    "common.password": "Password",
    "common.signin": "Sign in",
    "common.welcome": "Welcome",
    "common.signin_prompt": "Please sign in with your account",
    "common.faceid": "Sign in with Face ID",
    "common.touchid": "Sign in with Touch ID",
    "common.demo": "Demo: info@syroce.com / Syroce2026",

    # Login tablet
    "login.ipad_optimized": "Optimized for iPad",
    "login.tagline_l1": "Manage your hotel from",
    "login.tagline_l2": "your pocket and iPad.",
    "login.feature_split_view_t": "Split View",
    "login.feature_split_view_d": "Guest list and details side by side",
    "login.feature_pencil_t": "Apple Pencil",
    "login.feature_pencil_d": "Quick signatures and notes",
    "login.feature_keyboard_t": "Keyboard shortcuts",
    "login.feature_keyboard_d": "Check in within 30 seconds",
    "login.feature_multitask_t": "Multitasking",
    "login.feature_multitask_d": "Slide Over support",

    # Today
    "today.title": "Today",
    "today.subtitle_phone": "May 5, 2026 · Reception",
    "today.subtitle_tablet": "May 5, 2026 · Reception · Aydın Y.",
    "today.summary_checkin": "Check-in",
    "today.summary_checkout": "Check-out",
    "today.summary_noshow": "No-show",
    "today.summary_occupancy": "Occupancy",
    "today.pending_title": "Pending check-ins",
    "today.pending_sub_phone": "Today's priority",
    "today.pending_sub_tablet": "Today's priority · 4 guests",
    "today.row1_name": "Aydın Yılmaz",
    "today.row1_sub": "Room 412 · 2 adults",
    "today.row2_name": "Selin Demir",
    "today.row2_sub": "Room 207 · 1 adult",
    "today.row3_name": "Mert Karaca",
    "today.row3_sub": "Room 318 · 2 adults · 1 child",
    "today.row3_sub_tablet": "Room 318 · 2 ad · 1 ch",
    "today.row4_name": "Hannah Becker",
    "today.row4_sub": "Room 521 · 2 adults",
    "today.tag_vip": "VIP",
    "today.tag_early": "Early check-in",
    "today.tag_standard": "Standard",
    "today.tag_late": "Late",
    "today.btn_checkin": "Check-in",
    "today.detail_title": "Guest details",
    "today.detail_loyalty": "Loyalty: Gold · Returning guest",
    "today.detail_room_lbl": "Room",
    "today.detail_room_val": "412 · Deluxe",
    "today.detail_guest_lbl": "Guests",
    "today.detail_guest_val": "2 adults",
    "today.detail_stay_lbl": "Stay",
    "today.detail_stay_val": "May 5 – 10",
    "today.detail_total_lbl": "Total",
    "today.detail_total_val": "₺22,400",
    "today.notes_title": "Today's notes",
    "today.note1": "Early check-in approved",
    "today.note2": "Prefers a high floor",
    "today.note3": "Cake setup at 19:00",
    "today.btn_start_checkin": "Start check-in",
    "today.btn_message": "Message guest",

    # Navigation
    "nav.today": "Today",
    "nav.guests": "Guests",
    "nav.walkin": "Walk-in",
    "nav.more": "More",
    "nav.messages": "Messages",
    "nav.reports": "Reports",
    "nav.rooms": "Rooms",
    "nav.damage": "Damage",
    "nav.stock": "Inventory",
    "nav.tasks": "Tasks",
    "nav.home_full": "Home",
    "nav.home_short": "Home",
    "nav.bookings_full": "Bookings",
    "nav.bookings_short": "Bkgs",
    "nav.messages_short": "Msgs",
    "nav.key": "Key",
    "nav.account": "Account",
    "rail.user_role": "Reception",

    # Quick check-in
    "qci.title": "Quick Check-in",
    "qci.sub_phone": "QR + ID scan",
    "qci.sub_tablet": "QR + ID scan · Walk-in",
    "qci.align": "Align QR within the frame",
    "qci.found": "Guest found",
    "qci.guest_name": "Aydın Yılmaz",
    "qci.guest_meta": "TR · DOB 12.04.1987",
    "qci.tag_vip": "VIP",
    "qci.tag_returning": "Returning guest",
    "qci.btn_confirm": "Confirm",
    "qci.mode_qr": "QR",
    "qci.mode_id": "ID",
    "qci.mode_passport": "Passport",
    "qci.info_res_lbl": "Booking",
    "qci.info_res_val": "RES-2026-0541",
    "qci.info_room_lbl": "Room",
    "qci.info_room_val": "412 · Deluxe",
    "qci.info_stay_lbl": "Stay",
    "qci.info_stay_val": "May 5 – 10, 2026",
    "qci.info_total_lbl": "Total",
    "qci.info_total_val": "₺22,400",
    "qci.info_paid_lbl": "Paid",
    "qci.info_paid_val": "₺11,200",
    "qci.info_balance_lbl": "Balance",
    "qci.info_balance_val": "₺11,200",
    "qci.history_count": "Past stays: 4",
    "qci.history_last": "Last: Sep 12 – 14, 2025",
    "qci.btn_confirm_checkin": "Confirm & check-in",
    "qci.btn_manual": "Manual entry",

    # Housekeeping
    "hk.title": "Housekeeping",
    "hk.sub_phone": "Floor 4 · 14 rooms",
    "hk.sub_tablet": "Floor 4 · 14 rooms · 6 clean · 3 dirty",
    "hk.chip_all": "All floors",
    "hk.chip_floor4": "Floor 4",
    "hk.chip_dirty": "Dirty",
    "hk.chip_clean": "Clean",
    "hk.chip_maintenance": "Maintenance",
    "hk.status_clean": "Clean",
    "hk.status_dirty": "Dirty",
    "hk.status_cleaning": "Cleaning",
    "hk.status_maintenance": "Maintenance",
    "hk.status_occupied": "Occupied",
    "hk.status_inspection": "Inspection",
    "hk.kind_standard": "Standard",
    "hk.kind_suite": "Suite",
    "hk.kind_deluxe": "Deluxe",
    "hk.detail_room": "Room 412",
    "hk.detail_meta": "Deluxe · Floor 4 · Garden view",
    "hk.chip_occupied": "Occupied",
    "hk.chip_guest_in": "Guest inside",
    "hk.tasks_title": "Pending tasks",
    "hk.task1": "Change bed linen",
    "hk.task2": "Disinfect bathroom",
    "hk.task3": "Restock minibar",
    "hk.task4": "Replace towels",
    "hk.task5": "Welcome amenity",
    "hk.assigned": "Assigned staff",
    "hk.staff_name": "Elif Doğan",
    "hk.staff_eta": "Estimated end: 11:45",
    "hk.btn_mark_clean": "Mark as clean",
    "hk.btn_request_maintenance": "Request maintenance",

    # Guest bookings
    "gb.title": "My bookings",
    "gb.sub_phone": "Aydın · Loyalty: Gold",
    "gb.sub_tablet": "Aydın · Loyalty: Gold · 4 past stays",
    "gb.list_title": "My bookings",
    "gb.status_active": "Active",
    "gb.status_confirmed": "Confirmed",
    "gb.status_completed": "Completed",
    "gb.status_cancelled": "Cancelled",
    "gb.hotel_bodrum": "Bodrum Sahil Suite",
    "gb.hotel_kapadokya": "Kapadokya Cave Hotel",
    "gb.hotel_istanbul": "İstanbul Boğaz",
    "gb.hotel_antalya": "Antalya Riviera",
    "gb.hotel_izmir": "İzmir Marina",
    "gb.dates_active_phone": "May 10 – 14, 2026",
    "gb.dates_active_tablet": "May 10 – 14, 2026 · Room 521 · 2 adults",
    "gb.dates_active_short": "May 10 – 14, 2026",
    "gb.dates_kapadokya": "Jun 22 – 25, 2026",
    "gb.dates_istanbul": "Sep 12 – 14, 2025",
    "gb.dates_istanbul_full": "Sep 12 – 14, 2025",
    "gb.dates_antalya": "Jul 1 – 8, 2025",
    "gb.dates_antalya_full": "Jul 1 – 8, 2025",
    "gb.dates_izmir": "Mar 14 – 16, 2025",
    "gb.room_sub": "Room 521 · 2 adults",
    "gb.lbl_total": "Total",
    "gb.lbl_paid": "Paid",
    "gb.lbl_balance": "Balance",
    "gb.lbl_guest": "Guests",
    "gb.val_count2": "2",
    "gb.val_guest2_full": "2 adults",
    "gb.act_key": "Digital key",
    "gb.act_message": "Send message",
    "gb.act_early": "Early check-in",
    "gb.act_invoice": "View invoice",
    "gb.past_title": "Past stays",
    "gb.timeline_title": "Stay timeline",
    "gb.tl_checkin_when": "May 10 · 15:00",
    "gb.tl_checkin_what": "Check-in",
    "gb.tl_breakfast_when": "May 11 · 09:00",
    "gb.tl_breakfast_what": "Breakfast included",
    "gb.tl_dinner_when": "May 12 · 19:00",
    "gb.tl_dinner_what": "Restaurant reservation",
    "gb.tl_spa_when": "May 13 · 10:00",
    "gb.tl_spa_what": "Spa appointment",
    "gb.tl_checkout_when": "May 14 · 11:00",
    "gb.tl_checkout_what": "Check-out",

    # Digital key
    "dk.title": "Digital key",
    "dk.sub": "Room 521 · Bodrum Sahil Suite",
    "dk.valid_lbl": "Valid until",
    "dk.valid_val": "Until May 14, 11:00",
    "dk.bt_title": "Tap with Bluetooth",
    "dk.bt_sub": "Unlocks the door automatically",
    "dk.btn_share": "Share key",
    "dk.btn_help": "Help",
    "dk.btn_help_long": "Help & FAQ",
    "dk.qr_title": "Open with QR",
    "dk.qr_sub": "Show to the door reader",
    "dk.summary": "Stay summary",
    "dk.info_hotel_lbl": "Hotel",
    "dk.info_hotel_val": "Bodrum Sahil Suite",
    "dk.info_room_lbl": "Room",
    "dk.info_room_val": "521 · Deluxe",
    "dk.info_stay_lbl": "Stay",
    "dk.info_stay_val": "May 10 – 14, 2026",
    "dk.info_guest_lbl": "Guests",
    "dk.info_guest_val": "2 adults",
    "dk.info_floor_lbl": "Floor",
    "dk.info_floor_val": "5 · Elevator B",
    "dk.bt_extra": "iOS Wallet and Apple Watch support",
    "dk.tips_title": "Quick tips",
    "dk.tip1": "Works even when the phone is locked",
    "dk.tip2": "Open from your wrist with Apple Watch",
    "dk.tip3": "Share the key with your partner",

    # Store headlines
    "hl.01_login": "Secure sign-in with one tap",
    "hl.02_today": "Manage today at a glance",
    "hl.03_quick_checkin": "Check in in 30 seconds",
    "hl.04_housekeeping": "Track housekeeping in real time",
    "hl.05_guest_bookings": "Guest bookings in your pocket",
    "hl.06_digital_key": "Instant access with the digital key",
}


@dataclass(frozen=True)
class Locale:
    code: str          # "tr", "en"
    out_subdir: str    # "" → mevcut Türkçe konumu; "en" → ios/en, android/en
    copy: dict


LOCALES: tuple[Locale, ...] = (
    Locale(code="tr", out_subdir="", copy=COPY_TR),
    Locale(code="en", out_subdir="en", copy=COPY_EN),
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
        # Splash görseli uygulamanın açılışında kullanılır; varsayılan dil olan
        # Türkçe metni korur (mağaza yerelleştirmesi sadece screenshot'ları
        # etkiler).
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
def screen_login(w, h, theme: Theme, c: dict, kind: str = "phone"):
    if kind == "tablet":
        return _screen_login_tablet(w, h, theme, c)
    im, d = base_screen(w, h, theme)
    status_bar(d, w, theme)
    # logo merkez üst
    draw_logo_mark(im, w // 2, h // 2 - 480, 260)
    d_ = ImageDraw.Draw(im)
    title = c["brand.app_name"]
    sub = c["brand.tagline_short"]
    tw, _ = text_size(d_, title, font(64, bold=True))
    sw_, _ = text_size(d_, sub, font(34))
    d_.text(((w - tw) // 2, h // 2 - 290), title, fill=theme.text, font=font(64, bold=True))
    d_.text(((w - sw_) // 2, h // 2 - 210), sub, fill=theme.muted, font=font(34))

    # Form kartı
    cx, cy, cw, ch = 80, h // 2 - 100, w - 160, 760
    card(d_, cx, cy, cw, ch, theme)
    d_.text((cx + 40, cy + 40), c["common.email"], fill=theme.muted, font=font(28))
    d_.rounded_rectangle((cx + 40, cy + 80, cx + cw - 40, cy + 160), radius=14, fill=theme.surface_alt)
    d_.text((cx + 60, cy + 102), "info@syroce.com", fill=theme.text, font=font(34))
    d_.text((cx + 40, cy + 200), c["common.password"], fill=theme.muted, font=font(28))
    d_.rounded_rectangle((cx + 40, cy + 240, cx + cw - 40, cy + 320), radius=14, fill=theme.surface_alt)
    d_.text((cx + 60, cy + 262), "•••••••••••", fill=theme.text, font=font(34))
    # buton
    d_.rounded_rectangle((cx + 40, cy + 400, cx + cw - 40, cy + 500), radius=18, fill=PRIMARY)
    f = font(38, bold=True)
    btxt = c["common.signin"]
    btw, bth = text_size(d_, btxt, f)
    d_.text((cx + cw // 2 - btw // 2, cy + 430), btxt, fill=WHITE, font=f)
    # Biyometri
    d_.rounded_rectangle((cx + 40, cy + 540, cx + cw - 40, cy + 640), radius=18, outline=PRIMARY, width=3)
    btxt2 = c["common.faceid"]
    btw2, _ = text_size(d_, btxt2, f)
    d_.text((cx + cw // 2 - btw2 // 2, cy + 570), btxt2, fill=PRIMARY, font=f)

    d_.text((80, h - 200), c["common.demo"], fill=theme.muted, font=font(26))
    return im


def screen_today(w, h, theme: Theme, c: dict, kind: str = "phone"):
    if kind == "tablet":
        return _screen_today_tablet(w, h, theme, c)
    im, d = base_screen(w, h, theme)
    status_bar(d, w, theme)
    app_header(d, w, theme, c["today.title"], c["today.subtitle_phone"])

    # Özet kartları (3'lü grid)
    y = 240
    box_w = (w - 48 * 2 - 32) // 3
    summaries = [
        ("12", c["today.summary_checkin"], PRIMARY),
        ("8", c["today.summary_checkout"], INFO),
        ("3", c["today.summary_noshow"], WARNING),
    ]
    for i, (val, lbl, col) in enumerate(summaries):
        x = 48 + i * (box_w + 16)
        card(d, x, y, box_w, 200, theme)
        d.text((x + 24, y + 24), val, fill=col, font=font(72, bold=True))
        d.text((x + 24, y + 130), lbl, fill=theme.muted, font=font(28))

    # Bölüm başlığı
    y2 = y + 240
    d.text((48, y2), c["today.pending_title"], fill=theme.text, font=font(40, bold=True))
    d.text((48, y2 + 60), c["today.pending_sub_phone"], fill=theme.muted, font=font(28))

    # Liste
    rows = [
        (c["today.row1_name"], c["today.row1_sub"], c["today.tag_vip"], VIP),
        (c["today.row2_name"], c["today.row2_sub"], c["today.tag_early"], INFO),
        (c["today.row3_name"], c["today.row3_sub"], c["today.tag_standard"], MUTED),
        (c["today.row4_name"], c["today.row4_sub"], c["today.tag_late"], WARNING),
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
        bt = c["today.btn_checkin"]
        bw, bh = text_size(d, bt, f)
        d.text((w - 200 - bw // 2, ry + 100 - bh // 2), bt, fill=WHITE, font=f)
        ry += 200

    # FAB
    d.ellipse((w - 200, h - 360, w - 60, h - 220), fill=PRIMARY)
    d.text((w - 158, h - 332), "+", fill=WHITE, font=font(72, bold=True))

    tab_bar(d, w, h, theme, [
        (c["nav.today"], True),
        (c["nav.guests"], False),
        (c["nav.walkin"], False),
        (c["nav.more"], False),
    ])
    return im


def screen_quick_checkin(w, h, theme: Theme, c: dict, kind: str = "phone"):
    if kind == "tablet":
        return _screen_quick_checkin_tablet(w, h, theme, c)
    im, d = base_screen(w, h, theme)
    status_bar(d, w, theme)
    app_header(d, w, theme, c["qci.title"], c["qci.sub_phone"])

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
    d.text((48 + pad, cy0 + ch - pad - 80), c["qci.align"], fill=WHITE, font=font(32, bold=True))

    # Alt panel
    py = cy0 + ch + 40
    card(d, 48, py, w - 96, 300, theme)
    d.text((48 + 32, py + 28), c["qci.found"], fill=SUCCESS, font=font(32, bold=True))
    d.text((48 + 32, py + 80), c["qci.guest_name"], fill=theme.text, font=font(44, bold=True))
    d.text((48 + 32, py + 140), c["qci.guest_meta"], fill=theme.muted, font=font(28))
    chip(d, 48 + 32, py + 200, c["qci.tag_vip"], color=VIP)
    chip(d, 48 + 32 + 130, py + 200, c["qci.tag_returning"], color=INFO)
    # Onay butonu
    d.rounded_rectangle((w - 360, py + 100, w - 80, py + 200), radius=18, fill=SUCCESS)
    bt = c["qci.btn_confirm"]
    f = font(34, bold=True)
    bw, bh = text_size(d, bt, f)
    d.text((w - 220 - bw // 2, py + 150 - bh // 2), bt, fill=WHITE, font=f)

    tab_bar(d, w, h, theme, [
        (c["nav.today"], False),
        (c["nav.guests"], False),
        (c["nav.walkin"], True),
        (c["nav.more"], False),
    ])
    return im


def screen_housekeeping(w, h, theme: Theme, c: dict, kind: str = "phone"):
    if kind == "tablet":
        return _screen_housekeeping_tablet(w, h, theme, c)
    im, d = base_screen(w, h, theme)
    status_bar(d, w, theme)
    app_header(d, w, theme, c["hk.title"], c["hk.sub_phone"])

    # Filtre çipleri
    y = 240
    x = 48
    chips_def = [
        (c["hk.chip_all"], False),
        (c["hk.chip_floor4"], True),
        (c["hk.chip_dirty"], False),
        (c["hk.chip_clean"], False),
        (c["hk.chip_maintenance"], False),
    ]
    for label, active in chips_def:
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
        ("401", c["hk.status_clean"], SUCCESS),
        ("402", c["hk.status_dirty"], WARNING),
        ("403", c["hk.status_cleaning"], INFO),
        ("404", c["hk.status_maintenance"], DANGER),
        ("405", c["hk.status_clean"], SUCCESS),
        ("406", c["hk.status_occupied"], PRIMARY),
        ("407", c["hk.status_dirty"], WARNING),
        ("408", c["hk.status_clean"], SUCCESS),
        ("409", c["hk.status_inspection"], INFO),
        ("410", c["hk.status_clean"], SUCCESS),
        ("411", c["hk.status_dirty"], WARNING),
        ("412", c["hk.status_occupied"], PRIMARY),
        ("414", c["hk.status_clean"], SUCCESS),
        ("415", c["hk.status_maintenance"], DANGER),
        ("416", c["hk.status_clean"], SUCCESS),
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
        d.text((cx + 28, cy + 160), c["hk.kind_standard"], fill=theme.muted, font=font(24))

    tab_bar(d, w, h, theme, [
        (c["nav.rooms"], True),
        (c["nav.damage"], False),
        (c["nav.more"], False),
    ])
    return im


def screen_guest_bookings(w, h, theme: Theme, c: dict, kind: str = "phone"):
    if kind == "tablet":
        return _screen_guest_bookings_tablet(w, h, theme, c)
    im, d = base_screen(w, h, theme)
    status_bar(d, w, theme)
    app_header(d, w, theme, c["gb.title"], c["gb.sub_phone"])

    # Aktif rezervasyon
    y = 260
    card(d, 48, y, w - 96, 600, theme)
    chip(d, 80, y + 32, c["gb.status_active"], color=SUCCESS)
    d.text((80, y + 100), c["gb.hotel_bodrum"], fill=theme.text, font=font(46, bold=True))
    d.text((80, y + 170), c["gb.dates_active_phone"], fill=theme.muted, font=font(32))
    d.text((80, y + 220), c["gb.room_sub"], fill=theme.muted, font=font(28))

    # Detay grid
    items = [
        (c["gb.lbl_total"], "₺18.400"),
        (c["gb.lbl_paid"], "₺9.200"),
        (c["gb.lbl_balance"], "₺9.200"),
        (c["gb.lbl_guest"], c["gb.val_count2"]),
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
    for i, (label, color) in enumerate([
        (c["gb.act_key"], PRIMARY),
        (c["gb.act_message"], INFO),
        (c["gb.act_early"], WARNING),
    ]):
        f = font(26, bold=True)
        tw, _ = text_size(d, label, f)
        bw = tw + 60
        d.rounded_rectangle((bx, by, bx + bw, by + 70), radius=20, fill=color)
        d.text((bx + 30, by + 22), label, fill=WHITE, font=f)
        bx += bw + 16

    # Geçmiş
    y2 = y + 660
    d.text((48, y2), c["gb.past_title"], fill=theme.text, font=font(38, bold=True))
    past = [
        (c["gb.hotel_istanbul"], c["gb.dates_istanbul_full"], c["gb.status_completed"]),
        (c["gb.hotel_antalya"], c["gb.dates_antalya_full"], c["gb.status_completed"]),
    ]
    py = y2 + 80
    for title, date, status in past:
        card(d, 48, py, w - 96, 160, theme)
        d.text((80, py + 30), title, fill=theme.text, font=font(34, bold=True))
        d.text((80, py + 80), date, fill=theme.muted, font=font(28))
        d.text((80, py + 118), status, fill=SUCCESS, font=font(26, bold=True))
        py += 180

    tab_bar(d, w, h, theme, [
        (c["nav.home_short"], False),
        (c["nav.bookings_short"], True),
        (c["nav.messages_short"], False),
        (c["nav.more"], False),
    ])
    return im


def screen_digital_key(w, h, theme: Theme, c: dict, kind: str = "phone"):
    if kind == "tablet":
        return _screen_digital_key_tablet(w, h, theme, c)
    im, d = base_screen(w, h, theme)
    status_bar(d, w, theme)
    app_header(d, w, theme, c["dk.title"], c["dk.sub"])

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
    d.text((qx, iy), c["dk.valid_lbl"], fill=theme.muted, font=font(28))
    d.text((qx, iy + 40), c["dk.valid_val"], fill=theme.text, font=font(38, bold=True))

    # Bluetooth/NFC indicator
    d.rounded_rectangle((48 + 60, cy0 + ch - 220, w - 48 - 60, cy0 + ch - 80), radius=24, fill=theme.surface_alt)
    d.ellipse((48 + 100, cy0 + ch - 200, 48 + 200, cy0 + ch - 100), fill=PRIMARY)
    d.text((48 + 230, cy0 + ch - 195), c["dk.bt_title"], fill=theme.text, font=font(34, bold=True))
    d.text((48 + 230, cy0 + ch - 145), c["dk.bt_sub"], fill=theme.muted, font=font(26))

    # Aksiyon butonları
    by = cy0 + ch + 40
    d.rounded_rectangle((48, by, w // 2 - 16, by + 110), radius=22, fill=PRIMARY)
    bt = c["dk.btn_share"]
    f = font(32, bold=True)
    bw, bh = text_size(d, bt, f)
    d.text(((w // 2 - 16) // 2 + 24 - bw // 2, by + 55 - bh // 2), bt, fill=WHITE, font=f)

    d.rounded_rectangle((w // 2 + 16, by, w - 48, by + 110), radius=22, outline=PRIMARY, width=4)
    bt2 = c["dk.btn_help"]
    bw2, _ = text_size(d, bt2, f)
    d.text(((w // 2 + 16 + w - 48) // 2 - bw2 // 2, by + 55 - bh // 2), bt2, fill=PRIMARY, font=f)

    tab_bar(d, w, h, theme, [
        (c["nav.home_short"], False),
        (c["nav.bookings_short"], False),
        (c["nav.key"], True),
        (c["nav.more"], False),
    ])
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
    c: dict,
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
    d.text((140, uy + 46), c["rail.user_role"], fill=theme.muted, font=font(22))
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


def _screen_login_tablet(w: int, h: int, theme: Theme, c: dict) -> Image.Image:
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
    d.text((400, 220), c["brand.app_name"], fill=theme.text, font=font(72, bold=True))
    d.text((400, 320), c["login.ipad_optimized"], fill=theme.muted, font=font(34))
    # Slogan
    d.text((140, 540), c["login.tagline_l1"], fill=theme.text, font=font(72, bold=True))
    d.text((140, 630), c["login.tagline_l2"], fill=theme.text, font=font(72, bold=True))
    # Özellik listesi
    feats = [
        (c["login.feature_split_view_t"], c["login.feature_split_view_d"]),
        (c["login.feature_pencil_t"], c["login.feature_pencil_d"]),
        (c["login.feature_keyboard_t"], c["login.feature_keyboard_d"]),
        (c["login.feature_multitask_t"], c["login.feature_multitask_d"]),
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
    d.text((cx + 48, cy + 56), c["common.welcome"], fill=theme.text, font=font(52, bold=True))
    d.text((cx + 48, cy + 130), c["common.signin_prompt"], fill=theme.muted, font=font(28))

    d.text((cx + 48, cy + 230), c["common.email"], fill=theme.muted, font=font(28))
    d.rounded_rectangle((cx + 48, cy + 270, cx + cw - 48, cy + 360), radius=16, fill=theme.surface_alt)
    d.text((cx + 70, cy + 296), "info@syroce.com", fill=theme.text, font=font(34))
    d.text((cx + 48, cy + 410), c["common.password"], fill=theme.muted, font=font(28))
    d.rounded_rectangle((cx + 48, cy + 450, cx + cw - 48, cy + 540), radius=16, fill=theme.surface_alt)
    d.text((cx + 70, cy + 476), "•••••••••••", fill=theme.text, font=font(34))

    d.rounded_rectangle((cx + 48, cy + 620, cx + cw - 48, cy + 730), radius=20, fill=PRIMARY)
    f = font(38, bold=True)
    bt = c["common.signin"]
    btw, bth = text_size(d, bt, f)
    d.text((cx + cw // 2 - btw // 2, cy + 655), bt, fill=WHITE, font=f)

    d.rounded_rectangle((cx + 48, cy + 760, cx + cw - 48, cy + 870), radius=20, outline=PRIMARY, width=3)
    bt2 = c["common.touchid"]
    btw2, _ = text_size(d, bt2, f)
    d.text((cx + cw // 2 - btw2 // 2, cy + 795), bt2, fill=PRIMARY, font=f)

    d.text((cx + 48, cy + ch - 90), c["common.demo"], fill=theme.muted, font=font(26))
    return im


def _screen_today_tablet(w: int, h: int, theme: Theme, c: dict) -> Image.Image:
    im, d = base_screen(w, h, theme)
    rail_w = _tablet_side_rail(
        im, d, h, theme, c,
        [(c["nav.today"], True), (c["nav.guests"], False), (c["nav.walkin"], False),
         (c["nav.messages"], False), (c["nav.reports"], False), (c["nav.more"], False)],
    )
    d = ImageDraw.Draw(im)
    y0 = _tablet_header(d, rail_w, theme, c["today.title"], c["today.subtitle_tablet"])

    x0 = rail_w + TABLET_PAD
    content_w = w - x0 - TABLET_PAD

    # Üst özet kartları (4'lü grid)
    summaries = [
        ("12", c["today.summary_checkin"], PRIMARY),
        ("8", c["today.summary_checkout"], INFO),
        ("3", c["today.summary_noshow"], WARNING),
        ("87%", c["today.summary_occupancy"], SUCCESS),
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
    d.text((x0 + 32, md_y + 28), c["today.pending_title"], fill=theme.text, font=font(40, bold=True))
    d.text((x0 + 32, md_y + 88), c["today.pending_sub_tablet"], fill=theme.muted, font=font(26))
    rows = [
        (c["today.row1_name"], c["today.row1_sub"], c["today.tag_vip"], VIP, True),
        (c["today.row2_name"], c["today.row2_sub"], c["today.tag_early"], INFO, False),
        (c["today.row3_name"], c["today.row3_sub_tablet"], c["today.tag_standard"], MUTED, False),
        (c["today.row4_name"], c["today.row4_sub"], c["today.tag_late"], WARNING, False),
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
    d.text((right_x + 28, md_y + 28), c["today.detail_title"], fill=theme.muted, font=font(26))
    d.ellipse((right_x + 28, md_y + 80, right_x + 188, md_y + 240), fill=theme.surface_alt)
    iw, ih = text_size(d, "AY", font(64, bold=True))
    d.text((right_x + 108 - iw // 2, md_y + 160 - ih // 2), "AY", fill=PRIMARY, font=font(64, bold=True))
    d.text((right_x + 220, md_y + 92), c["today.row1_name"], fill=theme.text, font=font(40, bold=True))
    d.text((right_x + 220, md_y + 148), c["today.detail_loyalty"], fill=theme.muted, font=font(26))
    chip(d, right_x + 220, md_y + 188, c["today.tag_vip"], color=VIP)

    # Detay grid (2x2)
    items = [
        (c["today.detail_room_lbl"], c["today.detail_room_val"]),
        (c["today.detail_guest_lbl"], c["today.detail_guest_val"]),
        (c["today.detail_stay_lbl"], c["today.detail_stay_val"]),
        (c["today.detail_total_lbl"], c["today.detail_total_val"]),
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
    d.text((right_x + 28, ny), c["today.notes_title"], fill=theme.text, font=font(30, bold=True))
    notes = [
        (c["today.note1"], SUCCESS),
        (c["today.note2"], INFO),
        (c["today.note3"], WARNING),
    ]
    for i, (n, c_) in enumerate(notes):
        ny2 = ny + 60 + i * 60
        d.ellipse((right_x + 28, ny2 + 12, right_x + 56, ny2 + 40), fill=c_)
        d.text((right_x + 76, ny2 + 6), n, fill=theme.text, font=font(26))

    # Aksiyon butonları (alt)
    by = md_y + md_h - 220
    d.rounded_rectangle((right_x + 28, by, right_x + right_w - 28, by + 96), radius=20, fill=PRIMARY)
    f = font(34, bold=True)
    bt = c["today.btn_start_checkin"]
    bw, bh = text_size(d, bt, f)
    d.text((right_x + right_w // 2 - bw // 2, by + 48 - bh // 2), bt, fill=WHITE, font=f)
    by2 = by + 116
    d.rounded_rectangle((right_x + 28, by2, right_x + right_w - 28, by2 + 86), radius=20, outline=PRIMARY, width=3)
    bt2 = c["today.btn_message"]
    bw2, _ = text_size(d, bt2, f)
    d.text((right_x + right_w // 2 - bw2 // 2, by2 + 42 - bh // 2), bt2, fill=PRIMARY, font=f)
    return im


def _screen_quick_checkin_tablet(w: int, h: int, theme: Theme, c: dict) -> Image.Image:
    im, d = base_screen(w, h, theme)
    rail_w = _tablet_side_rail(
        im, d, h, theme, c,
        [(c["nav.today"], False), (c["nav.guests"], False), (c["nav.walkin"], True),
         (c["nav.messages"], False), (c["nav.reports"], False), (c["nav.more"], False)],
    )
    d = ImageDraw.Draw(im)
    y0 = _tablet_header(d, rail_w, theme, c["qci.title"], c["qci.sub_tablet"])

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

    d.text((x0 + pad, cy0 + ch - pad - 50), c["qci.align"],
           fill=WHITE, font=font(34, bold=True))
    # Mod düğmeleri
    mb_y = qy + qs + 60
    mods = [
        (c["qci.mode_qr"], True),
        (c["qci.mode_id"], False),
        (c["qci.mode_passport"], False),
    ]
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
    d.text((right_x + 32, y0 + 28), c["qci.found"], fill=SUCCESS, font=font(32, bold=True))
    d.text((right_x + 32, y0 + 80), c["qci.guest_name"], fill=theme.text, font=font(50, bold=True))
    d.text((right_x + 32, y0 + 150), c["qci.guest_meta"], fill=theme.muted, font=font(28))
    chip(d, right_x + 32, y0 + 210, c["qci.tag_vip"], color=VIP)
    chip(d, right_x + 32 + 130, y0 + 210, c["qci.tag_returning"], color=INFO)

    # Bilgi blokları
    info = [
        (c["qci.info_res_lbl"], c["qci.info_res_val"]),
        (c["qci.info_room_lbl"], c["qci.info_room_val"]),
        (c["qci.info_stay_lbl"], c["qci.info_stay_val"]),
        (c["qci.info_total_lbl"], c["qci.info_total_val"]),
        (c["qci.info_paid_lbl"], c["qci.info_paid_val"]),
        (c["qci.info_balance_lbl"], c["qci.info_balance_val"]),
    ]
    iy = y0 + 300
    for i, (lbl, val) in enumerate(info):
        d.text((right_x + 32, iy), lbl, fill=theme.muted, font=font(24))
        d.text((right_x + 32, iy + 32), val, fill=theme.text, font=font(32, bold=True))
        iy += 92

    # Geçmiş konaklama özeti
    hy = iy + 30
    d.text((right_x + 32, hy), c["qci.history_count"], fill=theme.text, font=font(28, bold=True))
    d.text((right_x + 32, hy + 44), c["qci.history_last"], fill=theme.muted, font=font(26))

    # Aksiyon butonları (alt)
    by = y0 + panel_h - 230
    d.rounded_rectangle((right_x + 32, by, right_x + right_w - 32, by + 100), radius=20, fill=SUCCESS)
    f = font(36, bold=True)
    bt = c["qci.btn_confirm_checkin"]
    bw, bh = text_size(d, bt, f)
    d.text((right_x + right_w // 2 - bw // 2, by + 50 - bh // 2), bt, fill=WHITE, font=f)
    by2 = by + 120
    d.rounded_rectangle((right_x + 32, by2, right_x + right_w - 32, by2 + 86), radius=20, outline=theme.border, width=3)
    bt2 = c["qci.btn_manual"]
    bw2, _ = text_size(d, bt2, f)
    d.text((right_x + right_w // 2 - bw2 // 2, by2 + 42 - bh // 2), bt2, fill=theme.text, font=f)
    return im


def _screen_housekeeping_tablet(w: int, h: int, theme: Theme, c: dict) -> Image.Image:
    im, d = base_screen(w, h, theme)
    rail_w = _tablet_side_rail(
        im, d, h, theme, c,
        [(c["nav.rooms"], True), (c["nav.damage"], False), (c["nav.stock"], False),
         (c["nav.tasks"], False), (c["nav.reports"], False), (c["nav.more"], False)],
    )
    d = ImageDraw.Draw(im)
    y0 = _tablet_header(d, rail_w, theme, c["hk.title"], c["hk.sub_tablet"])

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
    chips_def = [
        (c["hk.chip_all"], False),
        (c["hk.chip_floor4"], True),
        (c["hk.chip_dirty"], False),
        (c["hk.chip_clean"], False),
        (c["hk.chip_maintenance"], False),
    ]
    for label, active in chips_def:
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
        ("401", c["hk.status_clean"], SUCCESS, c["hk.kind_standard"], False),
        ("402", c["hk.status_dirty"], WARNING, c["hk.kind_standard"], False),
        ("403", c["hk.status_cleaning"], INFO, c["hk.kind_standard"], False),
        ("404", c["hk.status_maintenance"], DANGER, c["hk.kind_suite"], False),
        ("405", c["hk.status_clean"], SUCCESS, c["hk.kind_standard"], False),
        ("406", c["hk.status_occupied"], PRIMARY, c["hk.kind_deluxe"], False),
        ("407", c["hk.status_dirty"], WARNING, c["hk.kind_standard"], False),
        ("408", c["hk.status_clean"], SUCCESS, c["hk.kind_standard"], False),
        ("409", c["hk.status_inspection"], INFO, c["hk.kind_standard"], False),
        ("410", c["hk.status_clean"], SUCCESS, c["hk.kind_standard"], False),
        ("411", c["hk.status_dirty"], WARNING, c["hk.kind_suite"], False),
        ("412", c["hk.status_occupied"], PRIMARY, c["hk.kind_deluxe"], True),
        ("414", c["hk.status_clean"], SUCCESS, c["hk.kind_standard"], False),
        ("415", c["hk.status_maintenance"], DANGER, c["hk.kind_standard"], False),
        ("416", c["hk.status_clean"], SUCCESS, c["hk.kind_standard"], False),
        ("417", c["hk.status_dirty"], WARNING, c["hk.kind_standard"], False),
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
    d.text((right_x + 28, y0 + 28), c["hk.detail_room"], fill=theme.text, font=font(64, bold=True))
    d.text((right_x + 28, y0 + 110), c["hk.detail_meta"], fill=theme.muted, font=font(28))
    chip(d, right_x + 28, y0 + 160, c["hk.chip_occupied"], color=PRIMARY)
    chip(d, right_x + 28 + 140, y0 + 160, c["hk.chip_guest_in"], color=INFO)

    # Görev listesi
    ty = y0 + 240
    d.text((right_x + 28, ty), c["hk.tasks_title"], fill=theme.text, font=font(32, bold=True))
    tasks = [
        (c["hk.task1"], True),
        (c["hk.task2"], True),
        (c["hk.task3"], False),
        (c["hk.task4"], False),
        (c["hk.task5"], False),
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
    d.text((right_x + 28, ay), c["hk.assigned"], fill=theme.text, font=font(28, bold=True))
    d.ellipse((right_x + 28, ay + 50, right_x + 108, ay + 130), fill=theme.surface_alt)
    iw, ih = text_size(d, "ED", font(36, bold=True))
    d.text((right_x + 68 - iw // 2, ay + 90 - ih // 2), "ED", fill=PRIMARY, font=font(36, bold=True))
    d.text((right_x + 130, ay + 56), c["hk.staff_name"], fill=theme.text, font=font(32, bold=True))
    d.text((right_x + 130, ay + 100), c["hk.staff_eta"], fill=theme.muted, font=font(24))

    # Aksiyon
    by = y0 + panel_h - 200
    d.rounded_rectangle((right_x + 28, by, right_x + right_w - 28, by + 96), radius=20, fill=SUCCESS)
    f = font(32, bold=True)
    bt = c["hk.btn_mark_clean"]
    bw, bh = text_size(d, bt, f)
    d.text((right_x + right_w // 2 - bw // 2, by + 48 - bh // 2), bt, fill=WHITE, font=f)
    by2 = by + 116
    d.rounded_rectangle((right_x + 28, by2, right_x + right_w - 28, by2 + 86), radius=20, outline=PRIMARY, width=3)
    bt2 = c["hk.btn_request_maintenance"]
    bw2, _ = text_size(d, bt2, f)
    d.text((right_x + right_w // 2 - bw2 // 2, by2 + 42 - bh // 2), bt2, fill=PRIMARY, font=f)
    return im


def _screen_guest_bookings_tablet(w: int, h: int, theme: Theme, c: dict) -> Image.Image:
    im, d = base_screen(w, h, theme)
    rail_w = _tablet_side_rail(
        im, d, h, theme, c,
        [(c["nav.home_full"], False), (c["nav.bookings_full"], True), (c["nav.messages"], False),
         (c["nav.key"], False), (c["nav.account"], False), (c["nav.more"], False)],
    )
    d = ImageDraw.Draw(im)
    y0 = _tablet_header(d, rail_w, theme, c["gb.title"], c["gb.sub_tablet"])

    x0 = rail_w + TABLET_PAD
    content_w = w - x0 - TABLET_PAD
    left_w = int(content_w * 0.42)
    right_x = x0 + left_w + 24
    right_w = content_w - left_w - 24
    panel_h = h - y0 - TABLET_PAD

    # Sol: rezervasyon listesi
    card(d, x0, y0, left_w, panel_h, theme)
    d.text((x0 + 28, y0 + 24), c["gb.list_title"], fill=theme.text, font=font(32, bold=True))
    bookings = [
        (c["gb.hotel_bodrum"], c["gb.dates_active_short"], c["gb.status_active"], SUCCESS, True),
        (c["gb.hotel_kapadokya"], c["gb.dates_kapadokya"], c["gb.status_confirmed"], PRIMARY, False),
        (c["gb.hotel_istanbul"], c["gb.dates_istanbul"], c["gb.status_completed"], MUTED, False),
        (c["gb.hotel_antalya"], c["gb.dates_antalya"], c["gb.status_completed"], MUTED, False),
        (c["gb.hotel_izmir"], c["gb.dates_izmir"], c["gb.status_cancelled"], DANGER, False),
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
    chip(d, right_x + 28, y0 + 28, c["gb.status_active"], color=SUCCESS)
    d.text((right_x + 28, y0 + 90), c["gb.hotel_bodrum"], fill=theme.text, font=font(56, bold=True))
    d.text((right_x + 28, y0 + 170), c["gb.dates_active_tablet"],
           fill=theme.muted, font=font(30))

    # Konaklama bilgi grid (4 sütun)
    items = [
        (c["gb.lbl_total"], "₺18.400"),
        (c["gb.lbl_paid"], "₺9.200"),
        (c["gb.lbl_balance"], "₺9.200"),
        (c["gb.lbl_guest"], c["gb.val_guest2_full"]),
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
    actions = [
        (c["gb.act_key"], PRIMARY),
        (c["gb.act_message"], INFO),
        (c["gb.act_early"], WARNING),
        (c["gb.act_invoice"], MUTED),
    ]
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
    d.text((right_x + 28, ty), c["gb.timeline_title"], fill=theme.text, font=font(30, bold=True))
    timeline = [
        (c["gb.tl_checkin_when"], c["gb.tl_checkin_what"], PRIMARY),
        (c["gb.tl_breakfast_when"], c["gb.tl_breakfast_what"], INFO),
        (c["gb.tl_dinner_when"], c["gb.tl_dinner_what"], VIP),
        (c["gb.tl_spa_when"], c["gb.tl_spa_what"], SUCCESS),
        (c["gb.tl_checkout_when"], c["gb.tl_checkout_what"], WARNING),
    ]
    for i, (when, what, color) in enumerate(timeline):
        ly = ty + 60 + i * 60
        d.ellipse((right_x + 28, ly + 12, right_x + 56, ly + 40), fill=color)
        if i < len(timeline) - 1:
            d.line([(right_x + 42, ly + 40), (right_x + 42, ly + 90)], fill=theme.border, width=3)
        d.text((right_x + 76, ly + 6), when, fill=theme.muted, font=font(22))
        d.text((right_x + 220, ly + 4), what, fill=theme.text, font=font(26, bold=True))
    return im


def _screen_digital_key_tablet(w: int, h: int, theme: Theme, c: dict) -> Image.Image:
    im, d = base_screen(w, h, theme)
    rail_w = _tablet_side_rail(
        im, d, h, theme, c,
        [(c["nav.home_full"], False), (c["nav.bookings_full"], False), (c["nav.messages"], False),
         (c["nav.key"], True), (c["nav.account"], False), (c["nav.more"], False)],
    )
    d = ImageDraw.Draw(im)
    y0 = _tablet_header(d, rail_w, theme, c["dk.title"], c["dk.sub"])

    x0 = rail_w + TABLET_PAD
    content_w = w - x0 - TABLET_PAD
    left_w = int(content_w * 0.52)
    right_x = x0 + left_w + 24
    right_w = content_w - left_w - 24
    panel_h = h - y0 - TABLET_PAD

    # Sol: büyük QR kartı
    card(d, x0, y0, left_w, panel_h, theme)
    d.text((x0 + 32, y0 + 28), c["dk.qr_title"], fill=theme.text, font=font(36, bold=True))
    d.text((x0 + 32, y0 + 80), c["dk.qr_sub"], fill=theme.muted, font=font(26))
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
    d.text((x0 + 32, iy), c["dk.valid_lbl"], fill=theme.muted, font=font(26))
    d.text((x0 + 32, iy + 36), c["dk.valid_val"], fill=theme.text, font=font(36, bold=True))

    # Aksiyon (alt)
    by = y0 + panel_h - 130
    d.rounded_rectangle((x0 + 32, by, x0 + left_w - 32, by + 96), radius=22, fill=PRIMARY)
    f = font(32, bold=True)
    bt = c["dk.btn_share"]
    bw, bh = text_size(d, bt, f)
    d.text((x0 + left_w // 2 - bw // 2, by + 48 - bh // 2), bt, fill=WHITE, font=f)

    # Sağ: bilgi paneli
    card(d, right_x, y0, right_w, panel_h, theme)
    d.text((right_x + 28, y0 + 28), c["dk.summary"], fill=theme.text, font=font(36, bold=True))
    info = [
        (c["dk.info_hotel_lbl"], c["dk.info_hotel_val"]),
        (c["dk.info_room_lbl"], c["dk.info_room_val"]),
        (c["dk.info_stay_lbl"], c["dk.info_stay_val"]),
        (c["dk.info_guest_lbl"], c["dk.info_guest_val"]),
        (c["dk.info_floor_lbl"], c["dk.info_floor_val"]),
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
    d.text((right_x + 200, by2 + 50), c["dk.bt_title"],
           fill=theme.text, font=font(32, bold=True))
    d.text((right_x + 200, by2 + 100), c["dk.bt_sub"],
           fill=theme.muted, font=font(26))
    d.text((right_x + 200, by2 + 138), c["dk.bt_extra"],
           fill=theme.muted, font=font(24))

    # İpuçları
    ty = by2 + 240
    d.text((right_x + 28, ty), c["dk.tips_title"], fill=theme.text, font=font(28, bold=True))
    tips = [c["dk.tip1"], c["dk.tip2"], c["dk.tip3"]]
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
    bt = c["dk.btn_help_long"]
    bw, bh = text_size(d, bt, f)
    d.text((right_x + right_w // 2 - bw // 2, by3 + 48 - bh // 2), bt, fill=PRIMARY, font=f)
    return im


# Ekran tanımları: anahtar -> (headline_key, builder)
SCREENS = {
    "01_login": ("hl.01_login", screen_login),
    "02_today": ("hl.02_today", screen_today),
    "03_quick_checkin": ("hl.03_quick_checkin", screen_quick_checkin),
    "04_housekeeping": ("hl.04_housekeeping", screen_housekeeping),
    "05_guest_bookings": ("hl.05_guest_bookings", screen_guest_bookings),
    "06_digital_key": ("hl.06_digital_key", screen_digital_key),
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
    Cihaz mockup + üstte yerelleştirilmiş başlık + altta cihazın içine yerleşmiş ekran.
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
    mağaza boyutu için cihaz mockup'lı pazarlama görseli üretilir. Tüm
    yerelleştirmeler (Türkçe varsayılan, İngilizce `en/` altında) tek geçişte
    yazılır.
    """
    themes = (DARK, LIGHT)
    for locale in LOCALES:
        ios_dir = SHOTS / "ios" / locale.out_subdir if locale.out_subdir else SHOTS / "ios"
        android_dir = SHOTS / "android" / locale.out_subdir if locale.out_subdir else SHOTS / "android"
        ios_dir.mkdir(parents=True, exist_ok=True)
        android_dir.mkdir(parents=True, exist_ok=True)
        for key, (headline_key, builder) in SCREENS.items():
            headline = locale.copy[headline_key]
            for theme in themes:
                theme_suffix = "" if theme.name == "dark" else "_light"
                phone_base = builder(*PHONE_BASE, theme, locale.copy, kind="phone")
                tablet_base = builder(*TABLET_BASE, theme, locale.copy, kind="tablet")

                # iOS telefon
                for size_key, sz in IOS_PHONE_SIZES.items():
                    out = compose_marketing(phone_base, headline, sz, theme, "phone")
                    out.save(ios_dir / f"{key}_{size_key}{theme_suffix}.png", "PNG")
                # iOS iPad
                for size_key, sz in IOS_TABLET_SIZES.items():
                    out = compose_marketing(tablet_base, headline, sz, theme, "tablet")
                    out.save(ios_dir / f"{key}_{size_key}{theme_suffix}.png", "PNG")

                # Android telefon
                out = compose_marketing(phone_base, headline, ANDROID_PHONE_SIZE, theme, "phone")
                out.save(android_dir / f"{key}_phone{theme_suffix}.png", "PNG")
                # Android tabletler
                for size_key, sz in ANDROID_TABLET_SIZES.items():
                    out = compose_marketing(tablet_base, headline, sz, theme, "tablet")
                    out.save(android_dir / f"{key}_{size_key}{theme_suffix}.png", "PNG")

            print(f"  + [{locale.code}] {key} — {headline} (dark + light, telefon + tablet)")


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
