"""Nilvera alias selection policy."""

from .errors import NilveraBusinessRuleError


def resolve_receiver_alias(
    aliases: list[str],
    *,
    preferred_alias: str | None = None,
) -> str:
    """Select the exact PK (Posta Kutusu) receiver alias from a list of active aliases.

    Follows a strictly fail-closed, exact-match algorithm without substring heuristics:
    1. Removes empty or whitespace-only strings.
    2. Deduplicates exact matches while preserving case.
    3. If 0 valid aliases: raises NilveraBusinessRuleError.
    4. If 1 valid alias: returns it (unless preferred_alias is given and mismatches).
    5. If >1 valid aliases: returns preferred_alias if exact matched, else raises NilveraBusinessRuleError.

    Args:
        aliases: A list of active alias strings returned by the taxpayer service.
        preferred_alias: Optional explicit tenant preference for the receiver alias.

    Returns:
        The selected receiver alias string.

    Raises:
        NilveraBusinessRuleError: If no valid alias is found, or if multiple aliases
            exist but no exact matching preferred_alias is provided, or if the
            preferred_alias does not match any active alias.
    """
    # 1. Clean inputs: ignore empty or whitespace-only strings
    valid_aliases: list[str] = []
    for a in aliases:
        if a and a.strip():
            valid_aliases.append(a)

    # 2. Deduplicate exact matches (case-sensitive)
    unique_aliases: list[str] = []
    for a in valid_aliases:
        if a not in unique_aliases:
            unique_aliases.append(a)

    # 3. Handle empty case
    if not unique_aliases:
        raise NilveraBusinessRuleError(message="Mükellefin geçerli aktif etiketi bulunamadı.")

    # 4. Handle single alias case
    if len(unique_aliases) == 1:
        single_alias = unique_aliases[0]
        if preferred_alias is not None and preferred_alias != single_alias:
            raise NilveraBusinessRuleError(message="Kaydedilmiş tercih mükellefin aktif etiketiyle eşleşmiyor.")
        return single_alias

    # 5. Handle multiple aliases case
    if preferred_alias is None:
        raise NilveraBusinessRuleError(message="Mükellefin birden fazla aktif etiketi var, açık tercih gereklidir.")

    if preferred_alias not in unique_aliases:
        raise NilveraBusinessRuleError(message="Kaydedilmiş tercih mükellefin aktif etiketleri arasında bulunamadı.")

    return preferred_alias
