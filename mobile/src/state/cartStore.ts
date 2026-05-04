import { create } from 'zustand';
import { MenuItem } from '../api/guestRoomService';

export type CartLine = {
  itemId: string;
  name: string;
  price: number;
  quantity: number;
};

type CartState = {
  lines: CartLine[];
  add: (item: MenuItem) => void;
  remove: (itemId: string) => void;
  setQty: (itemId: string, qty: number) => void;
  clear: () => void;
  count: () => number;
  total: () => number;
};

export const useCartStore = create<CartState>((set, get) => ({
  lines: [],
  add: (item) =>
    set((s) => {
      const existing = s.lines.find((l) => l.itemId === item.id);
      if (existing) {
        return {
          lines: s.lines.map((l) =>
            l.itemId === item.id ? { ...l, quantity: l.quantity + 1 } : l,
          ),
        };
      }
      return {
        lines: [
          ...s.lines,
          { itemId: item.id, name: item.name, price: item.price, quantity: 1 },
        ],
      };
    }),
  remove: (itemId) => set((s) => ({ lines: s.lines.filter((l) => l.itemId !== itemId) })),
  setQty: (itemId, qty) =>
    set((s) => ({
      lines:
        qty <= 0
          ? s.lines.filter((l) => l.itemId !== itemId)
          : s.lines.map((l) => (l.itemId === itemId ? { ...l, quantity: qty } : l)),
    })),
  clear: () => set({ lines: [] }),
  count: () => get().lines.reduce((n, l) => n + l.quantity, 0),
  total: () => get().lines.reduce((n, l) => n + l.price * l.quantity, 0),
}));
