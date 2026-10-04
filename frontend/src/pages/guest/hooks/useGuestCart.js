import { useState, useCallback, useMemo } from 'react';

const generateIdempotencyKey = () => {
  return [...Array(32)].map(() => Math.floor(Math.random() * 16).toString(16)).join('');
};

export function useGuestCart() {
  const [cart, setCart] = useState([]);
  const [snapshot, setSnapshot] = useState(null); // { key, payload }

  const clearSnapshot = useCallback(() => {
    setSnapshot(null);
  }, []);

  const updateCart = useCallback((newCart) => {
    setCart(newCart);
    setSnapshot(null); // Invalidate snapshot on edit
  }, []);

  const clearCart = useCallback(() => {
    setCart([]);
    setSnapshot(null);
  }, []);

  const updateItem = useCallback((serviceCode, updates) => {
    updateCart((prev) => {
      const idx = prev.findIndex(item => item.service_code === serviceCode);
      if (idx === -1) {
        if (prev.length >= 10) return prev;
        return [...prev, { service_code: serviceCode, ...updates }];
      }
      
      const newCart = [...prev];
      const updatedItem = { ...newCart[idx], ...updates };
      
      // Remove if quantity is zero (except if min is explicitly allowed to be 0, but user said "Do not use quantity zero as a valid selected item.")
      if (updatedItem.input_type === "quantity" && (updatedItem.value?.quantity || 0) <= 0) {
        newCart.splice(idx, 1);
      } else {
        newCart[idx] = updatedItem;
      }
      
      return newCart;
    });
  }, [updateCart]);

  const removeItem = useCallback((serviceCode) => {
    updateCart((prev) => prev.filter(item => item.service_code !== serviceCode));
  }, [updateCart]);

  const totalItems = useMemo(() => {
    return cart.reduce((acc, item) => {
      if (item.input_type === "quantity") {
        return acc + (item.value?.quantity || 1);
      }
      return acc + 1;
    }, 0);
  }, [cart]);

  const uniqueServices = cart.length;

  const hasChargeable = useMemo(() => {
    return cart.some(item => item.catalogueItem?.is_chargeable);
  }, [cart]);

  const roomChargeTotals = useMemo(() => cart.reduce((totals, item) => {
    const service = item.catalogueItem;
    if (!service?.room_charge_enabled || !service.currency) return totals;
    const quantity = item.input_type === "quantity" ? (item.value?.quantity || 1) : 1;
    const currency = service.currency;
    totals[currency] = (totals[currency] || 0) + (Number(service.unit_price_minor) || 0) * quantity;
    return totals;
  }, {}), [cart]);

  const hasRoomCharge = Object.values(roomChargeTotals).some(total => total > 0);

  return {
    cart,
    totalItems,
    uniqueServices,
    hasChargeable,
    hasRoomCharge,
    roomChargeTotals,
    updateItem,
    removeItem,
    clearCart,
    snapshot,
    setSnapshot,
    clearSnapshot,
    generateIdempotencyKey
  };
}
