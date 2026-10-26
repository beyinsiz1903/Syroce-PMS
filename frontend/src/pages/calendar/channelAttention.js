/**
 * The shared Axios client already has /api as its base URL. Keep these
 * paths relative to that API root, just like the channel conflict screen.
 * Reject on either failure: a partial response must never look verified.
 */
export function loadChannelAttention(http) {
  return Promise.all([
    http.get('/channel-manager/conflict-queue', { params: { limit: 200 } }),
    http.get('/channel-manager/conflict-queue/mapping-issues'),
  ]);
}
