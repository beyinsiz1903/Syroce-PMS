import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Clock, Zap, LogOut, Save, RefreshCw } from 'lucide-react';

/**
 * POS Auto-Post Settings Component
 * Manages automatic posting schedule for POS charges to folios
 */
const POSAutoPostSettings = () => {
  const [autoPostMode, setAutoPostMode] = useState('realtime'); // realtime, batch, checkout
  const [batchInterval, setBatchInterval] = useState(15); // minutes
  const [loading, setLoading] = useState(false);
  const [lastSync, setLastSync] = useState(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const response = await axios.get('/pos/auto-post-settings');
      setAutoPostMode(response.data.mode || 'realtime');
      setBatchInterval(response.data.batch_interval || 15);
      setLastSync(response.data.last_sync);
    } catch (error) {
      console.error('Failed to load auto-post settings:', error);
    }
  };

  const saveSettings = async () => {
    setLoading(true);
    try {
      await axios.post('/pos/auto-post-settings', {
        mode: autoPostMode,
        batch_interval: batchInterval
      });
      toast.success('Auto-post settings saved!');
    } catch (error) {
      toast.error('Failed to save settings');
    } finally {
      setLoading(false);
    }
  };

  const manualSync = async () => {
    setLoading(true);
    try {
      const response = await axios.post('/pos/manual-sync');
      toast.success(`Synced ${response.data.posted_count} POS charges to folios`);
      setLastSync(new Date().toISOString());
    } catch (error) {
      toast.error('Manual sync failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="w-5 h-5 text-blue-600" />
          POS Auto-Post Zamanlaması
        </CardTitle>
        <CardDescription>
          POS fişlerinin folio'ya otomatik aktarım ayarları
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Mode Selection */}
        <div className="space-y-3">
          <label className="text-sm font-semibold">Aktarım Modu:</label>
          
          {/* Real-time */}
          <div 
            onClick={() => setAutoPostMode('realtime')}
            className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
              autoPostMode === 'realtime' 
                ? 'border-green-500 bg-green-50' 
                : 'border-gray-200 hover:border-green-300'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Zap className={`w-5 h-5 ${autoPostMode === 'realtime' ? 'text-green-600' : 'text-gray-400'}`} />
                <span className="font-semibold">Gerçek Zamanlı</span>
              </div>
              {autoPostMode === 'realtime' && (
                <Badge className="bg-green-500">Aktif</Badge>
              )}
            </div>
            <p className="text-xs text-gray-600">
              POS fişi kapatıldığında anında folio'ya aktarılır. En hızlı yöntem.
            </p>
          </div>

          {/* Batch (15 min) */}
          <div 
            onClick={() => setAutoPostMode('batch')}
            className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
              autoPostMode === 'batch' 
                ? 'border-blue-500 bg-blue-50' 
                : 'border-gray-200 hover:border-blue-300'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Clock className={`w-5 h-5 ${autoPostMode === 'batch' ? 'text-blue-600' : 'text-gray-400'}`} />
                <span className="font-semibold">Toplu Aktarım (Batch)</span>
              </div>
              {autoPostMode === 'batch' && (
                <Badge className="bg-blue-500">Aktif</Badge>
              )}
            </div>
            <p className="text-xs text-gray-600 mb-2">
              Belirli aralıklarla toplu aktarım. Sistem yükünü azaltır.
            </p>
            {autoPostMode === 'batch' && (
              <div className="flex items-center gap-2 mt-2">
                <label className="text-xs">Aralık:</label>
                <select 
                  value={batchInterval}
                  onChange={(e) => setBatchInterval(Number(e.target.value))}
                  className="text-xs border rounded px-2 py-1"
                  onClick={(e) => e.stopPropagation()}
                >
                  <option value={5}>5 dakika</option>
                  <option value={10}>10 dakika</option>
                  <option value={15}>15 dakika</option>
                  <option value={30}>30 dakika</option>
                  <option value={60}>1 saat</option>
                </select>
              </div>
            )}
          </div>

          {/* On Check-out */}
          <div 
            onClick={() => setAutoPostMode('checkout')}
            className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
              autoPostMode === 'checkout' 
                ? 'border-purple-500 bg-purple-50' 
                : 'border-gray-200 hover:border-purple-300'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <LogOut className={`w-5 h-5 ${autoPostMode === 'checkout' ? 'text-purple-600' : 'text-gray-400'}`} />
                <span className="font-semibold">Check-out'ta Toplu</span>
              </div>
              {autoPostMode === 'checkout' && (
                <Badge className="bg-purple-500">Aktif</Badge>
              )}
            </div>
            <p className="text-xs text-gray-600">
              Tüm POS fişleri check-out sırasında tek seferde aktarılır. Misafir kontrol eder.
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-2 pt-4 border-t">
          <Button 
            onClick={saveSettings}
            disabled={loading}
            className="flex-1 bg-blue-600 hover:bg-blue-700"
          >
            <Save className="w-4 h-4 mr-2" />
            Ayarları Kaydet
          </Button>
          <Button 
            onClick={manualSync}
            disabled={loading}
            variant="outline"
            className="flex-1"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Manuel Senkronizasyon
          </Button>
        </div>

        {/* Last Sync Info */}
        {lastSync && (
          <div className="text-xs text-gray-500 text-center pt-2 border-t">
            Son senkronizasyon: {new Date(lastSync).toLocaleString()}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default POSAutoPostSettings;
