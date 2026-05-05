"""
Guest QR Badge — Mobil cihazda dönen dinamik QR ile folyoya şarj akışı.

Tur 15 / Hafta 1 kapsamı:
  - Misafir mobil uygulamasında dönen QR token (60 sn TTL)
  - Personel POS'tan QR tarar → bekleyen şarj oluşturur
  - Misafire push gider, biyometrik onaylı approve/reject
  - Approve → FolioHardeningService.post_charge ile folyoya yazılır

Sonraki haftalar:
  Hafta 2 — POS web ekranı, davranış izleme, şüpheli işlem alarmı
  Hafta 3 — SMS yedek kodu, refakatçi modeli, manuel resepsiyon onayı
"""
from .router import router

__all__ = ["router"]
