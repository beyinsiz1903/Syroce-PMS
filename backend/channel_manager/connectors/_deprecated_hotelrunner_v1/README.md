"""
DEPRECATED — Legacy HotelRunner v1 Connector

Bu moduldeki tum siniflar artik KULLANILMAMALIDIR.
Yeni v2 connector: channel_manager.connectors.hotelrunner_v2

Bu dosyalar sadece geriye donuk uyumluluk icin burada tutulmaktadir.
Yeni kod asla bu module referans vermemelidir.

Migration notu: Application layer servisleri (inventory_sync_service,
reservation_import_service, connector_service, provider_adapters,
sandbox_validation_service) hala v1 import kullaniyor.
Bu servisler gelecek sprint'te v2'ye migrate edilecektir.

Tahmini kaldirilma tarihi: v2 full live write basarili olduktan sonra.
"""
