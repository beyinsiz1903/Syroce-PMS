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

export default function MobileMaintenanceSlaConfigModal({ slaConfigModalOpen, setSlaConfigModalOpen, slaConfigurations, getPriorityColor, handleSlaUpdate }) {
    const { t } = useTranslation();
    return (
        <Dialog open={slaConfigModalOpen} onOpenChange={setSlaConfigModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <Settings className="w-5 h-5" />
              <span>SLA Ayarları</span>
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            <p className="text-sm text-gray-600">
              Her öncelik seviyesi için yanıt ve çözüm sürelerini ayarlayın (dakika cinsinden)
            </p>
            
            {slaConfigurations.map(config => <Card key={config.priority} className="border-2">
                <CardContent className="p-4">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Badge className={getPriorityColor(config.priority)}>
                        {config.priority.toUpperCase()}
                      </Badge>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label className="text-xs">Yanıt Süresi (dk)</Label>
                        <Input type="number" defaultValue={config.response_time_minutes} id={`response-${config.priority}`} className="mt-1" />
                      </div>
                      <div>
                        <Label className="text-xs">Çözüm Süresi (dk)</Label>
                        <Input type="number" defaultValue={config.resolution_time_minutes} id={`resolution-${config.priority}`} className="mt-1" />
                      </div>
                    </div>
                    
                    <Button size="sm" className="w-full" onClick={() => {
              const response = document.getElementById(`response-${config.priority}`).value;
              const resolution = document.getElementById(`resolution-${config.priority}`).value;
              handleSlaUpdate(config.priority, response, resolution);
            }}>
                      Kaydet
                    </Button>
                  </div>
                </CardContent>
              </Card>)}
          </div>
        </DialogContent>
      </Dialog>
    );
}
