const EXPENSE_CATEGORY_KEYS = {
  salaries: ['invoice.salaries', 'Salaries'],
  utilities: ['invoice.utilities', 'Utilities'],
  supplies: ['invoice.supplies', 'Supplies'],
  maintenance: ['invoice.maintenance', 'Maintenance'],
  marketing: ['invoice.marketing', 'Marketing'],
  rent: ['invoice.rent', 'Rent'],
  insurance: ['invoice.insurance', 'Insurance'],
  taxes: ['invoice.taxes', 'Taxes'],
  other: ['common.other', 'Other'],
};

const PAYMENT_METHOD_KEYS = {
  cash: ['pms.cash', 'Cash'],
  card: ['pms.card', 'Credit Card'],
  credit_card: ['pms.card', 'Credit Card'],
  bank_transfer: ['pms.bankTransfer', 'Bank Transfer'],
};

const INVOICE_TYPE_KEYS = {
  sales: ['invoice.salesInvoice', 'Sales Invoice'],
  e_invoice: ['invoice.eInvoice', 'E-Invoice'],
  proforma: ['invoice.proforma', 'Proforma'],
};

const INVENTORY_CATEGORY_KEYS = {
  supplies: ['invoice.inventoryCategories.supplies', 'Supplies'],
  amenity: ['invoice.inventoryCategories.amenity', 'Guest Amenity'],
  amenities: ['invoice.inventoryCategories.amenity', 'Guest Amenity'],
  food: ['invoice.inventoryCategories.food', 'Food'],
  beverage: ['invoice.inventoryCategories.beverage', 'Beverage'],
  linen: ['invoice.inventoryCategories.linen', 'Linen'],
  cleaning: ['invoice.inventoryCategories.cleaning', 'Cleaning'],
  cleaning_supplies: ['invoice.inventoryCategories.cleaning', 'Cleaning'],
  maintenance: ['invoice.inventoryCategories.maintenance', 'Maintenance'],
  stationery: ['invoice.inventoryCategories.stationery', 'Stationery'],
  electronics: ['invoice.inventoryCategories.electronics', 'Electronics'],
  uniform: ['invoice.inventoryCategories.uniform', 'Uniform'],
  general: ['invoice.inventoryCategories.general', 'General'],
  other: ['invoice.inventoryCategories.other', 'Other'],
};

const INVENTORY_UNIT_KEYS = {
  piece: ['invoice.inventoryUnits.piece', 'Piece'],
  pieces: ['invoice.inventoryUnits.piece', 'Piece'],
  bottle: ['invoice.inventoryUnits.bottle', 'Bottle'],
  bottles: ['invoice.inventoryUnits.bottle', 'Bottle'],
  kg: ['invoice.inventoryUnits.kilogram', 'Kilogram'],
  kilogram: ['invoice.inventoryUnits.kilogram', 'Kilogram'],
  liter: ['invoice.inventoryUnits.liter', 'Liter'],
  litre: ['invoice.inventoryUnits.liter', 'Liter'],
  pack: ['invoice.inventoryUnits.pack', 'Pack'],
  box: ['invoice.inventoryUnits.box', 'Box'],
  set: ['invoice.inventoryUnits.set', 'Set'],
};

const normalizeCode = (value) => String(value || '').trim().toLowerCase();

const humanizeCode = (value) => String(value || '')
  .trim()
  .replace(/[_-]+/g, ' ')
  .replace(/\b\w/g, (letter) => letter.toUpperCase());

const translateCode = (t, value, dictionary) => {
  const normalized = normalizeCode(value);
  const entry = dictionary[normalized];
  if (!entry) return humanizeCode(value);
  return t(entry[0], entry[1]);
};

export const expenseCategoryLabel = (t, value) => translateCode(t, value, EXPENSE_CATEGORY_KEYS);
export const paymentMethodLabel = (t, value) => translateCode(t, value, PAYMENT_METHOD_KEYS);
export const invoiceTypeLabel = (t, value) => translateCode(t, value, INVOICE_TYPE_KEYS);
export const inventoryCategoryLabel = (t, value) => translateCode(t, value, INVENTORY_CATEGORY_KEYS);
export const inventoryUnitLabel = (t, value) => translateCode(t, value, INVENTORY_UNIT_KEYS);

export const INVENTORY_CATEGORY_OPTIONS = [
  'supplies', 'amenity', 'food', 'beverage', 'linen', 'cleaning',
  'maintenance', 'stationery', 'electronics', 'uniform', 'general', 'other',
];

export const INVENTORY_UNIT_OPTIONS = ['piece', 'bottle', 'kg', 'liter', 'pack', 'box', 'set'];
