"""
Agency v1 — Imza kimlik (shared_secret) deposu (ADR Karar 2, secret-at-rest).

Karar 2: her acente->PMS istegi `Authorization: Bearer <key_id>` (sir DEGIL,
yalniz tanimlayici) + `X-Agency-Signature = hex(hmac_sha256(shared_secret, ...))`
tasir. Bearer'daki key_id mevcut `agency_api_keys` dokumaninin `id`'sidir
(public tanimlayici). `shared_secret` ise HMAC imzasini uretmek/dogrulamak icin
gerekli SIR'dir ve PMS tarafinda AT-REST SIFRELI saklanir; bu modul o deponun
tek kaynagidir.

Neden ayri koleksiyon + engine-direct:
- `agency_api_keys` yalniz `key_hash` (tek-yonlu SHA-256) tutar; HMAC dogrulama
  iki-yonlu sirra ihtiyac duyar. Mevcut b2b mint/teslim akisini perturbe etmemek
  icin sir AYRI `agency_signing_secrets` koleksiyonunda, `_id = key_id` ile 1:1
  yan-dosya olarak tutulur (dogal benzersizlik; ek index gerekmez).
- Sifreleme softphone kayit desenini aynalar: `AESGCMEngine` DOGRUDAN kullanilir
  (CredentialEncryptionService DEGIL). Cunku servis varsayilan
  CRYPTO_V2_ENABLED=false altinda AAD'yi YOK SAYAR (legacy aes256gcm yolu);
  engine ise AAD'yi HER ZAMAN uygular. AAD = (tenant_id, agency_id, key_id)'ye
  baglar: bir sifreli sir baska bir tenant/agency/key dokumanina tasinirsa GCM
  tag dogrulamasi (InvalidTag) fail eder -> cross-tenant sir yeniden-kullanim
  fail-closed reddedilir.

Doktrin: shared_secret degeri ASLA loglanmaz/yanitta gecmez; resolve cozulemezse
(eksik dokuman, tamper, anahtar bulunamadi) fail-closed None doner (cagiran 401).
Sir cagirana yalniz mint aninda BIR KEZ ham doner; persist edilen tek sey sifreli
zarftir.
"""
from __future__ import annotations

import logging
import os
import secrets

from core.crypto.engine import AADContext, AESGCMEngine
from core.crypto.errors import CryptoError
from core.crypto.keys import load_keyring

logger = logging.getLogger("agency_v1.signing_store")

_PROVIDER = "agency_v1_signing"

_engine_inst: AESGCMEngine | None = None


def _engine() -> AESGCMEngine:
    global _engine_inst
    if _engine_inst is None:
        _engine_inst = AESGCMEngine(load_keyring())
    return _engine_inst


def _aad(tenant_id: str, agency_id: str, key_id: str) -> AADContext:
    return AADContext(
        tenant_id=tenant_id,
        provider=_PROVIDER,
        property_id=agency_id,
        environment=os.environ.get("APP_ENV", "development"),
        context_type=f"signing_secret:{key_id}",
    )


async def mint_agency_signing_secret(
    sysdb, *, key_id: str, tenant_id: str, agency_id: str
) -> str:
    """Yeni shared_secret uretir, AAD-bagli sifreli olarak saklar, ham degeri BIR
    KEZ doner. `_id = key_id` benzersiz oldugundan ayni key icin ikinci mint
    DuplicateKeyError firlatir (rotasyon ayri/bilincli bir islemdir).
    """
    raw_secret = secrets.token_urlsafe(48)
    secret_enc = _engine().encrypt(
        raw_secret, aad=_aad(tenant_id, agency_id, key_id)
    )
    from datetime import UTC, datetime

    doc = {
        "_id": key_id,
        "tenant_id": tenant_id,
        "agency_id": agency_id,
        "secret_enc": secret_enc,  # SYR1 zarf; plaintext sir ASLA yazilmaz
        "is_active": True,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await sysdb.agency_signing_secrets.insert_one(doc)
    return raw_secret


async def resolve_signing_secret(sysdb, key_id: str) -> dict | None:
    """key_id icin (tenant_id, agency_id, shared_secret) cozer; cozulemezse
    fail-closed None (cagiran 401). AAD stored tenant/agency/key_id'den yeniden
    kurulur; uyumsuz/tamper -> InvalidTag -> None.
    """
    if not key_id:
        return None
    doc = await sysdb.agency_signing_secrets.find_one(
        {"_id": key_id, "is_active": True}
    )
    if not doc:
        return None
    tenant_id = doc.get("tenant_id") or ""
    agency_id = doc.get("agency_id") or ""
    enc = doc.get("secret_enc") or ""
    if not (tenant_id and agency_id and enc):
        return None
    try:
        shared_secret = _engine().decrypt(
            enc, aad=_aad(tenant_id, agency_id, key_id)
        )
    except CryptoError:
        # tamper / wrong-AAD / key-not-found -> fail-closed. Sir/zarf LOGLANMAZ.
        logger.warning(
            "agency signing secret decrypt failed (fail-closed) key_id=%s", key_id
        )
        return None
    return {
        "key_id": key_id,
        "tenant_id": tenant_id,
        "agency_id": agency_id,
        "shared_secret": shared_secret,
    }


async def revoke_signing_secret(sysdb, key_id: str) -> None:
    """Imza sirrini pasiflestirir (api key revoke ile paralel). Idempotent."""
    await sysdb.agency_signing_secrets.update_one(
        {"_id": key_id}, {"$set": {"is_active": False}}
    )
