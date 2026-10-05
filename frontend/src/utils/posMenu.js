export const normalizePOSMenuItem = (item = {}) => ({
  ...item,
  id: item.id || item.item_id,
  name: item.name || item.item_name || 'Adsız ürün',
  price: Number(item.price ?? item.unit_price ?? 0),
});

export const normalizePOSMenuItems = (items) => (
  Array.isArray(items) ? items.map(normalizePOSMenuItem).filter(item => item.id) : []
);
