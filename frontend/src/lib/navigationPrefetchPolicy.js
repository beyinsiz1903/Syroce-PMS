/**
 * Opening a navigation category is a discovery action, not an intent to load
 * every page it contains. Route chunks are therefore warmed only when a
 * specific item is hovered or receives keyboard focus in Layout.
 */
export function shouldPrefetchOnGroupOpen() {
  return false;
}
