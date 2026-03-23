import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Users, RefreshCw, CheckCircle, Clock, XCircle } from 'lucide-react';

const POSTableManagement = ({ outletId = 'main_restaurant' }) => {
  const [tables, setTables] = useState([]);
  const [statusCounts, setStatusCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(null);

  useEffect(() => {
    loadTables();
  }, [outletId]);

  const loadTables = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`/pos/tables?outlet_id=${outletId}`);
      setTables(response.data.tables || []);
      setStatusCounts(response.data.status_counts || {});
    } catch (error) {
      console.error('Failed to load tables:', error);
      toast.error('Failed to load tables');
    } finally {
      setLoading(false);
    }
  };

  const updateTableStatus = async (tableId, newStatus) => {
    try {
      setUpdating(tableId);
      await axios.put(`/pos/tables/${tableId}/status?new_status=${newStatus}`);
      toast.success('Table status updated');
      loadTables();
    } catch (error) {
      toast.error('Failed to update table status');
    } finally {
      setUpdating(null);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'available':
        return 'bg-green-100 text-green-700 border-green-300';
      case 'occupied':
        return 'bg-red-100 text-red-700 border-red-300';
      case 'reserved':
        return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      default:
        return 'bg-gray-100 text-gray-700 border-gray-300';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'available':
        return <CheckCircle className="w-4 h-4" />;
      case 'occupied':
        return <Users className="w-4 h-4" />;
      case 'reserved':
        return <Clock className="w-4 h-4" />;
      default:
        return null;
    }
  };

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
            <Users className="w-5 h-5 mr-2 text-blue-600" />
            Restaurant Tables ({tables.length})
          </CardTitle>
          <Button variant="outline" size="sm" onClick={loadTables}>
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {/* Status Summary */}
        <div className="grid grid-cols-3 gap-3 mb-6">
          <div className="text-center p-3 bg-green-50 rounded-lg border border-green-200">
            <p className="text-2xl font-bold text-green-700">{statusCounts.available || 0}</p>
            <p className="text-xs text-green-600">Available</p>
          </div>
          <div className="text-center p-3 bg-red-50 rounded-lg border border-red-200">
            <p className="text-2xl font-bold text-red-700">{statusCounts.occupied || 0}</p>
            <p className="text-xs text-red-600">Occupied</p>
          </div>
          <div className="text-center p-3 bg-yellow-50 rounded-lg border border-yellow-200">
            <p className="text-2xl font-bold text-yellow-700">{statusCounts.reserved || 0}</p>
            <p className="text-xs text-yellow-600">Reserved</p>
          </div>
        </div>

        {/* Tables Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
          {tables.map((table) => (
            <Card
              key={table.id}
              className={`cursor-pointer hover:shadow-lg transition-all ${
                updating === table.id ? 'opacity-50' : ''
              }`}
            >
              <CardContent className="p-4">
                <div className="text-center">
                  <p className="text-2xl font-bold text-gray-900 mb-2">
                    {table.table_number}
                  </p>
                  <Badge className={`${getStatusColor(table.status)} flex items-center justify-center gap-1 mb-2`}>
                    {getStatusIcon(table.status)}
                    {table.status}
                  </Badge>
                  <p className="text-xs text-gray-600 mb-3">
                    <Users className="w-3 h-3 inline mr-1" />
                    {table.capacity} seats
                  </p>

                  {/* Quick Actions */}
                  <div className="space-y-1">
                    {table.status !== 'available' && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="w-full text-xs"
                        onClick={() => updateTableStatus(table.id, 'available')}
                        disabled={updating === table.id}
                      >
                        <CheckCircle className="w-3 h-3 mr-1" />
                        Free
                      </Button>
                    )}
                    {table.status === 'available' && (
                      <>
                        <Button
                          size="sm"
                          className="w-full text-xs bg-red-600 hover:bg-red-700"
                          onClick={() => updateTableStatus(table.id, 'occupied')}
                          disabled={updating === table.id}
                        >
                          <Users className="w-3 h-3 mr-1" />
                          Occupy
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="w-full text-xs"
                          onClick={() => updateTableStatus(table.id, 'reserved')}
                          disabled={updating === table.id}
                        >
                          <Clock className="w-3 h-3 mr-1" />
                          Reserve
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {tables.length === 0 && (
          <div className="text-center py-8 text-gray-500">
            No tables available
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default POSTableManagement;
