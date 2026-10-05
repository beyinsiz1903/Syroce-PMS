const TRANSIENT_GATEWAY_STATUSES = new Set([502, 503, 504]);
const DEFAULT_RETRY_DELAY_MS = 600;

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function isTransientLoginGatewayError(error) {
  return TRANSIENT_GATEWAY_STATUSES.has(error?.response?.status);
}

/**
 * Login is safe to repeat when a gateway briefly loses the upstream response.
 * Keep this retry local to auth; the global HTTP resilience layer intentionally
 * never retries arbitrary POST requests because most mutations are not idempotent.
 */
export async function postLoginWithGatewayRetry(
  httpClient,
  payload,
  { sleep = wait, retryDelayMs = DEFAULT_RETRY_DELAY_MS } = {},
) {
  try {
    return await httpClient.post('/auth/login', payload);
  } catch (error) {
    if (!isTransientLoginGatewayError(error)) throw error;
    await sleep(retryDelayMs);
    return httpClient.post('/auth/login', payload);
  }
}
