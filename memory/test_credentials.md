# Test Credentials

## Frontend Login
- Email: demo@hotel.com
- Password: demo123
- Role: super_admin

## Mock Server (HotelRunner)
- URL: http://localhost:9999
- Token: mock-hr-token-001
- HR ID: HR-HOTEL-001
- Valid tokens: mock-hr-token-001, test-token-valid
- Valid HR IDs: HR-HOTEL-001, HR-HOTEL-002

## Test Tenant Configuration
- tenant_id: test-tenant
- property_id: default
- Provider: hotelrunner
- Environment: mock
- Feature flags: connector_enabled=true, shadow_mode=true, write_enabled=false

## Room Mappings (test-tenant)
- DLX -> pms-dlx-001 (Deluxe Oda)
- STD -> pms-std-001 (Standard Oda)
- SUI -> pms-sui-001 (Suite)
- FAM -> pms-fam-001 (Aile Odasi)

## Rate Plan Mappings (test-tenant)
- BAR -> pms-bar-001 (Best Available Rate)
- PROMO -> pms-promo-001 (Promosyon)
- RACK -> pms-rack-001 (Rack Rate)
- NONREF -> pms-nonref-001 (Non-Refundable)
