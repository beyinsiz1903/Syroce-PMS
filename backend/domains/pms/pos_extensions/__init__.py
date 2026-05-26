"""POS Extensions — 8 yeni POS modülü (mevcut akışlardan tamamen bağımsız).

Modüller:
  - pos_currency       : çoklu döviz tahsilat
  - pos_happy_hour     : zaman-bazlı fiyat kuralları
  - pos_coupons        : kupon kodu motoru
  - pos_loyalty_pos    : puan kazan/harca (POS akışı)
  - pos_shift_close    : vardiya açma/kapama + nakit mutabakat
  - pos_barcode        : barkod→ürün eşleme + lookup
  - pos_print_spool    : ESC/POS termal yazıcı kuyruğu
  - pos_fiscal         : mali yazıcı (TR ÖKC) adapter + kuyruk

Tüm endpoint'ler /api/pos/ext/* prefix'i altında ve tenant_id scope zorunlu.
"""
