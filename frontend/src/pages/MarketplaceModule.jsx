import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ShoppingCart, Package, Droplet, Gift, Plus, Minus } from 'lucide-react';

const MarketplaceModule = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [products, setProducts] = useState([]);
  const [orders, setOrders] = useState([]);
  const [cart, setCart] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  // Backend: {products:[{product_name, unit_price, unit_of_measure, status, ...}], count}
  // Frontend render: {name, price, unit, in_stock, ...}
  // Hem array hem obje şekline tolerans + alan adı normalize
  const normalizeProduct = (p) => ({
    ...p,
    id: p.id,
    name: p.name ?? p.product_name ?? '',
    price: p.price ?? p.unit_price ?? 0,
    unit: p.unit ?? p.unit_of_measure ?? '',
    in_stock: p.in_stock ?? (p.status ? p.status === 'active' : true),
    description: p.description ?? '',
    supplier: p.supplier ?? '',
    category: p.category ?? 'equipment',
  });
  const extractProducts = (data) => {
    const raw = Array.isArray(data) ? data : Array.isArray(data?.products) ? data.products : [];
    return raw.map(normalizeProduct);
  };
  const extractOrders = (data) => {
    if (Array.isArray(data)) return data;
    if (Array.isArray(data?.orders)) return data.orders;
    return [];
  };

  const loadData = async () => {
    try {
      const [productsRes, ordersRes] = await Promise.all([
        axios.get('/marketplace/products'),
        axios.get('/marketplace/orders')
      ]);

      const initialProducts = extractProducts(productsRes.data);
      // Ürün yoksa örnek veriyle seed et
      if (initialProducts.length === 0) {
        await seedProducts();
        const newProductsRes = await axios.get('/marketplace/products');
        setProducts(extractProducts(newProductsRes.data));
      } else {
        setProducts(initialProducts);
      }

      setOrders(extractOrders(ordersRes.data));
    } catch (error) {
      console.error('Marketplace load failed', error);
      toast.error('Pazar yeri verileri yüklenemedi');
      setProducts([]);
      setOrders([]);
    } finally {
      setLoading(false);
    }
  };

  const seedProducts = async () => {
    // Backend POST /marketplace/products şeması: product_name, category, unit_price, unit_of_measure, supplier, min_order_qty
    const sampleProducts = [
      { product_name: 'Endüstriyel Süpürge', category: 'equipment', unit_price: 299.99, unit_of_measure: 'adet', supplier: 'CleanPro', min_order_qty: 1 },
      { product_name: 'King Yatak Takımı', category: 'equipment', unit_price: 89.99, unit_of_measure: 'set', supplier: 'ComfortBeds', min_order_qty: 1 },
      { product_name: 'Çok Amaçlı Temizleyici', category: 'cleaning', unit_price: 24.99, unit_of_measure: 'galon', supplier: 'ChemClean', min_order_qty: 1 },
      { product_name: 'Dezenfektan Sprey', category: 'cleaning', unit_price: 15.99, unit_of_measure: 'şişe', supplier: 'SafeGuard', min_order_qty: 1 },
      { product_name: 'Şampuan & Saç Kremi Seti', category: 'amenities', unit_price: 12.99, unit_of_measure: 'set', supplier: 'GuestCare', min_order_qty: 1 },
      { product_name: 'Banyo Havlusu (12li)', category: 'amenities', unit_price: 79.99, unit_of_measure: 'paket', supplier: 'TowelWorld', min_order_qty: 1 },
    ];

    for (const product of sampleProducts) {
      try {
        await axios.post('/marketplace/products', product);
      } catch (error) {
        console.error('Failed to seed product:', error);
      }
    }
  };

  const addToCart = (product) => {
    const existing = cart.find(item => item.product.id === product.id);
    if (existing) {
      setCart(cart.map(item => 
        item.product.id === product.id 
          ? { ...item, quantity: item.quantity + 1 }
          : item
      ));
    } else {
      setCart([...cart, { product, quantity: 1 }]);
    }
    toast.success('Added to cart');
  };

  const updateCartQuantity = (productId, change) => {
    setCart(cart.map(item => {
      if (item.product.id === productId) {
        const newQuantity = item.quantity + change;
        return newQuantity > 0 ? { ...item, quantity: newQuantity } : null;
      }
      return item;
    }).filter(Boolean));
  };

  const removeFromCart = (productId) => {
    setCart(cart.filter(item => item.product.id !== productId));
  };

  const placeOrder = async () => {
    if (cart.length === 0) {
      toast.error('Cart is empty');
      return;
    }

    const totalAmount = cart.reduce((sum, item) => sum + (item.product.price * item.quantity), 0);
    const orderData = {
      items: cart.map(item => ({
        product_id: item.product.id,
        name: item.product.name,
        quantity: item.quantity,
        price: item.product.price,
        total: item.product.price * item.quantity
      })),
      total_amount: totalAmount,
      delivery_address: tenant.address
    };

    try {
      await axios.post('/marketplace/orders', orderData);
      toast.success('Order placed successfully');
      setCart([]);
      loadData();
    } catch (error) {
      toast.error('Sipariş verilemedi');
    }
  };

  const getCategoryIcon = (category) => {
    switch(category) {
      case 'equipment': return Package;
      case 'cleaning': return Droplet;
      case 'amenities': return Gift;
      default: return Package;
    }
  };

  const cartTotal = cart.reduce((sum, item) => sum + (item.product.price * item.quantity), 0);

  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="marketplace">
        <div className="p-6 text-center">{t("common.loading")}</div>
      </Layout>
    );
  }

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="marketplace">
      <div className="p-6 space-y-6">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Space Grotesk' }}>{t('marketplace.title')}</h1>
            <p className="text-gray-600">{t('marketplace.subtitle')}</p>
          </div>
          <div className="flex items-center space-x-4">
            <div className="text-right">
              <div className="text-sm text-gray-600">Cart Total</div>
              <div className="text-2xl font-bold">${cartTotal.toFixed(2)}</div>
            </div>
            <Button onClick={placeOrder} disabled={cart.length === 0} data-testid="place-order-btn">
              <ShoppingCart className="w-4 h-4 mr-2" />
              Place Order ({cart.length})
            </Button>
          </div>
        </div>

        <Tabs defaultValue="products" className="w-full">
          <TabsList>
            <TabsTrigger value="products" data-testid="tab-products">{t('marketplace.products')}</TabsTrigger>
            <TabsTrigger value="cart" data-testid="tab-cart">{t('marketplace.cart')} ({cart.length})</TabsTrigger>
            <TabsTrigger value="orders" data-testid="tab-orders">{t('marketplace.orders')}</TabsTrigger>
          </TabsList>

          <TabsContent value="products" className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {products.map((product) => {
                const Icon = getCategoryIcon(product.category);
                return (
                  <Card key={product.id} data-testid={`product-card-${product.id}`}>
                    <CardHeader>
                      <div className="flex justify-between items-start">
                        <div className="flex-1">
                          <CardTitle className="text-lg">{product.name}</CardTitle>
                          <p className="text-sm text-gray-600 capitalize mt-1">{product.category}</p>
                        </div>
                        <Icon className="w-5 h-5 text-gray-400" />
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <p className="text-sm text-gray-600">{product.description}</p>
                      
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-600">Supplier:</span>
                          <span className="font-medium">{product.supplier}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-600">Unit:</span>
                          <span className="font-medium capitalize">{product.unit}</span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className="text-2xl font-bold text-blue-600">${product.price}</span>
                          <Button 
                            size="sm" 
                            onClick={() => addToCart(product)}
                            disabled={!product.in_stock}
                            data-testid={`add-to-cart-${product.id}`}
                          >
                            {product.in_stock ? t('marketplace.addToCart') : 'Out of Stock'}
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </TabsContent>

          <TabsContent value="cart" className="space-y-4">
            {cart.length === 0 ? (
              <Card>
                <CardContent className="py-12 text-center text-gray-500">
                  <ShoppingCart className="w-16 h-16 mx-auto mb-4 text-gray-300" />
                  <p>Your cart is empty</p>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-4">
                {cart.map((item) => (
                  <Card key={item.product.id} data-testid={`cart-item-${item.product.id}`}>
                    <CardContent className="pt-6">
                      <div className="flex justify-between items-center">
                        <div className="flex-1">
                          <h3 className="font-semibold text-lg">{item.product.name}</h3>
                          <p className="text-sm text-gray-600">${item.product.price} per {item.product.unit}</p>
                        </div>
                        <div className="flex items-center space-x-4">
                          <div className="flex items-center space-x-2">
                            <Button 
                              size="sm" 
                              variant="outline"
                              onClick={() => updateCartQuantity(item.product.id, -1)}
                            >
                              <Minus className="w-4 h-4" />
                            </Button>
                            <span className="w-12 text-center font-medium">{item.quantity}</span>
                            <Button 
                              size="sm" 
                              variant="outline"
                              onClick={() => updateCartQuantity(item.product.id, 1)}
                            >
                              <Plus className="w-4 h-4" />
                            </Button>
                          </div>
                          <div className="text-right w-24">
                            <div className="text-xl font-bold">${(item.product.price * item.quantity).toFixed(2)}</div>
                          </div>
                          <Button 
                            size="sm" 
                            variant="destructive"
                            onClick={() => removeFromCart(item.product.id)}
                          >
                            Remove
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
                
                <Card className="bg-blue-50">
                  <CardContent className="pt-6">
                    <div className="flex justify-between items-center">
                      <div className="text-lg font-semibold">Total</div>
                      <div className="text-3xl font-bold text-blue-600">${cartTotal.toFixed(2)}</div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}
          </TabsContent>

          <TabsContent value="orders" className="space-y-4">
            {orders.length === 0 ? (
              <Card>
                <CardContent className="py-12 text-center text-gray-500">
                  <p>No orders yet</p>
                </CardContent>
              </Card>
            ) : (
              orders.map((order) => (
                <Card key={order.id} data-testid={`order-card-${order.id}`}>
                  <CardContent className="pt-6">
                    <div className="flex justify-between items-start">
                      <div className="flex-1">
                        <div className="font-semibold text-lg mb-2">Order #{order.id.slice(0, 8)}</div>
                        <div className="text-sm text-gray-600 space-y-1">
                          <p>Date: {new Date(order.created_at).toLocaleDateString()}</p>
                          <p>Items: {order.items.length}</p>
                          <p>Delivery: {order.delivery_address}</p>
                          <p className="capitalize">Status: <span className={`font-medium ${
                            order.status === 'delivered' ? 'text-green-600' :
                            order.status === 'shipped' ? 'text-blue-600' :
                            'text-yellow-600'
                          }`}>{order.status}</span></p>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-2xl font-bold text-blue-600">${order.total_amount.toFixed(2)}</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
};

export default MarketplaceModule;
