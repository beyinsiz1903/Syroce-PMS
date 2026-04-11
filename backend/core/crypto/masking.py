"""
Display masking — completely separated from encryption.

Masking is for UI display ONLY. It is NOT a security control.
Never confuse masking with encryption or rely on it for data protection.
"""


def mask_value(
    value: str,
    visible_prefix: int = 0,
    visible_suffix: int = 4,
) -> str:
    """Mask a credential value for display.

    Examples:
        mask_value("sk-1234567890")       → "********7890"
        mask_value("short")               → "****"
        mask_value("abc", visible_prefix=1, visible_suffix=1) → "a*c"
    """
    if not value or len(value) <= (visible_prefix + visible_suffix):
        return "****"
    hidden_len = len(value) - visible_prefix - visible_suffix
    return value[:visible_prefix] + "*" * hidden_len + value[-visible_suffix:]


def mask_dict(
    credentials: dict,
    visible_suffix: int = 4,
) -> dict:
    """Mask all values in a credentials dict for display."""
    return {
        k: mask_value(str(v), visible_suffix=visible_suffix) if v else "****"
        for k, v in credentials.items()
    }
