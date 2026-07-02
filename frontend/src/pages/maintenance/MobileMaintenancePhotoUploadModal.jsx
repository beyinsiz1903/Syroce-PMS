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

export default function MobileMaintenancePhotoUploadModal({ photoUploadModalOpen, setPhotoUploadModalOpen, photoType, setPhotoType, setPhotoFile, photoFile, handlePhotoUpload }) {
    const { t } = useTranslation();
    return (
        <Dialog open={photoUploadModalOpen} onOpenChange={setPhotoUploadModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Fotoğraf Yükle</DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            <div>
              <Label>Fotoğraf Türü</Label>
              <Select value={photoType} onValueChange={setPhotoType}>
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="before">Öncesi</SelectItem>
                  <SelectItem value="during">Süreç</SelectItem>
                  <SelectItem value="after">Sonrası</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div>
              <Label>Fotoğraf Seç</Label>
              <Input type="file" accept="image/*" capture="environment" onChange={e => setPhotoFile(e.target.files[0])} className="mt-1" />
            </div>
            
            {photoFile && <div className="p-2 bg-green-50 rounded text-sm">
                <p className="font-semibold">Seçilen dosya:</p>
                <p>{photoFile.name}</p>
              </div>}
            
            <Button className="w-full" onClick={handlePhotoUpload} disabled={!photoFile}>
              <Upload className="w-4 h-4 mr-2" />
              Yükle
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    );
}
