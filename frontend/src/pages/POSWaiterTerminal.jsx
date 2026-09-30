import { useTranslation } from "react-i18next";
import { toast } from 'sonner';
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { UtensilsCrossed, ArrowLeft, Store, LayoutGrid, ShoppingCart, Plus, Minus, Check, CreditCard, Banknote, BedDouble, Eraser, Calendar, Loader2, Send, ArrowRightLeft, XCircle, Trash2, Split, RotateCcw } from 'lucide-react';
import { alertDialog, confirmDialog } from '@/lib/dialogs';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';

// Touch-first waiter terminal: outlet -> table -> open check -> KDS -> payment.
// The v2 order lifecycle keeps the table/check open until an explicit close.

const STEPS = {
  OUTLET: 'outlet',
  TABLE: 'table',
  ORDER: 'order'
};

export const normalizeWaiterMenuItems = list => list
  .filter(item => !['inactive', 'deleted'].includes(item.status))
  .map(item => ({
    ...item,
    item_name: item.item_name || item.name || '',
    unit_price: Number(item.unit_price ?? item.price ?? 0),
    tax_rate: Number(item.tax_rate ?? 0.18),
  }));

const POSWaiterTerminal = () => {
  const {
    t
  } = useTranslation();
  const navigate = useNavigate();
  const [step, setStep] = useState(STEPS.OUTLET);
  const [outlets, setOutlets] = useState([]);
  const [outlet, setOutlet] = useState(null);
  const [tables, setTables] = useState([]);
  const [table, setTable] = useState(null);
  const [menuItems, setMenuItems] = useState([]);
  const [category, setCategory] = useState('all');
  const [cart, setCart] = useState([]);
  const [inhouse, setInhouse] = useState([]);
  const [roomBooking, setRoomBooking] = useState(null);
  const [guestSearch, setGuestSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingOutlets, setLoadingOutlets] = useState(true);
  const [loadingTables, setLoadingTables] = useState(false);
  const [loadingMenu, setLoadingMenu] = useState(false);
  const [loadingInhouse, setLoadingInhouse] = useState(false);
  const [lastOrder, setLastOrder] = useState(null);
  const [activeOrder, setActiveOrder] = useState(null);
  const [transferTarget, setTransferTarget] = useState('');
  const [splitOpen, setSplitOpen] = useState(false);
  const [splitCount, setSplitCount] = useState(2);
  const [splitMethods, setSplitMethods] = useState(['cash', 'card']);
  const [tipAmount, setTipAmount] = useState('0');
  const pendingKeyRef = useRef(null);

  // Signature pad (canvas) — captured for room charges as proof of authorization.
  const canvasRef = useRef(null);
  const drawingRef = useRef(false);
  const hasSignatureRef = useRef(false);
  const loadOutlets = useCallback(async () => {
    try {
      setLoadingOutlets(true);
      const res = await axios.get('/pos/outlets');
      const list = Array.isArray(res.data) ? res.data : res.data.outlets || [];
      setOutlets(list.filter(o => !['inactive', 'deleted'].includes(o.status)));
    } catch (err) {
      console.error('Satış noktaları yüklenemedi:', err);
      toast.error('Satış noktaları yüklenemedi');
    } finally {
      setLoadingOutlets(false);
    }
  }, []);
  useEffect(() => {
    loadOutlets();
  }, [loadOutlets]);
  const loadTables = useCallback(async outletId => {
    try {
      setLoadingTables(true);
      const res = await axios.get(`/pos/table-layout/${outletId}`);
      setTables(res.data.tables || []);
    } catch (err) {
      console.error('Masalar yüklenemedi:', err); toast.error('Masalar yüklenemedi');
      setTables([]);
    } finally {
      setLoadingTables(false);
    }
  }, []);
  const loadMenu = useCallback(async outletId => {
    try {
      setLoadingMenu(true);
      const res = await axios.get('/pos/menu-items', {
        params: {
          outlet_id: outletId
        }
      });
      const list = Array.isArray(res.data) ? res.data : res.data.menu_items || [];
      setMenuItems(normalizeWaiterMenuItems(list));
    } catch (err) {
      console.error('Menü yüklenemedi:', err); toast.error('Menü yüklenemedi');
      setMenuItems([]);
    } finally {
      setLoadingMenu(false);
    }
  }, []);
  const loadInhouse = useCallback(async () => {
    try {
      setLoadingInhouse(true);
      const res = await axios.get('/frontdesk/inhouse');
      setInhouse(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      console.error('Konaklayan misafirler yüklenemedi:', err);
      toast.error('Konaklayan misafirler yüklenemedi');
      setInhouse([]);
    } finally {
      setLoadingInhouse(false);
    }
  }, []);
  const pickOutlet = o => {
    setOutlet(o);
    setTable(null);
    setCart([]);
    loadTables(o.id);
    loadMenu(o.id);
    setStep(STEPS.TABLE);
  };
  const pickTable = async t => {
    setTable(t);
    setCart([]);
    setRoomBooking(null);
    setTransferTarget('');
    if (t.current_order_id) {
      try {
        const response = await axios.get(`/pos/v2/orders/${t.current_order_id}`);
        setActiveOrder(response.data?.order || null);
      } catch (error) {
        console.error('Açık adisyon yüklenemedi:', error);
        toast.error('Masanın açık adisyonu yüklenemedi');
        return;
      }
    } else {
      setActiveOrder(null);
    }
    setStep(STEPS.ORDER);
  };
  const addToCart = item => {
    if (item.available === false) return;
    setCart(prev => {
      const existing = prev.find(c => c.item_id === item.id);
      if (existing) {
        return prev.map(c => c.item_id === item.id ? {
          ...c,
          quantity: c.quantity + 1
        } : c);
      }
      return [...prev, {
        item_id: item.id,
        item_name: item.item_name,
        unit_price: item.unit_price,
        category: item.category,
        tax_rate: item.tax_rate,
        station: item.station || 'main',
        quantity: 1
      }];
    });
  };
  const changeQty = (itemId, delta) => {
    setCart(prev => prev.map(c => {
      if (c.item_id !== itemId) return c;
      const q = c.quantity + delta;
      return q > 0 ? {
        ...c,
        quantity: q
      } : null;
    }).filter(Boolean));
  };
  const subtotal = cart.reduce((s, c) => s + c.unit_price * c.quantity, 0);
  const tax = cart.reduce((s, c) => s + c.unit_price * c.quantity * c.tax_rate, 0);
  const pendingTotal = subtotal + tax;
  const activeTotal = Number(activeOrder?.grand_total || 0);
  const total = activeTotal + pendingTotal;
  const currency = String(outlet?.currency || cachedTenantCurrency()).toUpperCase();
  const money = amount => formatCurrency(amount, currency);
  const categories = ['all', ...Array.from(new Set(menuItems.map(item => item.category).filter(Boolean)))];
  const categoryLabels = {
    all: 'Tümü', food: 'Ana Yemek', beverage: 'İçecek', alcohol: 'Alkollü',
    dessert: 'Tatlı', appetizer: 'Başlangıç',
  };
  const visibleItems = category === 'all' ? menuItems : menuItems.filter(m => m.category === category);

  // ── Signature canvas ──────────────────────────────────────────────────
  const canvasPoint = e => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const touch = e.touches?.[0];
    const clientX = touch ? touch.clientX : e.clientX;
    const clientY = touch ? touch.clientY : e.clientY;
    return {
      x: (clientX - rect.left) * (canvas.width / rect.width),
      y: (clientY - rect.top) * (canvas.height / rect.height)
    };
  };
  const startDraw = e => {
    e.preventDefault();
    drawingRef.current = true;
    const ctx = canvasRef.current.getContext('2d');
    const {
      x,
      y
    } = canvasPoint(e);
    ctx.beginPath();
    ctx.moveTo(x, y);
  };
  const moveDraw = e => {
    if (!drawingRef.current) return;
    e.preventDefault();
    const ctx = canvasRef.current.getContext('2d');
    const {
      x,
      y
    } = canvasPoint(e);
    ctx.lineTo(x, y);
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#111827';
    ctx.lineCap = 'round';
    ctx.stroke();
    hasSignatureRef.current = true;
  };
  const endDraw = () => {
    drawingRef.current = false;
  };
  const clearSignature = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
    hasSignatureRef.current = false;
  };
  const resetForNext = () => {
    setCart([]);
    setActiveOrder(null);
    setRoomBooking(null);
    setGuestSearch('');
    clearSignature();
  };
  const buildOrderItems = () => cart.map(c => ({
    item_id: c.item_id,
    name: c.item_name,
    quantity: c.quantity,
    price: c.unit_price,
    tax_rate: c.tax_rate,
    station: c.station || 'main',
  }));
  const refreshActiveOrder = async orderId => {
    const response = await axios.get(`/pos/v2/orders/${orderId}`);
    const next = response.data?.order || null;
    setActiveOrder(next);
    return next;
  };
  const ensureOpenOrder = async () => {
    if (activeOrder && cart.length === 0) return activeOrder;
    if (cart.length === 0) throw new Error('EMPTY_ORDER');
    if (!pendingKeyRef.current) {
      pendingKeyRef.current = globalThis.crypto?.randomUUID?.() || `pos-term-${Date.now()}-${Math.random()}`;
    }
    let orderId = activeOrder?.id;
    if (orderId) {
      await axios.post(`/pos/v2/orders/${orderId}/items`, {
        items: buildOrderItems(),
        idempotency_key: pendingKeyRef.current,
      });
    } else {
      const response = await axios.post('/pos/v2/orders', {
        outlet_id: outlet.id,
        table_number: String(table.table_number),
        items: buildOrderItems(),
        order_type: 'dine_in',
        idempotency_key: pendingKeyRef.current,
      });
      orderId = response.data?.order_id;
    }
    pendingKeyRef.current = null;
    setCart([]);
    await loadTables(outlet.id);
    return refreshActiveOrder(orderId);
  };
  const sendToKitchen = async () => {
    setLoading(true);
    try {
      await ensureOpenOrder();
      toast.success('Sipariş mutfağa gönderildi ve adisyon açık bırakıldı');
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Sipariş mutfağa gönderilemedi');
    } finally {
      setLoading(false);
    }
  };
  const submitOrder = async (paymentMethod, payments = null) => {
    if (cart.length === 0 && !activeOrder) {
      alertDialog({
        message: 'Adisyonda ürün bulunmuyor.'
      });
      return;
    }
    if (paymentMethod === 'room_charge') {
      if (!roomBooking) {
        alertDialog({
          message: 'Odaya yazmak için konaklayan bir misafir seçin.'
        });
        return;
      }
      if (!hasSignatureRef.current) {
        alertDialog({
          message: 'Odaya yazma işlemi için misafir imzası gereklidir.'
        });
        return;
      }
    }
    setLoading(true);
    try {
      const order = await ensureOpenOrder();
      const closeKey = globalThis.crypto?.randomUUID?.() || `pos-close-${Date.now()}-${Math.random()}`;
      const signature = paymentMethod === 'room_charge' && hasSignatureRef.current ? canvasRef.current.toDataURL('image/png') : null;
      const res = await axios.post('/pos/v2/orders/close', {
          order_id: order.id,
          booking_id: paymentMethod === 'room_charge' ? roomBooking?.id || null : null,
          payment_method: paymentMethod,
          post_to_folio: paymentMethod === 'room_charge',
          guest_signature: signature,
          idempotency_key: closeKey,
          tip_amount: Number(tipAmount || 0),
          payments,
      });
      if (res.status >= 200 && res.status < 300) {
        const data = res.data || {};
        setLastOrder({ ...order, total_amount: data.amount_paid, payment_method: data.payment_method });
        if (data.idempotent) {
          alertDialog({
            message: 'Bu sipariş daha önce oluşturulmuş; ikinci kez hesap kesilmedi.'
          });
        } else {
          alertDialog({
            message: paymentMethod === 'room_charge'
              ? 'Adisyon kapatıldı ve oda folyosuna gönderildi.'
              : 'Adisyon kapatıldı ve ödeme kaydedildi.'
          });
        }
        resetForNext();
        setSplitOpen(false);
        setTipAmount('0');
        if (outlet) await loadTables(outlet.id);
        setTable(null);
        setStep(STEPS.TABLE);
      }
    } catch (err) {
      console.error('Sipariş hatası:', err);
      const status = err?.response?.status;
      if (status && status < 500) pendingKeyRef.current = null;
      const detail = err?.response?.data?.detail;
      alertDialog({
        message: typeof detail === 'string'
          ? detail
          : 'Sipariş oluşturulamadı. Bağlantınızı kontrol edip yeniden deneyin.'
      });
    } finally {
      setLoading(false);
    }
  };
  const submitSplitPayment = async () => {
    const count = Math.max(2, Math.min(8, Number(splitCount) || 2));
    const payableCents = Math.round((total + Number(tipAmount || 0)) * 100);
    const base = Math.floor(payableCents / count);
    const remainder = payableCents - base * count;
    const payments = Array.from({ length: count }, (_, index) => ({
      method: splitMethods[index] || 'cash',
      amount: (base + (index === count - 1 ? remainder : 0)) / 100,
    }));
    await submitOrder('mixed', payments);
  };
  const changeSplitCount = value => {
    const count = Math.max(2, Math.min(8, Number(value) || 2));
    setSplitCount(count);
    setSplitMethods(previous => Array.from({ length: count }, (_, index) => previous[index] || (index % 2 ? 'card' : 'cash')));
  };
  const voidOrderItem = async index => {
    if (!activeOrder?.id) return;
    const item = activeOrder.order_items?.[index];
    const confirmed = await confirmDialog({ message: `${item?.item_name || 'Bu kalem'} adisyondan ve mutfak kuyruğundan iptal edilsin mi?` });
    if (!confirmed) return;
    setLoading(true);
    try {
      await axios.post(`/pos/v2/orders/${activeOrder.id}/items/void`, {
        line_index: index,
        reason: 'Garson terminalinden kalem iptali',
      });
      await refreshActiveOrder(activeOrder.id);
      toast.success('Kalem iptal edildi; mutfak ekranı güncellendi');
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Kalem iptal edilemedi');
    } finally {
      setLoading(false);
    }
  };
  const refundLastOrder = async () => {
    if (!lastOrder?.id) return;
    const confirmed = await confirmDialog({ message: 'Son adisyonun tamamı iade edilsin mi? Bu işlem kayıt altına alınır.' });
    if (!confirmed) return;
    setLoading(true);
    try {
      await axios.post(`/pos/v2/orders/${lastOrder.id}/refund`, {
        reason: 'Garson terminalinden tam iade',
        idempotency_key: globalThis.crypto?.randomUUID?.() || `pos-refund-${Date.now()}`,
      });
      setLastOrder(previous => ({ ...previous, refunded: true }));
      toast.success('İade kaydedildi');
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'İade kaydedilemedi');
    } finally {
      setLoading(false);
    }
  };
  const transferOrder = async () => {
    if (!activeOrder?.id || !transferTarget) return;
    setLoading(true);
    try {
      await axios.post(`/pos/v2/orders/${activeOrder.id}/transfer-table`, {
        to_table_number: transferTarget,
      });
      toast.success(`Adisyon Masa ${transferTarget} üzerine aktarıldı`);
      await loadTables(outlet.id);
      setTable(prev => ({ ...prev, table_number: transferTarget }));
      setActiveOrder(prev => ({ ...prev, table_number: transferTarget }));
      setTransferTarget('');
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Masa transferi yapılamadı');
    } finally {
      setLoading(false);
    }
  };
  const voidActiveOrder = async () => {
    if (!activeOrder?.id) return;
    const confirmed = await confirmDialog({ message: 'Açık adisyon iptal edilsin mi? Mutfak fişi de iptal edilir.' });
    if (!confirmed) return;
    setLoading(true);
    try {
      await axios.post('/pos/v2/orders/void', { order_id: activeOrder.id, reason: 'Garson terminalinden iptal edildi' });
      toast.success('Adisyon iptal edildi');
      resetForNext();
      await loadTables(outlet.id);
      setTable(null);
      setStep(STEPS.TABLE);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Adisyon iptal edilemedi');
    } finally {
      setLoading(false);
    }
  };
  const statusColor = s => ({
    available: 'bg-green-100 text-green-800 border-green-300',
    occupied: 'bg-red-100 text-red-800 border-red-300',
    reserved: 'bg-amber-100 text-amber-800 border-amber-300',
    dirty: 'bg-gray-100 text-gray-700 border-gray-300'
  })[s] || 'bg-gray-100 text-gray-700 border-gray-300';
  const statusLabel = s => ({
    available: 'Müsait', occupied: 'Dolu', reserved: 'Rezerve', dirty: 'Temizlenecek',
  })[s] || 'Durum bilinmiyor';
  const outletTypeLabel = type => ({
    restaurant: 'Restoran', bar: 'Bar', cafe: 'Kafe', room_service: 'Oda Servisi',
    banquet: 'Banket', spa: 'SPA',
  })[type] || type;
  const filteredInhouse = inhouse.filter(b => {
    if (!guestSearch.trim()) return true;
    const q = guestSearch.toLowerCase();
    const name = (b.guest?.full_name || b.guest_name || '').toLowerCase();
    const room = String(b.room?.room_number || b.room_number || '').toLowerCase();
    return name.includes(q) || room.includes(q);
  });
  return <div className="p-4 md:p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold flex items-center gap-3">
            <UtensilsCrossed className="w-7 h-7 text-amber-600" />{t("cm.pages_POSWaiterTerminal.garson_terminali")}</h1>
          <p className="text-gray-600 mt-1 text-sm">
            {outlet ? outlet.outlet_name || outlet.name : 'Satış noktası seçin'}
            {table ? ` • Masa ${table.table_number}` : ''}
          </p>
        </div>
        <Button variant="outline" onClick={() => navigate('/pos')} data-testid="btn-back-pos">
          <ArrowLeft className="w-4 h-4 mr-2" />{t("cm.pages_POSWaiterTerminal.pos_paneli")}</Button>
      </div>

      {/* Step 1: Outlet */}
      {step === STEPS.OUTLET && <div>
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Store className="w-5 h-5 text-amber-600" />{t("cm.pages_POSWaiterTerminal.satis_noktasi")}</h2>
          {loadingOutlets ? (
            <Card><CardContent className="p-12 flex items-center justify-center gap-3 text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin" /> Satış noktaları yükleniyor…
            </CardContent></Card>
          ) : outlets.length === 0 ? (
            <Card className="border-dashed border-2 bg-gray-50">
              <CardContent className="p-12 text-center flex flex-col items-center justify-center">
                <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center shadow-sm mb-4">
                  <Store className="w-8 h-8 text-gray-400" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">Satış Noktası Bulunamadı</h3>
                <p className="text-gray-500 max-w-sm mx-auto mb-6">
                  Garson terminalini kullanabilmek için öncelikle POS Paneli üzerinden en az bir satış noktası (Örn: Restoran, Bar) eklemeniz gerekmektedir.
                </p>
                <Button onClick={() => navigate('/pos')} variant="outline" className="gap-2">
                  <ArrowLeft className="w-4 h-4" />
                  POS Paneline Dön
                </Button>
              </CardContent>
            </Card>
          ) : <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {outlets.map(o => <Card key={o.id} className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => pickOutlet(o)} data-testid={`outlet-${o.id}`}>
                  <CardContent className="p-5 text-center">
                    <Store className="w-8 h-8 mx-auto mb-2 text-amber-600" />
                    <div className="font-semibold">{o.outlet_name || o.name}</div>
                    {o.outlet_type && <Badge variant="outline" className="mt-2">{outletTypeLabel(o.outlet_type)}</Badge>}
                  </CardContent>
                </Card>)}
            </div>}
        </div>}

      {/* Step 2: Table */}
      {step === STEPS.TABLE && <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <LayoutGrid className="w-5 h-5 text-amber-600" />{t("cm.pages_POSWaiterTerminal.masa_sec")}</h2>
            <Button variant="ghost" size="sm" onClick={() => setStep(STEPS.OUTLET)}>
              <ArrowLeft className="w-4 h-4 mr-1" />{t("cm.pages_POSWaiterTerminal.satis_noktasi")}</Button>
          </div>
          {loadingTables ? <Card><CardContent className="p-8 flex items-center justify-center gap-2 text-gray-500"><Loader2 className="w-5 h-5 animate-spin" /> Masalar yükleniyor…</CardContent></Card> : tables.length === 0 ? <Card><CardContent className="p-8 text-center text-gray-500">{t("cm.pages_POSWaiterTerminal.bu_satis_noktasinda_masa_bulun")}</CardContent></Card> : <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
              {tables.map(tbl => <button key={tbl.id} onClick={() => pickTable(tbl)} data-testid={`table-${tbl.table_number}`} className={`rounded-lg border-2 p-4 text-center transition-shadow hover:shadow-md ${statusColor(tbl.status)}`}>
                  <div className="text-xl font-bold">{tbl.table_number}</div>
                  <div className="text-xs mt-1">{tbl.seats} {t("cm.pages_POSWaiterTerminal.kisi")}</div>
                  <div className="text-[11px] mt-1 font-medium">{statusLabel(tbl.status)}</div>
                  {Number(tbl.current_bill || 0) > 0 && <div className="text-xs mt-1 font-bold">{money(tbl.current_bill)}</div>}
                </button>)}
            </div>}
        </div>}

      {/* Step 3: Menu + Cart */}
      {step === STEPS.ORDER && <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Menu */}
          <div className="lg:col-span-2 space-y-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <Button variant="ghost" size="sm" onClick={() => setStep(STEPS.TABLE)}>
                <ArrowLeft className="w-4 h-4 mr-1" />{t("cm.pages_POSWaiterTerminal.masalar")}</Button>
              <div className="flex gap-1 flex-wrap">
                {categories.map(c => <Button key={c} size="sm" variant={category === c ? 'default' : 'outline'} onClick={() => setCategory(c)}>
                    {categoryLabels[c] || c}
                  </Button>)}
              </div>
            </div>
            {loadingMenu ? <div className="py-16 flex items-center justify-center gap-2 text-gray-500"><Loader2 className="w-5 h-5 animate-spin" /> Menü yükleniyor…</div> : <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {visibleItems.map(item => <Card key={item.id}
                aria-disabled={item.available === false}
                className={item.available === false
                  ? 'cursor-not-allowed opacity-60'
                  : 'cursor-pointer hover:shadow-md transition-shadow'}
                onClick={() => addToCart(item)} data-testid={`menu-item-${item.id}`}>
                  <CardContent className="p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="font-semibold text-sm leading-tight">{item.item_name}</div>
                      {item.available === false && <Badge variant="destructive">Tükendi</Badge>}
                    </div>
                    <Badge variant="outline" className="mt-1 text-xs">{categoryLabels[item.category] || item.category}</Badge>
                    <div className="mt-2 font-bold text-amber-700">
                      {money(item.unit_price)}</div>
                  </CardContent>
                </Card>)}
              {visibleItems.length === 0 && <div className="col-span-full text-center text-gray-500 py-8">{t("cm.pages_POSWaiterTerminal.bu_kategoride_urun_yok")}</div>}
            </div>}
          </div>

          {/* Cart */}
          <div className="space-y-3">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <ShoppingCart className="w-5 h-5" />{t("cm.pages_POSWaiterTerminal.adisyon")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {activeOrder && <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm" data-testid="active-order-summary">
                    <div className="flex items-center justify-between gap-2">
                      <div><span className="font-semibold">Açık adisyon</span><div className="text-xs text-gray-600">{activeOrder.order_number}</div></div>
                      <span className="font-bold text-emerald-700">{money(activeTotal)}</span>
                    </div>
                    <div className="mt-3 space-y-1 border-t border-emerald-200 pt-2">
                      {(activeOrder.order_items || []).map((item, index) => <div key={`${item.line_id || item.item_id || item.item_name}-${index}`} className="flex items-center justify-between gap-2 text-xs">
                          <span className="truncate">{item.quantity} × {item.item_name || item.name}</span>
                          <span className="ml-auto shrink-0 font-medium">{money(item.total ?? item.unit_price * item.quantity)}</span>
                          <button type="button" aria-label={`${item.item_name || 'Kalem'} iptal et`} className="rounded p-1 text-red-600 hover:bg-red-100" disabled={loading} onClick={() => voidOrderItem(index)} data-testid={`void-order-item-${index}`}><Trash2 className="h-3.5 w-3.5" /></button>
                        </div>)}
                    </div>
                    <div className="mt-3 flex gap-2">
                      <select className="h-9 flex-1 rounded-md border bg-white px-2 text-sm" value={transferTarget} onChange={event => setTransferTarget(event.target.value)} aria-label="Hedef masa">
                        <option value="">Başka masaya aktar…</option>
                        {tables.filter(candidate => candidate.id !== table?.id && candidate.status === 'available' && !candidate.current_order_id).map(candidate => <option key={candidate.id} value={candidate.table_number}>Masa {candidate.table_number}</option>)}
                      </select>
                      <Button size="sm" variant="outline" disabled={!transferTarget || loading} onClick={transferOrder} data-testid="transfer-table"><ArrowRightLeft className="h-4 w-4 mr-1" />Aktar</Button>
                      <Button size="sm" variant="destructive" disabled={loading} onClick={voidActiveOrder} data-testid="void-order"><XCircle className="h-4 w-4 mr-1" />İptal</Button>
                    </div>
                  </div>}
                {cart.length === 0 && !activeOrder ? <div className="text-center text-gray-500 py-6 text-sm">{t("cm.pages_POSWaiterTerminal.urun_eklemek_icin_menuden_seci")}</div> : cart.length > 0 ? <div className="space-y-2">
                    {cart.map(c => <div key={c.item_id} className="flex items-center justify-between gap-2 p-2 bg-gray-50 rounded">
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-sm truncate">{c.item_name}</div>
                          <div className="text-xs text-gray-600">
                            {money(c.unit_price)} / adet</div>
                        </div>
                        <div className="flex items-center gap-1">
                          <Button size="sm" variant="outline" onClick={() => changeQty(c.item_id, -1)} data-testid={`cart-minus-${c.item_id}`}>
                            <Minus className="w-3 h-3" />
                          </Button>
                          <span className="w-7 text-center font-medium">{c.quantity}</span>
                          <Button size="sm" variant="outline" onClick={() => changeQty(c.item_id, 1)} data-testid={`cart-plus-${c.item_id}`}>
                            <Plus className="w-3 h-3" />
                          </Button>
                        </div>
                      </div>)}
                  </div> : null}

                {(cart.length > 0 || activeOrder) && <div className="border-t pt-3 space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span>{activeOrder ? 'Yeni eklenenler' : t("cm.pages_POSWaiterTerminal.ara_toplam")}</span><span>{money(pendingTotal)}</span>
                    </div>
                    <div className="flex justify-between font-bold text-base border-t pt-1">
                      <span>{t("cm.pages_POSWaiterTerminal.toplam")}</span>
                      <span className="text-amber-700">{money(total)}</span>
                    </div>
                  </div>}
              </CardContent>
            </Card>

            {/* Payment actions */}
            {(cart.length > 0 || activeOrder) && <Card>
                <CardContent className="p-3 space-y-3">
                  {cart.length > 0 && <Button className="w-full bg-amber-600 hover:bg-amber-700" disabled={loading} onClick={sendToKitchen} data-testid="send-kitchen">
                    <Send className="w-4 h-4 mr-2" />{activeOrder ? 'Yeni Ürünleri Mutfağa Gönder' : 'Mutfağa Gönder ve Adisyonu Aç'}
                  </Button>}
                  <div className="grid grid-cols-2 gap-2">
                    <Button variant="outline" disabled={loading} onClick={() => submitOrder('cash')} data-testid="pay-cash">
                      <Banknote className="w-4 h-4 mr-2" />{t("cm.pages_POSWaiterTerminal.nakit")}</Button>
                    <Button variant="outline" disabled={loading} onClick={() => submitOrder('card')} data-testid="pay-card">
                      <CreditCard className="w-4 h-4 mr-2" />{t("cm.pages_POSWaiterTerminal.kart")}</Button>
                  </div>
                  <Button variant="outline" className="w-full" disabled={loading} onClick={() => setSplitOpen(value => !value)} data-testid="toggle-split-payment">
                    <Split className="w-4 h-4 mr-2" />Hesabı Böl / Karma Öde
                  </Button>
                  {splitOpen && <div className="rounded-lg border bg-gray-50 p-3 space-y-3" data-testid="split-payment-panel">
                    <div className="grid grid-cols-2 gap-2">
                      <label className="text-xs font-medium text-gray-700">Kişi / ödeme sayısı
                        <Input type="number" min="2" max="8" value={splitCount} onChange={event => changeSplitCount(event.target.value)} />
                      </label>
                      <label className="text-xs font-medium text-gray-700">Bahşiş
                        <Input type="number" min="0" step="0.01" value={tipAmount} onChange={event => setTipAmount(event.target.value)} />
                      </label>
                    </div>
                    <div className="space-y-2">
                      {Array.from({ length: splitCount }, (_, index) => {
                        const cents = Math.round((total + Number(tipAmount || 0)) * 100);
                        const base = Math.floor(cents / splitCount);
                        const amount = (base + (index === splitCount - 1 ? cents - base * splitCount : 0)) / 100;
                        return <div key={index} className="flex items-center justify-between gap-2 rounded border bg-white px-2 py-1.5 text-sm">
                          <span>{index + 1}. ödeme · <strong>{money(amount)}</strong></span>
                          <select aria-label={`${index + 1}. ödeme yöntemi`} className="h-8 rounded border px-2" value={splitMethods[index] || 'cash'} onChange={event => setSplitMethods(previous => previous.map((method, methodIndex) => methodIndex === index ? event.target.value : method))}>
                            <option value="cash">Nakit</option><option value="card">Kart</option>
                          </select>
                        </div>;
                      })}
                    </div>
                    <Button className="w-full" disabled={loading} onClick={submitSplitPayment} data-testid="submit-split-payment">Bölünmüş Ödemeyi Tamamla</Button>
                  </div>}

                  {/* Room charge */}
                  <div className="border-t pt-3 space-y-2">
                    <div className="flex items-center gap-2 text-sm font-semibold">
                      <BedDouble className="w-4 h-4 text-amber-600" />{t("cm.pages_POSWaiterTerminal.odaya_yaz")}</div>
                    {!roomBooking ? <>
                        <Input value={guestSearch} onChange={e => setGuestSearch(e.target.value)} onFocus={() => {
                  if (inhouse.length === 0) loadInhouse();
                }} placeholder={t("cm.pages_POSWaiterTerminal.misafir_adi_oda_no")} data-testid="room-guest-search" />
                        <div className="max-h-40 overflow-y-auto space-y-1">
                          {filteredInhouse.map(b => <button key={b.id} onClick={() => setRoomBooking(b)} data-testid={`inhouse-${b.id}`} className="w-full text-left p-2 rounded border hover:bg-amber-50 text-sm">
                              <span className="font-medium">
                                {b.guest?.full_name || b.guest_name || 'Misafir'}
                              </span>
                              {(b.room?.room_number || b.room_number) && <span className="text-gray-500">{t("cm.pages_POSWaiterTerminal._oda")}{b.room?.room_number || b.room_number}</span>}
                            </button>)}
                          {loadingInhouse && <div className="text-xs text-gray-500 p-2 flex items-center gap-2"><Loader2 className="w-3.5 h-3.5 animate-spin" /> Konaklayan misafirler yükleniyor…</div>}
                          {!loadingInhouse && inhouse.length === 0 && guestSearch && <div className="text-xs text-gray-500 p-2">Konaklayan misafir bulunamadı.</div>}
                          {inhouse.length > 0 && filteredInhouse.length === 0 && <div className="text-xs text-gray-500 p-2">{t("cm.pages_POSWaiterTerminal.eslesme_yok")}</div>}
                        </div>
                      </> : <div className="flex items-center justify-between p-2 rounded bg-amber-50 text-sm">
                        <span>
                          <span className="font-medium">
                            {roomBooking.guest?.full_name || roomBooking.guest_name || 'Misafir'}
                          </span>
                          {(roomBooking.room?.room_number || roomBooking.room_number) && <span className="text-gray-600">{t("cm.pages_POSWaiterTerminal._oda")}{roomBooking.room?.room_number || roomBooking.room_number}</span>}
                        </span>
                        <Button size="sm" variant="ghost" onClick={() => setRoomBooking(null)}>{t("cm.pages_POSWaiterTerminal.degistir")}</Button>
                      </div>}

                    {roomBooking && <div className="space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-gray-600">{t("cm.pages_POSWaiterTerminal.misafir_imzasi")}</span>
                          <Button size="sm" variant="ghost" onClick={clearSignature} data-testid="signature-clear">
                            <Eraser className="w-3 h-3 mr-1" />{t("cm.pages_POSWaiterTerminal.temizle")}</Button>
                        </div>
                        <canvas ref={canvasRef} width={320} height={120} className="w-full h-28 border rounded bg-white touch-none" data-testid="signature-pad" onMouseDown={startDraw} onMouseMove={moveDraw} onMouseUp={endDraw} onMouseLeave={endDraw} onTouchStart={startDraw} onTouchMove={moveDraw} onTouchEnd={endDraw} />
                        <Button className="w-full" disabled={loading} onClick={() => submitOrder('room_charge')} data-testid="pay-room">
                          <Check className="w-4 h-4 mr-2" />
                          {loading ? 'Gönderiliyor…' : 'Odaya Yaz ve Onayla'}
                        </Button>
                      </div>}
                  </div>
                </CardContent>
              </Card>}

            {/* Last order summary (adisyon no + business date visible) */}
            {lastOrder && <Card className="border-l-4 border-l-green-500 bg-green-50/40" data-testid="last-order">
                <CardContent className="p-3 text-sm space-y-1">
                  <div className="font-semibold flex items-center gap-2 text-green-700">
                    <Check className="w-4 h-4" />{t("cm.pages_POSWaiterTerminal.son_adisyon")}</div>
                  {lastOrder.adisyon_number != null && <div className="flex justify-between">
                      <span>{t("cm.pages_POSWaiterTerminal.adisyon_no")}</span>
                      <span className="font-bold" data-testid="last-adisyon-number">#{lastOrder.adisyon_number}</span>
                    </div>}
                  {lastOrder.business_date && <div className="flex justify-between text-gray-600">
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" />{t("cm.pages_POSWaiterTerminal.is_gunu")}</span>
                      <span data-testid="last-business-date">{lastOrder.business_date}</span>
                    </div>}
                  {lastOrder.total_amount != null && <div className="flex justify-between">
                      <span>{t("cm.pages_POSWaiterTerminal.toplam")}</span>
                      <span>{formatCurrency(lastOrder.total_amount, lastOrder.currency || currency)}</span>
                  </div>}
                  <Button variant="outline" className="w-full mt-2 border-red-200 text-red-700 hover:bg-red-50" disabled={loading || lastOrder.refunded} onClick={refundLastOrder} data-testid="refund-last-order">
                    <RotateCcw className="w-4 h-4 mr-2" />{lastOrder.refunded ? 'İade edildi' : 'Tam iade yap'}
                  </Button>
                </CardContent>
              </Card>}
          </div>
        </div>}
    </div>;
};
export default POSWaiterTerminal;
