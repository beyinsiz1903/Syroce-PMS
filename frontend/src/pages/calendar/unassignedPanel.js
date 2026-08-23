export function resetUnassignedListScroll(listElement) {
  if (!listElement) return false;

  listElement.scrollTop = 0;
  return true;
}
