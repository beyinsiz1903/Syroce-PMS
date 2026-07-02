import { useTranslation } from 'react-i18next';
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { ArrowLeft, Wrench, AlertTriangle, CheckCircle, Clock, TrendingUp, RefreshCw, Settings, History, FileText, BarChart3, Eye, Calendar, Package, ShoppingCart, Camera, Upload, Filter, X, Plus, Minus, QrCode, Activity, Home, Snowflake, Zap, Droplet, Hammer, Sofa } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export default function MobileMaintenancePartsUsageModal({ partsUsageModalOpen, setPartsUsageModalOpen, partsInventory, setSelectedPart, selectedPart, setUsageQuantity, usageQuantity, parseInt, handlePartUsage }) {
    const { t } = useTranslation();
    return (
        <Dialog open={partsUsageModalOpen} onOpenChange={setPartsUsageModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Parça Kullanımı</DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            <div>
              <Label>Parça Seçin</Label>
              <select className="w-full p-2 border rounded mt-1" onChange={e => {
          const part = partsInventory.find(p => p.id === e.target.value);
          setSelectedPart(part);
        }}>
                <option value="">Seçin...</option>
                {partsInventory.filter(p => p.current_stock > 0).map(part => <option key={part.id} value={part.id}>
                    {part.part_name} - Stok: {part.current_stock}
                  </option>)}
              </select>
            </div>
            
            {selectedPart && <>
                <Card className="bg-blue-50">
                  <CardContent className="p-3 text-sm">
                    <p><strong>Parça:</strong> {selectedPart.part_name}</p>
                    <p><strong>Kategori:</strong> {selectedPart.category}</p>
                    <p><strong>Mevcut Stok:</strong> {selectedPart.current_stock}</p>
                    <p><strong>Birim Fiyat:</strong> {selectedPart.unit_price} ₺</p>
                    <p><strong>Depo:</strong> {selectedPart.warehouse_location}</p>
                  </CardContent>
                </Card>
                
                <div>
                  <Label>Miktar</Label>
                  <div className="flex items-center space-x-2 mt-1">
                    <Button size="sm" variant="outline" onClick={() => setUsageQuantity(Math.max(1, usageQuantity - 1))}>
                      <Minus className="w-4 h-4" />
                    </Button>
                    <Input type="number" value={usageQuantity} onChange={e => setUsageQuantity(parseInt(e.target.value) || 1)} min="1" max={selectedPart.current_stock} className="text-center" />
                    <Button size="sm" variant="outline" onClick={() => setUsageQuantity(Math.min(selectedPart.current_stock, usageQuantity + 1))}>
                      <Plus className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
                
                <div className="p-3 bg-gray-100 rounded">
                  <p className="text-sm">
                    <strong>Toplam Maliyet:</strong> {(selectedPart.unit_price * usageQuantity).toFixed(2)} ₺
                  </p>
                </div>
              </>}
            
            <Button className="w-full" onClick={handlePartUsage} disabled={!selectedPart || usageQuantity < 1}>
              Parça Kullan
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    );
}
