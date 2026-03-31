# Test Credentials

## Hotel Admin (super_admin)
- **Email:** demo@hotel.com
- **Password:** demo123
- **Role:** super_admin
- **Tenant:** Syroce Demo Hotel (044f122b-87b5-480a-88b4-b9534b0c8c90)

## Dashboard Access
- **URL:** /hrv2-ops
- **Tenant ID used in API:** syroce_default

## Auth Flow (for Playwright)
1. Navigate to app
2. Use JS fetch to call `/api/auth/login` with credentials above
3. Set `localStorage.token`, `localStorage.user`, `localStorage.tenant`
4. Navigate to `/hrv2-ops`
