import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import {
  UtensilsCrossed, ArrowLeft, Store, LayoutGrid, ShoppingCart,
  Plus, Minus, Check, CreditCard, Banknote, BedDouble, Eraser, Calendar,
} from 'lucide-react';
import { alertDialog } from '@/lib/dialogs';
import { formatAmount } from '@/lib/currency';

// Touch-first waiter terminal: outlet -> table -> menu/cart -> pay / charge-room.
// Currency is single-currency TRY shown as "tr-TR + ' TL'". Order creation goes
// through the idempotent /api/pos/create-order which also fires the KDS + KOT.

const STEPS = { OUTLET: 'outlet', TABLE: 'table', ORDER: 'order' };

const POSWaiterTerminal = () => {
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
  const [lastOrder, setLastOrder] = useState(null);
  const pendingKeyRef = useRef(null);

  // Signature pad (canvas) — captured for room charges as proof of authorization.
  const canvasRef = useRef(null);
  const drawingRef = useRef(false);
  const hasSignatureRef = useRef(false);

  const loadOutlets = useCallback(async () => {
    try {
      const res = await axios.get('/pos/outlets');
      const list = Array.isArray(res.data) ? res.data : (res.data.outlets || []);
      setOutlets(list.filter(o => o.status !== 'inactive'));
    } catch (err) {
      console.error('Outlets yuklenemedi:', err);
    }
  }, []);

  useEffect(() => { loadOutlets(); }, [loadOutlets]);

  const loadTables = useCallback(async (outletId) => {
    try {
      const res = await axios.get(`/pos/table-layout/${outletId}`);
      setTables(res.data.tables || []);
    } catch (err) {
      console.error('Masalar yuklenemedi:', err);
      setTables([]);
    }
  }, []);

  const loadMenu = useCallback(async (outletId) => {
    try {
      const res = await axios.get('/pos/menu-items', { params: { outlet_id: outletId } });
      const list = Array.isArray(res.data) ? res.data : (res.data.menu_items || []);
      setMenuItems(list);
    } catch (err) {
      console.error('Menu yuklenemedi:', err);
      setMenuItems([]);
    }
  }, []);

  const loadInhouse = useCallback(async () => {
    try {
      const res = await axios.get('/frontdesk/inhouse');
      setInhouse(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      console.error('Konaklayan misafirler yuklenemedi:', err);
      setInhouse([]);
    }
  }, []);

  const pickOutlet = (o) => {
    setOutlet(o);
    setTable(null);
    setCart([]);
    loadTables(o.id);
    loadMenu(o.id);
    setStep(STEPS.TABLE);
  };

  const pickTable = (t) => {
    setTable(t);
    setStep(STEPS.ORDER);
  };

  const addToCart = (item) => {
    setCart(prev => {
      const existing = prev.find(c => c.item_id === item.id);
      if (existing) {
        return prev.map(c => c.item_id === item.id ? { ...c, quantity: c.quantity + 1 } : c);
      }
      return [...prev, {
        item_id: item.id,
        item_name: item.item_name,
        unit_price: item.unit_price,
        category: item.category,
        quantity: 1,
      }];
    });
  };

  const changeQty = (itemId, delta) => {
    setCart(prev => prev.map(c => {
      if (c.item_id !== itemId) return c;
      const q = c.quantity + delta;
      return q > 0 ? { ...c, quantity: q } : null;
    }).filter(Boolean));
  };

  const subtotal = cart.reduce((s, c) => s + c.unit_price * c.quantity, 0);
  const tax = subtotal * 0.18;
  const total = subtotal + tax;

  const categories = ['all', 'food', 'beverage', 'alcohol', 'dessert', 'appetizer'];
  const visibleItems = category === 'all'
    ? menuItems
    : menuItems.filter(m => m.category === category);

  // ── Signature canvas ──────────────────────────────────────────────────
  const canvasPoint = (e) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const touch = e.touches?.[0];
    const clientX = touch ? touch.clientX : e.clientX;
    const clientY = touch ? touch.clientY : e.clientY;
    return {
      x: (clientX - rect.left) * (canvas.width / rect.width),
      y: (clientY - rect.top) * (canvas.height / rect.height),
    };
  };
  const startDraw = (e) => {
    e.preventDefault();
    drawingRef.current = true;
    const ctx = canvasRef.current.getContext('2d');
    const { x, y } = canvasPoint(e);
    ctx.beginPath();
    ctx.moveTo(x, y);
  };
  const moveDraw = (e) => {
    if (!drawingRef.current) return;
    e.preventDefault();
    const ctx = canvasRef.current.getContext('2d');
    const { x, y } = canvasPoint(e);
    ctx.lineTo(x, y);
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#111827';
    ctx.lineCap = 'round';
    ctx.stroke();
    hasSignatureRef.current = true;
  };
  const endDraw = () => { drawingRef.current = false; };
  const clearSignature = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
    hasSignatureRef.current = false;
  };

  const resetForNext = () => {
    setCart([]);
    setRoomBooking(null);
    setGuestSearch('');
    clearSignature();
  };

  const submitOrder = async (paymentMethod) => {
    if (cart.length === 0) {
      alertDialog({ message: 'Sepet bos' });
      return;
    }
    if (paymentMethod === 'room_charge') {
      if (!roomBooking) {
        alertDialog({ message: 'Odaya yazmak icin konaklayan misafir secin' });
        return;
      }
      if (!hasSignatureRef.current) {
        alertDialog({ message: 'Odaya yazmak icin misafir imzasi gerekli' });
        return;
      }
    }

    setLoading(true);
    try {
      if (!pendingKeyRef.current) {
        pendingKeyRef.current = globalThis.crypto?.randomUUID?.()
          || `pos-term-${Date.now()}-${Math.random()}`;
      }
      const signature = paymentMethod === 'room_charge' && hasSignatureRef.current
        ? canvasRef.current.toDataURL('image/png')
        : null;

      const token = localStorage.getItem('token');
      const res = await fetch('/api/pos/create-order', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          outlet_id: outlet?.id || null,
          table_number: table?.table_number != null ? String(table.table_number) : null,
          booking_id: paymentMethod === 'room_charge' ? (roomBooking?.id || null) : null,
          payment_method: paymentMethod,
          guest_signature: signature,
          order_items: cart.map(c => ({ item_id: c.item_id, quantity: c.quantity })),
          idempotency_key: pendingKeyRef.current,
        }),
      });

      if (res.ok) {
        const data = await res.json().catch(() => ({}));
        pendingKeyRef.current = null;
        setLastOrder(data.order || null);
        if (data.idempotent_replay) {
          alertDialog({ message: 'Bu siparis zaten olusturulmustu — cift hesap kesilmedi.' });
        } else {
          alertDialog({ message: 'Siparis olusturuldu, mutfak fisi yazdirildi.' });
        }
        resetForNext();
        if (outlet) loadTables(outlet.id);
      } else {
        const err = await res.json().catch(() => ({}));
        alertDialog({ message: err.detail || 'Siparis olusturulamadi' });
      }
    } catch (err) {
      console.error('Siparis hatasi:', err);
      alertDialog({ message: 'Siparis olusturulurken hata olustu' });
    } finally {
      setLoading(false);
    }
  };

  const statusColor = (s) => ({
    available: 'bg-green-100 text-green-800 border-green-300',
    occupied: 'bg-red-100 text-red-800 border-red-300',
    reserved: 'bg-amber-100 text-amber-800 border-amber-300',
    dirty: 'bg-gray-100 text-gray-700 border-gray-300',
  }[s] || 'bg-gray-100 text-gray-700 border-gray-300');

  const filteredInhouse = inhouse.filter((b) => {
    if (!guestSearch.trim()) return true;
    const q = guestSearch.toLowerCase();
    const name = (b.guest?.full_name || b.guest_name || '').toLowerCase();
    const room = String(b.room?.room_number || '').toLowerCase();
    return name.includes(q) || room.includes(q);
  });

  return (
    <div className="p-4 md:p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold flex items-center gap-3">
            <UtensilsCrossed className="w-7 h-7 text-amber-600" />
            Garson Terminali
          </h1>
          <p className="text-gray-600 mt-1 text-sm">
            {outlet ? outlet.outlet_name || outlet.name : 'Satis noktasi secin'}
            {table ? ` • Masa ${table.table_number}` : ''}
          </p>
        </div>
        <Button variant="outline" onClick={() => navigate('/pos')} data-testid="btn-back-pos">
          <ArrowLeft className="w-4 h-4 mr-2" />
          POS Paneli
        </Button>
      </div>

      {/* Step 1: Outlet */}
      {step === STEPS.OUTLET && (
        <div>
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Store className="w-5 h-5 text-amber-600" /> Satis Noktasi
          </h2>
          {outlets.length === 0 ? (
            <Card><CardContent className="p-8 text-center text-gray-500">
              Aktif satis noktasi yok.
            </CardContent></Card>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {outlets.map(o => (
                <Card key={o.id}
                  className="cursor-pointer hover:shadow-md transition-shadow"
                  onClick={() => pickOutlet(o)}
                  data-testid={`outlet-${o.id}`}>
                  <CardContent className="p-5 text-center">
                    <Store className="w-8 h-8 mx-auto mb-2 text-amber-600" />
                    <div className="font-semibold">{o.outlet_name || o.name}</div>
                    {o.outlet_type && (
                      <Badge variant="outline" className="mt-2">{o.outlet_type}</Badge>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Step 2: Table */}
      {step === STEPS.TABLE && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <LayoutGrid className="w-5 h-5 text-amber-600" /> Masa Sec
            </h2>
            <Button variant="ghost" size="sm" onClick={() => setStep(STEPS.OUTLET)}>
              <ArrowLeft className="w-4 h-4 mr-1" /> Satis noktasi
            </Button>
          </div>
          {tables.length === 0 ? (
            <Card><CardContent className="p-8 text-center text-gray-500">
              Bu satis noktasinda masa bulunamadi.
            </CardContent></Card>
          ) : (
            <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
              {tables.map(t => (
                <button key={t.id}
                  onClick={() => pickTable(t)}
                  data-testid={`table-${t.table_number}`}
                  className={`rounded-lg border-2 p-4 text-center transition-shadow hover:shadow-md ${statusColor(t.status)}`}>
                  <div className="text-xl font-bold">{t.table_number}</div>
                  <div className="text-xs mt-1">{t.seats} kisi</div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Step 3: Menu + Cart */}
      {step === STEPS.ORDER && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Menu */}
          <div className="lg:col-span-2 space-y-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <Button variant="ghost" size="sm" onClick={() => setStep(STEPS.TABLE)}>
                <ArrowLeft className="w-4 h-4 mr-1" /> Masalar
              </Button>
              <div className="flex gap-1 flex-wrap">
                {categories.map(c => (
                  <Button key={c} size="sm"
                    variant={category === c ? 'default' : 'outline'}
                    onClick={() => setCategory(c)}>
                    {c === 'all' ? 'Tumu' : c}
                  </Button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {visibleItems.map(item => (
                <Card key={item.id}
                  className="cursor-pointer hover:shadow-md transition-shadow"
                  onClick={() => addToCart(item)}
                  data-testid={`menu-item-${item.id}`}>
                  <CardContent className="p-3">
                    <div className="font-semibold text-sm leading-tight">{item.item_name}</div>
                    <Badge variant="outline" className="mt-1 text-xs">{item.category}</Badge>
                    <div className="mt-2 font-bold text-amber-700">
                      {formatAmount(item.unit_price)} TL
                    </div>
                  </CardContent>
                </Card>
              ))}
              {visibleItems.length === 0 && (
                <div className="col-span-full text-center text-gray-500 py-8">
                  Bu kategoride urun yok.
                </div>
              )}
            </div>
          </div>

          {/* Cart */}
          <div className="space-y-3">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <ShoppingCart className="w-5 h-5" /> Adisyon
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {cart.length === 0 ? (
                  <div className="text-center text-gray-500 py-6 text-sm">
                    Urun eklemek icin menuden secin.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {cart.map(c => (
                      <div key={c.item_id}
                        className="flex items-center justify-between gap-2 p-2 bg-gray-50 rounded">
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-sm truncate">{c.item_name}</div>
                          <div className="text-xs text-gray-600">
                            {formatAmount(c.unit_price)} TL / adet
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          <Button size="sm" variant="outline"
                            onClick={() => changeQty(c.item_id, -1)}
                            data-testid={`cart-minus-${c.item_id}`}>
                            <Minus className="w-3 h-3" />
                          </Button>
                          <span className="w-7 text-center font-medium">{c.quantity}</span>
                          <Button size="sm" variant="outline"
                            onClick={() => changeQty(c.item_id, 1)}
                            data-testid={`cart-plus-${c.item_id}`}>
                            <Plus className="w-3 h-3" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {cart.length > 0 && (
                  <div className="border-t pt-3 space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span>Ara Toplam</span><span>{formatAmount(subtotal)} TL</span>
                    </div>
                    <div className="flex justify-between">
                      <span>KDV (%18)</span><span>{formatAmount(tax)} TL</span>
                    </div>
                    <div className="flex justify-between font-bold text-base border-t pt-1">
                      <span>Toplam</span>
                      <span className="text-amber-700">{formatAmount(total)} TL</span>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Payment actions */}
            {cart.length > 0 && (
              <Card>
                <CardContent className="p-3 space-y-3">
                  <div className="grid grid-cols-2 gap-2">
                    <Button variant="outline" disabled={loading}
                      onClick={() => submitOrder('cash')} data-testid="pay-cash">
                      <Banknote className="w-4 h-4 mr-2" /> Nakit
                    </Button>
                    <Button variant="outline" disabled={loading}
                      onClick={() => submitOrder('card')} data-testid="pay-card">
                      <CreditCard className="w-4 h-4 mr-2" /> Kart
                    </Button>
                  </div>

                  {/* Room charge */}
                  <div className="border-t pt-3 space-y-2">
                    <div className="flex items-center gap-2 text-sm font-semibold">
                      <BedDouble className="w-4 h-4 text-amber-600" /> Odaya Yaz
                    </div>
                    {!roomBooking ? (
                      <>
                        <Input
                          value={guestSearch}
                          onChange={(e) => setGuestSearch(e.target.value)}
                          onFocus={() => { if (inhouse.length === 0) loadInhouse(); }}
                          placeholder="Misafir adi / oda no"
                          data-testid="room-guest-search"
                        />
                        <div className="max-h-40 overflow-y-auto space-y-1">
                          {filteredInhouse.map(b => (
                            <button key={b.id}
                              onClick={() => setRoomBooking(b)}
                              data-testid={`inhouse-${b.id}`}
                              className="w-full text-left p-2 rounded border hover:bg-amber-50 text-sm">
                              <span className="font-medium">
                                {b.guest?.full_name || b.guest_name || 'Misafir'}
                              </span>
                              {b.room?.room_number && (
                                <span className="text-gray-500"> • Oda {b.room.room_number}</span>
                              )}
                            </button>
                          ))}
                          {inhouse.length > 0 && filteredInhouse.length === 0 && (
                            <div className="text-xs text-gray-500 p-2">Eslesme yok.</div>
                          )}
                        </div>
                      </>
                    ) : (
                      <div className="flex items-center justify-between p-2 rounded bg-amber-50 text-sm">
                        <span>
                          <span className="font-medium">
                            {roomBooking.guest?.full_name || roomBooking.guest_name || 'Misafir'}
                          </span>
                          {roomBooking.room?.room_number && (
                            <span className="text-gray-600"> • Oda {roomBooking.room.room_number}</span>
                          )}
                        </span>
                        <Button size="sm" variant="ghost"
                          onClick={() => setRoomBooking(null)}>Degistir</Button>
                      </div>
                    )}

                    {roomBooking && (
                      <div className="space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-gray-600">Misafir imzasi</span>
                          <Button size="sm" variant="ghost" onClick={clearSignature}
                            data-testid="signature-clear">
                            <Eraser className="w-3 h-3 mr-1" /> Temizle
                          </Button>
                        </div>
                        <canvas
                          ref={canvasRef}
                          width={320}
                          height={120}
                          className="w-full h-28 border rounded bg-white touch-none"
                          data-testid="signature-pad"
                          onMouseDown={startDraw}
                          onMouseMove={moveDraw}
                          onMouseUp={endDraw}
                          onMouseLeave={endDraw}
                          onTouchStart={startDraw}
                          onTouchMove={moveDraw}
                          onTouchEnd={endDraw}
                        />
                        <Button className="w-full" disabled={loading}
                          onClick={() => submitOrder('room_charge')}
                          data-testid="pay-room">
                          <Check className="w-4 h-4 mr-2" />
                          {loading ? 'Gonderiliyor...' : 'Odaya Yaz ve Onayla'}
                        </Button>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Last order summary (adisyon no + business date visible) */}
            {lastOrder && (
              <Card className="border-l-4 border-l-green-500 bg-green-50/40" data-testid="last-order">
                <CardContent className="p-3 text-sm space-y-1">
                  <div className="font-semibold flex items-center gap-2 text-green-700">
                    <Check className="w-4 h-4" /> Son Adisyon
                  </div>
                  {lastOrder.adisyon_number != null && (
                    <div className="flex justify-between">
                      <span>Adisyon No</span>
                      <span className="font-bold" data-testid="last-adisyon-number">#{lastOrder.adisyon_number}</span>
                    </div>
                  )}
                  {lastOrder.business_date && (
                    <div className="flex justify-between text-gray-600">
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" /> Is Gunu
                      </span>
                      <span data-testid="last-business-date">{lastOrder.business_date}</span>
                    </div>
                  )}
                  {lastOrder.total_amount != null && (
                    <div className="flex justify-between">
                      <span>Toplam</span>
                      <span>{formatAmount(lastOrder.total_amount)} TL</span>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default POSWaiterTerminal;
