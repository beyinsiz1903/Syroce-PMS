import hashlib


def fingerprint_id(identifier: str) -> str:
    if not identifier:
        return "-"
    return hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:12]
