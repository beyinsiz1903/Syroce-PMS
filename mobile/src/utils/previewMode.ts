// A public env flag is not enough: demo affordances belong only to a
// development build pointed at the dedicated, loopback-only fixture service.
export function demoPreviewEnabled(development: boolean, mode: string | undefined, apiUrl: string | undefined): boolean {
  return development && mode === 'demo' && /^http:\/\/(localhost|127\.0\.0\.1):18999\/?$/.test(apiUrl || '');
}
