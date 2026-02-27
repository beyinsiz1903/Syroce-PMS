import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Package, ShoppingCart, Truck, AlertCircle, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const MarketplaceInventory = () => {
  const { t } = useTranslation();
  const [inventory, setInventory] = useState([]);
  const [purchaseOrders, setPurchaseOrders] = useState([]);
  const [deliveries, setDeliveries] = useState([]);
  const [showDialog, setShowDialog] = useState(false);
  const [dialogType, setDialogType] = useState('product'); // 'product', 'order', 'delivery'
  const [formData, setFormData] = useState({
    product_name: '',
    category: 'food',
    sku: '',
    current_stock: 0,
    min_stock: 0,
    max_stock: 0,
    unit_price: 0,
    supplier: '',
    unit: 'units'
  });

  useEffect(() => {
    loadInventory();
    loadPurchaseOrders();
    loadDeliveries();
  }, []);

  const loadInventory = async () => {
    try {
      const response = await axios.get('/marketplace/inventory');
      setInventory(response.data.products || []);
    } catch (error) {
      console.error('Failed to load inventory:', error);
    }
  };

  const loadPurchaseOrders = async () => {
    try {
      const response = await axios.get('/marketplace/purchase-orders');
      setPurchaseOrders(response.data.orders || []);
    } catch (error) {
      console.error('Failed to load orders:', error);
    }
  };

  const loadDeliveries = async () => {
    try {
      const response = await axios.get('/marketplace/deliveries');
      setDeliveries(response.data.deliveries || []);
    } catch (error) {
      console.error('Failed to load deliveries:', error);
    }
  };

  const handleCreateProduct = async () => {
    try {
      await axios.post('/marketplace/inventory', formData);
      toast.success('Product added to inventory');
      setShowDialog(false);
      loadInventory();
    } catch (error) {
      toast.error('Failed to add product');
    }
  };

  const handleCreatePurchaseOrder = async (product) => {
    try {
      const quantity = prompt(`Enter quantity to order for ${product.product_name}:`);
      if (!quantity) return;

      await axios.post('/marketplace/purchase-orders', {
        product_id: product.id,
        quantity: parseInt(quantity),
        unit_price: product.unit_price,
        supplier: product.supplier
      });

      toast.success('Purchase order created');
      loadPurchaseOrders();
    } catch (error) {
      toast.error('Failed to create order');
    }
  };

  const getStockStatus = (product) => {
    if (product.current_stock <= product.min_stock) {
      return { color: 'bg-red-100 text-red-700', label: 'Low Stock', icon: <AlertCircle className="w-4 h-4" /> };
    } else if (product.current_stock >= product.max_stock) {
      return { color: 'bg-orange-100 text-orange-700', label: 'Overstock', icon: <AlertCircle className="w-4 h-4" /> };
    }
    return { color: 'bg-green-100 text-green-700', label: 'In Stock', icon: null };
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">Marketplace Inventory</h1>
          <p className="text-gray-600">Stock management & procurement</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => {
            setDialogType('product');
            setShowDialog(true);
          }}>
            <Plus className="w-4 h-4 mr-2" />
            Add Product
          </Button>
        </div>
      </div>

      {/* Inventory Table */}
      <Card>
        <CardHeader>
          <CardTitle>Current Inventory</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-2">Product</th>
                  <th className="text-left p-2">SKU</th>
                  <th className="text-left p-2">Category</th>
                  <th className="text-right p-2">Current Stock</th>
                  <th className="text-right p-2">Min/Max</th>
                  <th className="text-left p-2">Status</th>
                  <th className="text-right p-2">Unit Price</th>
                  <th className="text-left p-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {inventory.map((product) => {
                  const status = getStockStatus(product);
                  return (
                    <tr key={product.id} className="border-b hover:bg-gray-50">
                      <td className="p-2 font-semibold">{product.product_name}</td>
                      <td className="p-2 text-gray-600">{product.sku}</td>
                      <td className="p-2 capitalize">{product.category}</td>
                      <td className="p-2 text-right font-semibold">{product.current_stock} {product.unit}</td>
                      <td className="p-2 text-right text-sm text-gray-600">
                        {product.min_stock}/{product.max_stock}
                      </td>
                      <td className="p-2">
                        <Badge className={status.color}>
                          {status.icon}
                          {status.label}
                        </Badge>
                      </td>
                      <td className="p-2 text-right">${product.unit_price}</td>
                      <td className="p-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleCreatePurchaseOrder(product)}
                        >
                          <ShoppingCart className="w-4 h-4 mr-1" />
                          Order
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Purchase Orders */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShoppingCart className="w-5 h-5" />
              Purchase Orders
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {purchaseOrders.slice(0, 5).map((order) => (
                <div key={order.id} className="flex justify-between items-center p-3 bg-gray-50 rounded">
                  <div>
                    <div className="font-semibold">{order.product_name}</div>
                    <div className="text-sm text-gray-600">
                      Qty: {order.quantity} - ${order.total_amount}
                    </div>
                  </div>
                  <Badge className={{
                    pending: 'bg-yellow-100 text-yellow-700',
                    approved: 'bg-blue-100 text-blue-700',
                    delivered: 'bg-green-100 text-green-700'
                  }[order.status]}>
                    {order.status}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Recent Deliveries */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Truck className="w-5 h-5" />
              Recent Deliveries
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {deliveries.slice(0, 5).map((delivery) => (
                <div key={delivery.id} className="flex justify-between items-center p-3 bg-gray-50 rounded">
                  <div>
                    <div className="font-semibold">{delivery.product_name}</div>
                    <div className="text-sm text-gray-600">
                      {new Date(delivery.delivered_at).toLocaleDateString()}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold">{delivery.quantity_delivered} units</div>
                    <div className="text-xs text-gray-600">{delivery.received_by}</div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Add Product Dialog */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Add Product to Inventory</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Product Name</Label>
                <Input
                  value={formData.product_name}
                  onChange={(e) => setFormData({ ...formData, product_name: e.target.value })}
                  placeholder="Shampoo"
                />
              </div>
              <div>
                <Label>SKU</Label>
                <Input
                  value={formData.sku}
                  onChange={(e) => setFormData({ ...formData, sku: e.target.value })}
                  placeholder="SHP-001"
                />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <Label>Category</Label>
                <select
                  className="w-full border rounded-md p-2"
                  value={formData.category}
                  onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                >
                  <option value="food">Food & Beverage</option>
                  <option value="amenities">Amenities</option>
                  <option value="cleaning">Cleaning Supplies</option>
                  <option value="linens">Linens</option>
                  <option value="maintenance">Maintenance</option>
                </select>
              </div>
              <div>
                <Label>Unit</Label>
                <select
                  className="w-full border rounded-md p-2"
                  value={formData.unit}
                  onChange={(e) => setFormData({ ...formData, unit: e.target.value })}
                >
                  <option value="units">Units</option>
                  <option value="kg">Kilograms</option>
                  <option value="liters">Liters</option>
                  <option value="boxes">Boxes</option>
                </select>
              </div>
              <div>
                <Label>Unit Price ($)</Label>
                <Input
                  type="number"
                  value={formData.unit_price}
                  onChange={(e) => setFormData({ ...formData, unit_price: parseFloat(e.target.value) })}
                />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <Label>Current Stock</Label>
                <Input
                  type="number"
                  value={formData.current_stock}
                  onChange={(e) => setFormData({ ...formData, current_stock: parseInt(e.target.value) })}
                />
              </div>
              <div>
                <Label>Min Stock</Label>
                <Input
                  type="number"
                  value={formData.min_stock}
                  onChange={(e) => setFormData({ ...formData, min_stock: parseInt(e.target.value) })}
                />
              </div>
              <div>
                <Label>Max Stock</Label>
                <Input
                  type="number"
                  value={formData.max_stock}
                  onChange={(e) => setFormData({ ...formData, max_stock: parseInt(e.target.value) })}
                />
              </div>
            </div>

            <div>
              <Label>Supplier</Label>
              <Input
                value={formData.supplier}
                onChange={(e) => setFormData({ ...formData, supplier: e.target.value })}
                placeholder="Supplier name"
              />
            </div>

            <Button onClick={handleCreateProduct} className="w-full">
              Add to Inventory
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MarketplaceInventory;