"""Purpose-bound restaurant table capabilities; never usable as login tokens."""
import jwt
from fastapi import HTTPException

from core.security import JWT_ALGORITHM, JWT_SECRET


def table_token(tenant_id, outlet_id, table):
    return jwt.encode({'purpose': 'pos_guest_order', 'tenant': tenant_id, 'outlet': outlet_id,
                       'table': str(table['id']), 'version': table.get('qr_version', 0)},
                      JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_table_token(token, tenant_id, outlet_id, table):
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(403, 'Masa QR kodu geçersiz; personelden güncel kodu isteyin.') from None
    expected = {'purpose': 'pos_guest_order', 'tenant': tenant_id, 'outlet': outlet_id,
                'table': str(table['id']), 'version': table.get('qr_version', 0)}
    if any(claims.get(key) != value for key, value in expected.items()):
        raise HTTPException(403, 'Bu QR kodu seçilen masaya ait değil.')
