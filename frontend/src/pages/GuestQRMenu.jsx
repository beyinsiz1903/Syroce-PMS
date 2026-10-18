import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { toast, Toaster } from 'react-hot-toast';
import { ShoppingCart, Plus, Minus, Send, UtensilsCrossed } from 'lucide-react';
import { formatCurrency } from '@/lib/currency';

const GuestQRMenu = () => {
  const { tenantId, outletId } = useParams();
  const [categories, setCategories] = useState([]);
  const [cart, setCart] = useState({});
  const [tableId, setTableId] = useState('');
  const [guestName, setGuestName] = useState('');
  const [loading, setLoading] = useState(true);
  const [menuCurrency, setMenuCurrency] = useState('TRY');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [reload, setReload] = useState(0);
  const submittingRef = useRef(false);
  const pendingRef = useRef(null);
  const tableToken = new URLSearchParams(window.location.search).get('token') || '';
  const queryTable = new URLSearchParams(window.location.search).get('table') || '';
  const storageKey = `pos-guest-pending:${tenantId}:${outletId}:${queryTable}`;

  useEffect(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
      if (saved?.body?.table_token === tableToken) {
        pendingRef.current = saved.body;
        setCart(saved.cart);
        setGuestName(saved.body.guest_name || '');
      }
    } catch { /* Unavailable storage is checked before sending any order. */ }
  }, [storageKey, tableToken]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    // URL params like ?table=12
    const params = new URLSearchParams(window.location.search);
    setTableId(params.get('table') || '');

    const fetchMenu = async () => {
      try {
        const response = await axios.get(`/public/fnb/${encodeURIComponent(tenantId)}/${encodeURIComponent(outletId)}/menu`);
        if (!active) return;
        setCategories(response.data.categories || []);
        setMenuCurrency(response.data.currency || 'TRY');
      } catch (error) {
        if (!active) return;
        setError(typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : 'Menü yüklenemedi. Lütfen personelden yardım isteyin.');
        toast.error("Menü yüklenirken bir hata oluştu.");
      } finally {
        if (active) setLoading(false);
      }
    };
    fetchMenu();
    return () => { active = false; };
  }, [tenantId, outletId, reload]);

  const updateCart = (item, delta) => {
    if (pendingRef.current || submittingRef.current) return;
    setCart(prev => {
      const current = prev[item.id] || { ...item, qty: 0 };
      const nextQty = Math.max(0, current.qty + delta);
      const newCart = { ...prev };
      
      if (nextQty === 0) {
        delete newCart[item.id];
      } else {
        newCart[item.id] = { ...current, qty: nextQty };
      }
      return newCart;
    });
  };

  const totalsByCurrency = Object.values(cart).reduce((totals, item) => {
    const currency = String(item.currency || menuCurrency).toUpperCase();
    const subtotal = Math.round(item.unit_price * item.qty * 100) / 100;
    const tax = Math.round(subtotal * Number(item.tax_rate || 0) * 100) / 100;
    totals[currency] = (totals[currency] || 0) + subtotal + tax;
    return totals;
  }, {});

  const placeOrder = async () => {
    if (submittingRef.current) return;
    if (Object.keys(cart).length === 0 || !tableId || !tableToken) { toast.error('Güncel masa QR kodunu okutun; gerekirse personelden yardım isteyin.'); return; }
    submittingRef.current = true;
    setSubmitting(true);
    
    try {
      const items = Object.values(cart).map(it => ({
        item_id: it.id,
        quantity: it.qty
      }));
      
      if (!pendingRef.current) pendingRef.current = {
        table_id: tableId,
        table_token: tableToken,
        idempotency_key: crypto.randomUUID(),
        guest_name: guestName,
        items,
        expected_total: Math.round(Object.values(totalsByCurrency).reduce((sum, value) => sum + value, 0) * 100) / 100,
      };
      try { sessionStorage.setItem(storageKey, JSON.stringify({ body: pendingRef.current, cart })); }
      catch { pendingRef.current = null; throw new Error('Siparişin güvenli tekrar kaydı tutulamadı. Tarayıcı oturum depolamasını açın; sipariş gönderilmedi.'); }
      await axios.post(`/public/fnb/${encodeURIComponent(tenantId)}/${encodeURIComponent(outletId)}/order`, pendingRef.current);
      
      toast.success("Siparişiniz başarıyla mutfağa iletildi!");
      setCart({});
      pendingRef.current = null;
      sessionStorage.removeItem(storageKey);
    } catch (error) {
      const status = error?.response?.status;
      if (status && status < 500) {
        pendingRef.current = null;
        sessionStorage.removeItem(storageKey);
        if (status === 409) { setCart({}); setReload(value => value + 1); }
      }
      toast.error(typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : error?.message?.startsWith('Siparişin güvenli') ? error.message : 'Sipariş sonucu belirsiz. Aynı siparişi yeniden göndermek için tekrar deneyin; yeni sipariş oluşturulmaz.');
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-screen bg-gray-50"><div className="animate-spin text-blue-500"><UtensilsCrossed size={48} /></div></div>;
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-32">
      <Toaster position="top-center" />
      {error && <div role="alert" className="m-4 rounded border border-red-200 bg-red-50 p-4 text-red-800">{error} <button onClick={() => setReload(value => value + 1)}>Menüyü yeniden yükle</button></div>}
      {pendingRef.current && <div role="status" className="m-4 rounded border p-4">Önceki siparişinizin sonucu doğrulanamadı. Aynı siparişi tekrar deneyin; yeni sipariş açılmaz.</div>}
      {!tableToken && <div role="alert" className="m-4 rounded border border-amber-200 bg-amber-50 p-4 text-amber-800">Bu eski QR kodu ile sipariş verilemez. Personelden güncel masa QR kodunu isteyin.</div>}
      
      {/* Header */}
      <div className="bg-white p-4 shadow-sm sticky top-0 z-10">
        <h1 className="text-xl font-bold text-center text-gray-800">Dijital Menü</h1>
        <div className="text-center text-sm text-gray-500">{tableId ? `Masa: ${tableId}` : 'Geçersiz QR kodu'}</div>
      </div>

      {/* Menu Categories */}
      <div className="max-w-3xl mx-auto p-4 space-y-8">
        {!error && categories.length === 0 && <p role="status">Bu satış noktasında şu an sipariş verilebilecek ürün yok. Personelden yardım isteyin.</p>}
        {categories.map(cat => (
          <div key={cat.name}>
            <h2 className="text-lg font-bold text-gray-800 border-b pb-2 mb-4">{cat.name}</h2>
            <div className="space-y-4">
              {cat.items.map(item => (
                <div key={item.id} className="bg-white p-4 rounded-xl shadow-sm flex justify-between items-center">
                  <div>
                    <h3 className="font-semibold text-gray-800">{item.item_name}</h3>
                    <p className="text-blue-600 font-bold mt-1">{formatCurrency(item.unit_price * (1 + Number(item.tax_rate || 0)), item.currency || menuCurrency)} <span className="text-xs font-normal">KDV dahil</span></p>
                  </div>
                  
                  <div className="flex items-center space-x-3 bg-gray-100 rounded-full p-1">
                    <button 
                      onClick={() => updateCart(item, -1)} aria-label={`${item.item_name} azalt`}
                      disabled={submitting || Boolean(pendingRef.current)}
                      className="w-8 h-8 flex items-center justify-center bg-white rounded-full shadow-sm text-gray-600 hover:text-red-500"
                    >
                      <Minus size={16} />
                    </button>
                    <span className="w-4 text-center font-semibold">{cart[item.id]?.qty || 0}</span>
                    <button 
                      onClick={() => updateCart(item, 1)} aria-label={`${item.item_name} ekle`}
                      disabled={submitting || Boolean(pendingRef.current) || (cart[item.id]?.qty || 0) >= 100}
                      className="w-8 h-8 flex items-center justify-center bg-white rounded-full shadow-sm text-gray-600 hover:text-green-500"
                    >
                      <Plus size={16} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Floating Cart Panel */}
      {Object.keys(cart).length > 0 && (
        <div className="fixed bottom-0 left-0 right-0 bg-white shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.1)] p-4 border-t">
          <div className="max-w-3xl mx-auto flex items-center justify-between">
            <div>
              <div className="text-sm text-gray-500 font-medium">Toplam Tutar</div>
              <div className="text-xl font-bold text-gray-800">
                {Object.entries(totalsByCurrency).map(([currency, amount]) => (
                  <span key={currency} className="block">{formatCurrency(amount, currency)}</span>
                ))}
              </div>
            </div>
            
            <button 
              onClick={placeOrder} disabled={!tableId || !tableToken || submitting}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-xl font-semibold flex items-center space-x-2"
            >
              <span>{submitting ? 'Gönderiliyor…' : pendingRef.current ? 'Aynı siparişi tekrar dene' : 'Siparişi Ver'}</span>
              <Send size={18} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default GuestQRMenu;
