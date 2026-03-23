import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Package, TrendingUp, TrendingDown } from 'lucide-react';

const InventoryMovements = () => {
  const [movements, setMovements] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadMovements();
  }, []);

  const loadMovements = async () => {
    try {
      const response = await axios.get('/pos/inventory-movements?limit=20');
      setMovements(response.data.movements || []);
    } catch (error) {
      console.error('Failed to load movements:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="text-center py-4">Yükleniyor...</div>;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center text-lg">
          <Package className="w-5 h-5 mr-2" />
          Stok Hareketleri
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {movements.length === 0 ? (
            <p className="text-center text-gray-500 py-8">Hareket yok</p>
          ) : (
            movements.map((movement) => (
              <div
                key={movement.id}
                className={`p-3 rounded-lg border-l-4 ${
                  movement.movement_type === 'in'
                    ? 'border-green-500 bg-green-50'
                    : 'border-red-500 bg-red-50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2 flex-1">
                    {movement.movement_type === 'in' ? (
                      <TrendingUp className="w-5 h-5 text-green-600" />
                    ) : (
                      <TrendingDown className="w-5 h-5 text-red-600" />
                    )}
                    <div>
                      <div className="font-medium text-sm">{movement.item_name}</div>
                      <div className="text-xs text-gray-500">{movement.notes}</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`font-bold ${
                      movement.movement_type === 'in' ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {movement.movement_type === 'in' ? '+' : '-'}{movement.quantity} {movement.unit}
                    </div>
                    <div className="text-xs text-gray-500">
                      {new Date(movement.created_at).toLocaleDateString('tr-TR')}
                    </div>
                  </div>
                </div>
                {movement.reference && (
                  <div className="mt-2">
                    <Badge variant="outline" className="text-xs">
                      {movement.reference}
                    </Badge>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default InventoryMovements;
