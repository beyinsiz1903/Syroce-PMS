// Sentry browserTracingIntegration fetch wrapper + service-worker arasındaki
// bilinen Response.clone() race condition'ı nadiren "Failed to execute 'clone'
// on 'Response': Response body is already used" üretiyor. Hata transient — bir
// kez kısa gecikmeli retry yeterli. HTTP 4xx/5xx ve gerçek ağ hataları retry
// EDİLMEZ; sadece clone/body-stream desenli mesajlar.

const TRANSIENT_FETCH_ERR = /clone|body is already used|body stream/i;

export async function fetchJsonWithRetry(url, opts) {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const res = await fetch(url, opts);
      if (!res.ok) {
        const err = new Error('HTTP ' + res.status);
        err.status = res.status;
        throw err;
      }
      return await res.json();
    } catch (err) {
      const msg = err && err.message ? String(err.message) : '';
      const isTransient = TRANSIENT_FETCH_ERR.test(msg);
      if (!isTransient || attempt === 1) throw err;
      await new Promise((r) => setTimeout(r, 150));
    }
  }
}

export async function fetchWithRetry(url, opts) {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      return await fetch(url, opts);
    } catch (err) {
      const msg = err && err.message ? String(err.message) : '';
      const isTransient = TRANSIENT_FETCH_ERR.test(msg);
      if (!isTransient || attempt === 1) throw err;
      await new Promise((r) => setTimeout(r, 150));
    }
  }
}
