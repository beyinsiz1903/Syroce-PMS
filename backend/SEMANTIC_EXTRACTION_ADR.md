# Semantic Extraction ADR

## Sprint 1 Governance Rules

- `server.py` içine yeni business logic eklenmez.
- Domain logic semantic module'lerde yaşar: `reservations`, `stays`, `inventory`, `folio`.
- Cross-module direct DB access yasaktır.
- Legacy endpoint davranışı korunur; yeni abstraction layer bridge olarak eklenir.
- Sprint 1 boyunca write-path migration yapılmaz.