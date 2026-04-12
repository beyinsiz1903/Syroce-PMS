import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { ShoppingCart, UtensilsCrossed, Plus, Minus, History, Check } from 'lucide-react';

const POSEnhancements = () => {
  const [activeTab, setActiveTab] = useState('order'); // order, history
  const [menuItems, setMenuItems] = useState([]);
  const [orders, setOrders] = useState([]);
  const [cart, setCart] = useState([]);
  const [bookingId, setBookingId] = useState('');
  const [folioId, setFolioId] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchMenuItems();
  }, [selectedCategory]);

  const fetchMenuItems = async () => {
    try {
      const token = localStorage.getItem('token');
      const url = selectedCategory === 'all'
        ? `/api/pos/menu-items`
        : `/api/pos/menu-items?category=${selectedCategory}`;
      
      const response = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setMenuItems(data.menu_items || []);
      }
    } catch (error) {
      console.error('Error fetching menu items:', error);
    }
  };

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/pos/orders`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setOrders(data.orders || []);
      }
    } catch (error) {
      console.error('Error fetching orders:', error);
    } finally {
      setLoading(false);
    }
  };

  const addToCart = (item) => {
    const existingItem = cart.find(cartItem => cartItem.item_id === item.id);
    
    if (existingItem) {
      setCart(cart.map(cartItem =>
        cartItem.item_id === item.id
          ? { ...cartItem, quantity: cartItem.quantity + 1 }
          : cartItem
      ));
    } else {
      setCart([...cart, {
        item_id: item.id,
        item_name: item.item_name,
        unit_price: item.unit_price,
        category: item.category,
        quantity: 1
      }]);
    }
  };

  const updateQuantity = (itemId, change) => {
    setCart(cart.map(item => {
      if (item.item_id === itemId) {
        const newQuantity = item.quantity + change;
        return newQuantity > 0 ? { ...item, quantity: newQuantity } : null;
      }
      return item;
    }).filter(Boolean));
  };

  const calculateTotal = () => {
    const subtotal = cart.reduce((sum, item) => sum + (item.unit_price * item.quantity), 0);
    const tax = subtotal * 0.18; // 18% VAT
    return { subtotal, tax, total: subtotal + tax };
  };

  const handleCreateOrder = async () => {
    if (cart.length === 0) {
      alert('Cart is empty');
      return;
    }

    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const orderItems = cart.map(item => ({
        item_id: item.item_id,
        quantity: item.quantity
      }));

      const response = await fetch(
        `/api/pos/create-order`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            booking_id: bookingId || null,
            folio_id: folioId || null,
            order_items: orderItems
          })
        }
      );

      if (response.ok) {
        alert('Order created successfully!');
        setCart([]);
        setBookingId('');
        setFolioId('');
      } else {
        alert('Failed to create order');
      }
    } catch (error) {
      console.error('Error creating order:', error);
      alert('Error creating order');
    } finally {
      setLoading(false);
    }
  };

  const getCategoryColor = (category) => {
    const colors = {
      food: 'bg-orange-100 text-orange-800',
      beverage: 'bg-blue-100 text-blue-800',
      alcohol: 'bg-purple-100 text-purple-800',
      dessert: 'bg-pink-100 text-pink-800',
      appetizer: 'bg-green-100 text-green-800'
    };
    return colors[category] || 'bg-gray-100 text-gray-800';
  };

  const { subtotal, tax, total } = calculateTotal();

  return (
    <div className="space-y-4">
      {/* Tab Navigation */}
      <div className="flex gap-2 border-b">
        <Button
          variant={activeTab === 'order' ? 'default' : 'ghost'}
          onClick={() => setActiveTab('order')}
          className="rounded-b-none"
        >
          <ShoppingCart className="w-4 h-4 mr-2" />
          Create Order
        </Button>
        <Button
          variant={activeTab === 'history' ? 'default' : 'ghost'}
          onClick={() => {
            setActiveTab('history');
            fetchOrders();
          }}
          className="rounded-b-none"
        >
          <History className="w-4 h-4 mr-2" />
          Order History
        </Button>
      </div>

      {/* Create Order Tab */}
      {activeTab === 'order' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Menu Items */}
          <div className="lg:col-span-2 space-y-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Menu Items</CardTitle>
                  <Select value={selectedCategory} onValueChange={setSelectedCategory}>
                    <SelectTrigger className="w-[180px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Categories</SelectItem>
                      <SelectItem value="food">Food</SelectItem>
                      <SelectItem value="beverage">Beverage</SelectItem>
                      <SelectItem value="alcohol">Alcohol</SelectItem>
                      <SelectItem value="dessert">Dessert</SelectItem>
                      <SelectItem value="appetizer">Appetizer</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {menuItems.map((item, idx) => (
                    <Card key={idx} className="hover:shadow-md transition-shadow cursor-pointer" onClick={() => addToCart(item)}>
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between">
                          <div className="space-y-1 flex-1">
                            <h3 className="font-semibold">{item.item_name}</h3>
                            <Badge className={getCategoryColor(item.category)}>
                              {item.category}
                            </Badge>
                          </div>
                          <div className="text-lg font-bold text-blue-600">
                            ${item.unit_price}
                          </div>
                        </div>
                        <Button size="sm" className="w-full mt-3">
                          <Plus className="w-4 h-4 mr-2" />
                          Add to Cart
                        </Button>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Cart */}
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ShoppingCart className="w-5 h-5" />
                  Current Order
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <Label>Booking ID (Optional)</Label>
                    <Input
                      value={bookingId}
                      onChange={(e) => setBookingId(e.target.value)}
                      placeholder="Enter booking ID"
                    />
                  </div>
                  <div>
                    <Label>Folio ID (Optional)</Label>
                    <Input
                      value={folioId}
                      onChange={(e) => setFolioId(e.target.value)}
                      placeholder="Enter folio ID to post charges"
                    />
                  </div>

                  <div className="border-t pt-4">
                    {cart.length === 0 ? (
                      <div className="text-center text-gray-500 py-8">
                        <ShoppingCart className="w-12 h-12 mx-auto mb-2 text-gray-400" />
                        Cart is empty
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {cart.map((item, idx) => (
                          <div key={idx} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                            <div className="flex-1">
                              <div className="font-medium text-sm">{item.item_name}</div>
                              <div className="text-xs text-gray-600">${item.unit_price} each</div>
                            </div>
                            <div className="flex items-center gap-2">
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => updateQuantity(item.item_id, -1)}
                              >
                                <Minus className="w-3 h-3" />
                              </Button>
                              <span className="w-8 text-center font-medium">{item.quantity}</span>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => updateQuantity(item.item_id, 1)}
                              >
                                <Plus className="w-3 h-3" />
                              </Button>
                            </div>
                            <div className="ml-2 font-semibold w-16 text-right">
                              ${(item.unit_price * item.quantity).toFixed(2)}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {cart.length > 0 && (
                    <>
                      <div className="border-t pt-4 space-y-2">
                        <div className="flex justify-between text-sm">
                          <span>Subtotal:</span>
                          <span>${subtotal.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between text-sm">
                          <span>Tax (18%):</span>
                          <span>${tax.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between font-bold text-lg border-t pt-2">
                          <span>Total:</span>
                          <span className="text-blue-600">${total.toFixed(2)}</span>
                        </div>
                      </div>

                      <Button
                        onClick={handleCreateOrder}
                        disabled={loading}
                        className="w-full"
                      >
                        <Check className="w-4 h-4 mr-2" />
                        {loading ? 'Creating...' : 'Create Order'}
                      </Button>
                    </>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* Order History Tab */}
      {activeTab === 'history' && (
        <Card>
          <CardHeader>
            <CardTitle>Order History</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="text-center py-8">Loading orders...</div>
            ) : orders.length === 0 ? (
              <div className="text-center text-gray-500 py-8">No orders found</div>
            ) : (
              <div className="space-y-3">
                {orders.map((order, idx) => (
                  <Card key={idx} className={`border-l-4 ${order.folio_id ? 'border-l-green-500 bg-green-50/30' : 'border-l-blue-500'}`}>
                    <CardContent className="p-4">
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-semibold flex items-center gap-2">
                              Order #{order.id?.slice(0, 8)}
                              {order.folio_id && <span className="text-xs text-green-600">📋</span>}
                            </div>
                            <div className="text-sm text-gray-600">
                              {new Date(order.created_at).toLocaleString()}
                            </div>
                          </div>
                          <Badge className={order.status === 'completed' ? 'bg-green-500' : 'bg-yellow-500'}>
                            {order.status}
                          </Badge>
                        </div>

                        <div className="space-y-1">
                          {order.order_items?.map((item, itemIdx) => (
                            <div key={itemIdx} className="flex justify-between text-sm">
                              <span>{item.item_name} x {item.quantity}</span>
                              <span>${item.total_price?.toFixed(2)}</span>
                            </div>
                          ))}
                        </div>

                        <div className="border-t pt-2 flex justify-between font-semibold">
                          <span>Total:</span>
                          <span className="text-blue-600">${order.total_amount?.toFixed(2)}</span>
                        </div>

                        {order.folio_id && (
                          <div className="mt-2">
                            <Badge variant="secondary" className="bg-green-100 text-green-700 text-xs">
                              ✓ Posted to Room Folio
                            </Badge>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default POSEnhancements;
