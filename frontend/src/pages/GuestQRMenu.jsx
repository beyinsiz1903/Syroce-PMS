import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { toast, Toaster } from 'react-hot-toast';
import { ShoppingCart, Plus, Minus, Send, UtensilsCrossed } from 'lucide-react';

const GuestQRMenu = () => {
  const { tenantId, outletId } = useParams();
  const [categories, setCategories] = useState([]);
  const [cart, setCart] = useState({});
  const [tableId, setTableId] = useState('T1'); // For demo, usually from URL query
  const [guestName, setGuestName] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // URL params like ?table=12
    const params = new URLSearchParams(window.location.search);
    if (params.get('table')) {
      setTableId(params.get('table'));
    }

    const fetchMenu = async () => {
      try {
        const response = await axios.get(`/api/public/fnb/${tenantId}/${outletId}/menu`);
        setCategories(response.data.categories || []);
      } catch (error) {
        toast.error("Menü yüklenirken bir hata oluştu.");
      } finally {
        setLoading(false);
      }
    };
    fetchMenu();
  }, [tenantId, outletId]);

  const updateCart = (item, delta) => {
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

  const totalAmount = Object.values(cart).reduce((sum, item) => sum + (item.unit_price * item.qty), 0);

  const placeOrder = async () => {
    if (Object.keys(cart).length === 0) return;
    
    try {
      const items = Object.values(cart).map(it => ({
        item_id: it.id,
        quantity: it.qty
      }));
      
      await axios.post(`/api/public/fnb/${tenantId}/${outletId}/order`, {
        table_id: tableId,
        guest_name: guestName,
        items
      });
      
      toast.success("Siparişiniz başarıyla mutfağa iletildi!");
      setCart({});
    } catch (error) {
      toast.error("Sipariş iletilemedi. Lütfen tekrar deneyin.");
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-screen bg-gray-50"><div className="animate-spin text-blue-500"><UtensilsCrossed size={48} /></div></div>;
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-32">
      <Toaster position="top-center" />
      
      {/* Header */}
      <div className="bg-white p-4 shadow-sm sticky top-0 z-10">
        <h1 className="text-xl font-bold text-center text-gray-800">Dijital Menü</h1>
        <div className="text-center text-sm text-gray-500">Masa: {tableId}</div>
      </div>

      {/* Menu Categories */}
      <div className="max-w-3xl mx-auto p-4 space-y-8">
        {categories.map(cat => (
          <div key={cat.name}>
            <h2 className="text-lg font-bold text-gray-800 border-b pb-2 mb-4">{cat.name}</h2>
            <div className="space-y-4">
              {cat.items.map(item => (
                <div key={item.id} className="bg-white p-4 rounded-xl shadow-sm flex justify-between items-center">
                  <div>
                    <h3 className="font-semibold text-gray-800">{item.item_name}</h3>
                    <p className="text-blue-600 font-bold mt-1">{item.unit_price.toFixed(2)} ₺</p>
                  </div>
                  
                  <div className="flex items-center space-x-3 bg-gray-100 rounded-full p-1">
                    <button 
                      onClick={() => updateCart(item, -1)}
                      className="w-8 h-8 flex items-center justify-center bg-white rounded-full shadow-sm text-gray-600 hover:text-red-500"
                    >
                      <Minus size={16} />
                    </button>
                    <span className="w-4 text-center font-semibold">{cart[item.id]?.qty || 0}</span>
                    <button 
                      onClick={() => updateCart(item, 1)}
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
              <div className="text-xl font-bold text-gray-800">{totalAmount.toFixed(2)} ₺</div>
            </div>
            
            <button 
              onClick={placeOrder}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-xl font-semibold flex items-center space-x-2"
            >
              <span>Siparişi Ver</span>
              <Send size={18} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default GuestQRMenu;
