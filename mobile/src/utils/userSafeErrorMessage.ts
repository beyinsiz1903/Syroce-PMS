/** Keep meaningful business errors, but never render raw HTTP/JS diagnostics. */
export function userSafeErrorMessage(message: string | undefined, fallback: string): string {
  const value = (message || '').trim();
  if (!value) return fallback;

  if (/plan(?:ınıza|iniza).*dahil değil/i.test(value)) {
    return 'Bu özellik otelinizin paketinde etkin değil.';
  }

  // A router-level "Not Found" is not proof that a guest or reservation was
  // deleted. Use the screen's contextual load error; preserve explicit backend
  // messages such as "Rezervasyon bulunamadı" or a permission explanation.
  if (/^(?:not found|forbidden|unauthorized|internal server error|bad gateway|service unavailable|request_failed|network|failed to fetch|network request failed)$/i.test(value)) {
    return fallback;
  }

  if (
    /\b(TypeError|ReferenceError|SyntaxError|RangeError):/i.test(value) ||
    /\/var\/mobile\/Containers\//i.test(value) ||
    /\.bundle:\d+/i.test(value) ||
    /\n\s*at\s+/i.test(value)
  ) {
    return fallback;
  }

  return value;
}
