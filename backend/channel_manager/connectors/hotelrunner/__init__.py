"""
DEPRECATED — Legacy HotelRunner v1 Connector.

Tum yeni gelistirmeler hotelrunner_v2 connector'da yapilmalidir.
Bu modul sadece geriye donuk uyumluluk icin korunmaktadir.
Tam kaynak kodu _deprecated_hotelrunner_v1/ dizininde yedeklenmistir.

Yeni connector: channel_manager.connectors.hotelrunner_v2
"""
import warnings

warnings.warn(
    "channel_manager.connectors.hotelrunner DEPRECATED — "
    "use channel_manager.connectors.hotelrunner_v2 instead. "
    "This module will be removed after v2 full live write is confirmed stable.",
    DeprecationWarning,
    stacklevel=2,
)
