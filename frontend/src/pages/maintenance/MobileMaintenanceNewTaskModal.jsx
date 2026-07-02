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

export default function MobileMaintenanceNewTaskModal({ newTaskModalOpen, setNewTaskModalOpen, handleCreateTask, FormData, allRooms }) {
    const { t } = useTranslation();
    return (
        <Dialog open={newTaskModalOpen} onOpenChange={setNewTaskModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Yeni Bakım Görevi Oluştur</DialogTitle>
          </DialogHeader>
          <form onSubmit={e => {
      e.preventDefault();
      handleCreateTask(new FormData(e.target));
    }}>
            <div className="space-y-4">
              <div>
                <Label>Oda Seçin *</Label>
                <select name="room_id" className="w-full p-2 border rounded mt-1" required>
                  <option value="">Seçin...</option>
                  {allRooms.map(room => <option key={room.id} value={room.id}>
                      Oda {room.room_number} - {room.room_type}
                    </option>)}
                </select>
              </div>

              <div>
                <Label>Arıza Tipi *</Label>
                <select name="issue_type" className="w-full p-2 border rounded mt-1" required>
                  <option value="">Seçin...</option>
                  <option value="electrical">Elektrik</option>
                  <option value="plumbing">Tesisat</option>
                  <option value="hvac">HVAC / Klima</option>
                  <option value="furniture">Mobilya</option>
                  <option value="appliance">Cihaz</option>
                  <option value="structural">Yapısal</option>
                  <option value="other">Diğer</option>
                </select>
              </div>

              <div>
                <Label>Açıklama *</Label>
                <Textarea name="description" rows={4} placeholder="Arıza detaylarını yazın..." required />
              </div>

              <div>
                <Label>Öncelik *</Label>
                <select name="priority" className="w-full p-2 border rounded mt-1" required>
                  <option value="normal">Normal</option>
                  <option value="high">Yüksek</option>
                  <option value="urgent">Acil</option>
                </select>
              </div>

              <Button type="submit" className="w-full bg-indigo-600 hover:bg-indigo-700">
                Görev Oluştur
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    );
}
