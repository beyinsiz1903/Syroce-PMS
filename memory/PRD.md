# RoomOps PMS — Product Requirements Document

## Original Problem Statement
Build a production-grade hospitality platform (RoomOps PMS). Replace all mocked data provider integrations with real, robust, and maintainable API adapters.

## Core Requirements
1. **(P0 — DONE)** HotelRunner REST adapter — production-grade, 80+ tests
2. **(P0 — DONE)** Exely SOAP adapter — production-grade, 91+ tests
3. **(P0 — DONE)** Real Exely test environment integration — WSDL-based Security header, real API calls
4. **(P1)** Mapping UI improvement — PMS room/rate ↔ Provider room/rate mapping
5. **(P2)** Legacy collection cleanup — archive/delete unused DB collections

## Architecture
- **Backend**: FastAPI (Python) + MongoDB
- **Frontend**: React + Shadcn/UI
- **Providers**: HotelRunner (REST), Exely (SOAP/WCF)
- **Security**: Encrypted credential vault, JWT auth

## Exely Real Test Environment
- **Endpoint**: `https://pmsconnect.test.hopenapi.com/Api/PMSConnect.svc`
- **HotelCode**: 501694
- **Property**: TEST Syroce PMS
- **Currency**: USD
- **Mode**: sandbox
- **Security**: PMSConnect attribute-based Security header (NOT WSSE)
- **SOAPAction Pattern**: `https://www.hopenapi.com/Api/PMSConnect/{Operation}`

### Discovered Inventory (Real)
| Room Types | Code | Name |
|---|---|---|
| 1 | 5001574 | Standart |
| 2 | 5001575 | Deluxe |
| 3 | 5001576 | Suite |

| Rate Plans | Code | Name |
|---|---|---|
| 1 | 10003182 | Лучшая цена дня |
| 2 | 10003186 | Mixed rate USD |
| 3 | 10003541 | Dynamic Rate USD |
| 4 | 10003869 | Non-ref rate USD |
| 5 | 10003870 | Base rate USD |

## Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
