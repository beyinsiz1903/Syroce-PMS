import { create } from 'zustand';
type CartProduct = { id: string; name: string; price: number; currency?: string };

export type CartLine = {
  itemId: string;
  name: string;
  price: number;
  quantity: number;
  currency: string;
};

type CartState = {
  lines: CartLine[];
  requestId: string;
  serviceAt?: string;
  locked: boolean;
  bookingId: string | null;
  bindBooking: (id: string) => void;
  markSubmitted: () => void;
  unlockRejected: () => void;
  add: (item: CartProduct) => void;
  remove: (itemId: string) => void;
  setQty: (itemId: string, qty: number) => void;
  clear: () => void;
  count: () => number;
  total: () => number;
};

const requestId = () => `room-order-${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
export const useCartStore = create<CartState>((set, get) => ({
  lines: [],
  requestId: requestId(), locked: false, bookingId: null,
  bindBooking: id => { if (get().bookingId && get().bookingId !== id && get().lines.length) throw new Error('Mevcut sepet farklı bir konaklamaya ait. Önce mevcut siparişi kontrol edin.'); set({ bookingId: id }); },
  markSubmitted: () => set(state => ({ locked: true, serviceAt: state.serviceAt || new Date().toISOString() })),
  unlockRejected: () => set({ locked: false, serviceAt: undefined }),
  add: (item) =>
    set((s) => {
      if (s.locked) return {};
      const currency = item.currency?.toUpperCase();
      if (!currency || !/^[A-Z]{3}$/.test(currency) || s.lines.some(line => line.currency !== currency)) throw new Error('Farklı veya bilinmeyen para birimindeki ürünler aynı siparişe eklenemez.');
      if (!Number.isFinite(item.price) || item.price <= 0) throw new Error('Ürün fiyatı doğrulanamadı. Menüyü yenileyin.');
      const existing = s.lines.find((l) => l.itemId === item.id);
      if (existing) {
        if (existing.price !== item.price) throw new Error('Ürün fiyatı değişti. Mevcut sepeti kontrol edin.');
        if (existing.quantity >= 20) throw new Error('Bir üründen en fazla 20 adet sipariş edilebilir.');
        return {
          lines: s.lines.map((l) =>
            l.itemId === item.id ? { ...l, quantity: l.quantity + 1 } : l,
          ),
        };
      }
      return {
        lines: [
          ...s.lines,
          { itemId: item.id, name: item.name, price: item.price, quantity: 1, currency },
        ],
      };
    }),
  remove: (itemId) => set((s) => s.locked ? {} : ({ lines: s.lines.filter((l) => l.itemId !== itemId) })),
  setQty: (itemId, qty) =>
    set((s) => s.locked || !Number.isInteger(qty) || qty > 20 ? {} : ({
      lines:
        qty <= 0
          ? s.lines.filter((l) => l.itemId !== itemId)
          : s.lines.map((l) => (l.itemId === itemId ? { ...l, quantity: qty } : l)),
    })),
  clear: () => set({ lines: [], locked: false, bookingId: null, serviceAt: undefined, requestId: requestId() }),
  count: () => get().lines.reduce((n, l) => n + l.quantity, 0),
  total: () => get().lines.reduce((n, l) => n + l.price * l.quantity, 0),
}));
