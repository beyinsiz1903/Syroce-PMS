# Test Credentials

## Hotel Admin (Full Access)
- Email: demo@hotel.com
- Password: demo123
- Role: super_admin

## Front Desk Staff (Limited — no delete)
- Email: frontdesk@hotel.com
- Password: staff123
- Role: front_desk

## B2B API Test
- API Key auth uses X-API-Key header
- Keys generated via: POST /api/b2b/api-keys?agency_id={id} (admin auth required)
- Key format: syroce_b2b_{random}
- Existing test agencies:
  - Antalya Turizm (active, id: 1d6ebdef-b42a-40ea-8c01-f749ea96fdea)
  - TEST_Content_Agency_093011 (active, has API key)
