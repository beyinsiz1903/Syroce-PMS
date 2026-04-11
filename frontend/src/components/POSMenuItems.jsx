import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { UtensilsCrossed, RefreshCw, Search } from 'lucide-react';
import { Input } from './ui/input';

const POSMenuItems = ({ outletId = 'main_restaurant', onItemSelect }) => {
  const [menuItems, setMenuItems] = useState([]);
  const [byCategory, setByCategory] = useState({});
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');

  useEffect(() => {
    loadMenu();
  }, [outletId]);

  const loadMenu = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`/pos/menu?outlet_id=${outletId}`);
      setMenuItems(response.data.items || []);
      setByCategory(response.data.by_category || {});
    } catch (error) {
      console.error('Failed to load menu:', error);
      toast.error('Failed to load menu');
    } finally {
      setLoading(false);
    }
  };

  const filteredItems = menuItems.filter(item => {
    const matchesSearch = item.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = selectedCategory === 'all' || item.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const categories = ['all', ...Object.keys(byCategory)];

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-600 mx-auto" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center">
            <UtensilsCrossed className="w-5 h-5 mr-2 text-orange-600" />
            Menu Items ({filteredItems.length})
          </CardTitle>
          <Button variant="outline" size="sm" onClick={loadMenu}>
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {/* Search */}
        <div className="mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              placeholder="Search menu items..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
        </div>

        {/* Category Filter */}
        <div className="flex flex-wrap gap-2 mb-4">
          {categories.map((cat) => (
            <Badge
              key={cat}
              variant={selectedCategory === cat ? 'default' : 'outline'}
              className="cursor-pointer"
              onClick={() => setSelectedCategory(cat)}
            >
              {cat === 'all' ? 'All' : cat} ({cat === 'all' ? menuItems.length : byCategory[cat]?.length || 0})
            </Badge>
          ))}
        </div>

        {/* Menu Items Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredItems.map((item) => (
            <Card
              key={item.id}
              className={`cursor-pointer hover:shadow-lg transition ${
                !item.available ? 'opacity-50' : ''
              }`}
              onClick={() => onItemSelect && onItemSelect(item)}
            >
              <CardContent className="p-4">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex-1">
                    <h3 className="font-bold text-gray-900">{item.name}</h3>
                    <Badge variant="outline" className="mt-1">
                      {item.category}
                    </Badge>
                  </div>
                  {!item.available && (
                    <Badge variant="destructive" className="ml-2">
                      Out of Stock
                    </Badge>
                  )}
                </div>
                <div className="flex items-center justify-between mt-3">
                  <div>
                    <p className="text-2xl font-bold text-green-600">
                      ${item.price.toFixed(2)}
                    </p>
                    <p className="text-xs text-gray-500">
                      Cost: ${item.cost.toFixed(2)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-medium text-gray-600">
                      Margin
                    </p>
                    <p className="text-lg font-bold text-blue-600">
                      {((item.price - item.cost) / item.price * 100).toFixed(0)}%
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {filteredItems.length === 0 && (
          <div className="text-center py-8 text-gray-500">
            No menu items found
          </div>
        )}

        {/* Summary */}
        <div className="mt-6 p-4 bg-gray-50 rounded-lg">
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <p className="text-sm text-gray-600">Total Items</p>
              <p className="text-xl font-bold">{menuItems.length}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600">Available</p>
              <p className="text-xl font-bold text-green-600">
                {menuItems.filter(i => i.available).length}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-600">Categories</p>
              <p className="text-xl font-bold text-blue-600">
                {Object.keys(byCategory).length}
              </p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default POSMenuItems;
