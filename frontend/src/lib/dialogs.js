/**
 * Imperative dialog API — Promise tabanlı, native window.confirm/alert/prompt yerine.
 * Drop-in replacement: `if (!await confirmDialog({ message: '...' })) return;`
 *
 * UI tarafı `<DialogHost />` componenti tarafından render edilir; App köküne tek bir
 * defa mount edilir (NotificationProvider yanına). Bu modül stateless bir köprüdür.
 *
 * Aynı anda birden fazla dialog talebi gelirse FIFO kuyruğa alınır; her zaman tek
 * dialog gösterilir, kullanıcı kapattıktan sonra sıradaki açılır.
 */

let _setState = null;
let _resolver = null;
const _queue = [];

export function _registerDialogHost(setStateFn) {
  _setState = setStateFn;
  if (!setStateFn) {
    // Host unmount oldu — varsa bekleyen resolver'ı iptal et ki kuyruk takılmasın
    if (_resolver) {
      const r = _resolver;
      _resolver = null;
      try { r(undefined); } catch (_) { /* noop */ }
    }
    return;
  }
  // Mount sonrası kuyrukta bekleyen varsa hemen göster
  _drain();
}

function _showNext() {
  if (_resolver) return; // hâlâ açık dialog var
  const next = _queue.shift();
  if (!next) return;
  _resolver = next.resolve;
  if (_setState) {
    _setState({ ...next.opts, open: true });
  } else {
    // DialogHost mount edilmediyse güvenli native fallback
    console.warn('[dialogs] DialogHost mount edilmemiş, native fallback');
    const opts = next.opts;
    let val;
    if (opts.type === 'confirm') val = window.confirm(opts.message);
    else if (opts.type === 'prompt') val = window.prompt(opts.message, opts.defaultValue || '');
    else { window.alert(opts.message); val = undefined; }
    _resolver = null;
    next.resolve(val);
    _showNext();
  }
}

function _drain() {
  if (!_resolver) _showNext();
}

function _open(opts) {
  return new Promise((resolve) => {
    _queue.push({ opts, resolve });
    _showNext();
  });
}

export function _resolveDialog(value) {
  const r = _resolver;
  _resolver = null;
  if (r) r(value);
  // Sıradaki dialog'u tetikle (microtask sonrası, state güncellemesi için)
  Promise.resolve().then(_showNext);
}

/**
 * @param {{ title?: string, message: string, confirmText?: string, cancelText?: string, variant?: 'danger'|'default' }} opts
 * @returns {Promise<boolean>}
 */
export function confirmDialog(opts) {
  return _open({ type: 'confirm', ...opts });
}

/**
 * @param {{ title?: string, message: string, confirmText?: string, variant?: 'danger'|'default' }} opts
 * @returns {Promise<void>}
 */
export function alertDialog(opts) {
  return _open({ type: 'alert', ...opts });
}

/**
 * @param {{ title?: string, message: string, defaultValue?: string, placeholder?: string, confirmText?: string, cancelText?: string }} opts
 * @returns {Promise<string|null>}  null = iptal
 */
export function promptDialog(opts) {
  return _open({ type: 'prompt', ...opts });
}
