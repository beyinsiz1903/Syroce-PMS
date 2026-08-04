import { useState, useCallback, useMemo } from 'react';

// Generates a random 32-char hex string (64-char max allowed by backend)
const generateIdempotencyKey = () => {
  return [...Array(32)].map(() => Math.floor(Math.random() * 16).toString(16)).join('');
};

export function useGuestCart() {
  const [cart, setCart] = useState([]);
  const [idempotencyKey, setIdempotencyKey] = useState(null);

  // When the user edits the cart, we must invalidate the previous idempotency key
  // because the "intent" has changed.
  const updateCart = useCallback((newCart) => {
    setCart(newCart);
    setIdempotencyKey(null); // Invalidate snapshot
  }, []);

  const getOrGenerateKey = useCallback(() => {
    if (idempotencyKey) return idempotencyKey;
    const newKey = generateIdempotencyKey();
    setIdempotencyKey(newKey);
    return newKey;
  }, [idempotencyKey]);

  const clearCart = useCallback(() => {
    setCart([]);
    setIdempotencyKey(null);
  }, []);

  // Update a single item in the cart
  const updateItem = useCallback((serviceCode, updates) => {
    updateCart((prev) => {
      const idx = prev.findIndex(item => item.service_code === serviceCode);
      if (idx === -1) {
        // Enforce max 10 unique services
        if (prev.length >= 10) return prev;
        return [...prev, { service_code: serviceCode, ...updates }];
      }
      
      const newCart = [...prev];
      const updatedItem = { ...newCart[idx], ...updates };
      
      // If quantity becomes 0 or less, or one_tap is explicitly removed, we drop it
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

  // Derived state
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

  return {
    cart,
    totalItems,
    uniqueServices,
    hasChargeable,
    updateItem,
    removeItem,
    clearCart,
    getOrGenerateKey,
    idempotencyKey
  };
}
