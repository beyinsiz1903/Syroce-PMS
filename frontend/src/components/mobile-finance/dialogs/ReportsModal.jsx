import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Wallet, CreditCard, TrendingUp, AlertTriangle, FileText, DollarSign, ArrowDownCircle, ArrowUpCircle, Receipt, Banknote, Clock, CheckCircle, XCircle, Calendar, Filter, Download, Upload, Eye, Search, Plus, Minus, RefreshCw, ChevronRight, ChevronDown, BarChart3, PieChart, Activity, Users, Building, Briefcase, ShoppingCart, Coffee, Utensils, Bed, Home } from 'lucide-react';

export default function ReportsModal(props) {
  const { dailyCollections, formatCurrency, formatPercent, monthlyCollections, monthlyCosts, reportsModalOpen, setReportsModalOpen } = props;
  return (
    <Dialog open={reportsModalOpen} onOpenChange={setReportsModalOpen}>
      <DialogContent className="max-w-full w-[95vw] max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Finansal Raporlar</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Günlük Özet</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex justify-between">
                <span className="text-gray-600">Bugün Tahsilat:</span>
                <span className="font-bold text-green-700">{formatCurrency(dailyCollections?.total_collected || 0)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">İşlem Sayısı:</span>
                <span className="font-bold">{dailyCollections?.payment_count || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Ortalama İşlem:</span>
                <span className="font-bold">{formatCurrency(dailyCollections?.average_transaction || 0)}</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Aylık Özet</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex justify-between">
                <span className="text-gray-600">Toplam Tahsilat:</span>
                <span className="font-bold text-green-700">{formatCurrency(monthlyCollections?.total_collected || 0)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Beklenen Tutar:</span>
                <span className="font-bold">{formatCurrency(monthlyCollections?.total_expected || 0)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Tahsilat Oranı:</span>
                <span className="font-bold text-blue-700">{formatPercent(monthlyCollections?.collection_rate || 0)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Kalan Alacak:</span>
                <span className="font-bold text-amber-700">{formatCurrency(monthlyCollections?.outstanding || 0)}</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Maliyet Özeti</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex justify-between">
                <span className="text-gray-600">Aylık Maliyet:</span>
                <span className="font-bold text-red-700">{formatCurrency(monthlyCosts?.total_costs || 0)}</span>
              </div>
              {monthlyCosts?.costs_by_category && Object.entries(monthlyCosts.costs_by_category).map(([category, amount]) => (
                <div key={category} className="flex justify-between pl-4">
                  <span className="text-sm text-gray-500 capitalize">{category}:</span>
                  <span className="text-sm">{formatCurrency(amount)}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </DialogContent>
    </Dialog>
  );
}
