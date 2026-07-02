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

export default function MobileMaintenanceFilterModal({ filterModalOpen, setFilterModalOpen, filters, setFilters, applyFilters, clearFilters }) {
    const { t } = useTranslation();
    return (
        <Dialog open={filterModalOpen} onOpenChange={setFilterModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <Filter className="w-5 h-5" />
              <span>Görev Filtreleme</span>
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            <div>
              <Label>Durum</Label>
              <Select value={filters.status || "__all__"} onValueChange={val => setFilters({
          ...filters,
          status: val === "__all__" ? "" : val
        })}>
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder={t("common.all")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">{t("common.all")}</SelectItem>
                  <SelectItem value="open">Açık</SelectItem>
                  <SelectItem value="in_progress">Devam Ediyor</SelectItem>
                  <SelectItem value="on_hold">Beklemede</SelectItem>
                  <SelectItem value="waiting_parts">Parça Bekliyor</SelectItem>
                  <SelectItem value="completed">Tamamlandı</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div>
              <Label>Öncelik</Label>
              <Select value={filters.priority || "__all__"} onValueChange={val => setFilters({
          ...filters,
          priority: val === "__all__" ? "" : val
        })}>
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder={t("common.all")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">{t("common.all")}</SelectItem>
                  <SelectItem value="emergency">Acil</SelectItem>
                  <SelectItem value="urgent">Çok Acil</SelectItem>
                  <SelectItem value="high">Yüksek</SelectItem>
                  <SelectItem value="normal">Normal</SelectItem>
                  <SelectItem value="low">Düşük</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div>
              <Label>Başlangıç Tarihi</Label>
              <Input type="date" value={filters.start_date} onChange={e => setFilters({
          ...filters,
          start_date: e.target.value
        })} className="mt-1" />
            </div>
            
            <div>
              <Label>Bitiş Tarihi</Label>
              <Input type="date" value={filters.end_date} onChange={e => setFilters({
          ...filters,
          end_date: e.target.value
        })} className="mt-1" />
            </div>
            
            <div className="flex space-x-2">
              <Button className="flex-1" onClick={applyFilters}>
                <Filter className="w-4 h-4 mr-2" />
                Uygula
              </Button>
              <Button variant="outline" onClick={clearFilters}>
                <X className="w-4 h-4 mr-2" />
                Temizle
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    );
}
