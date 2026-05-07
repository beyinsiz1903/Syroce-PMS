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
import { Wallet, CreditCard, TrendingUp, AlertTriangle, FileText, DollarSign, ArrowDownCircle, ArrowUpCircle, Receipt, Banknote, Clock, CheckCircle, XCircle, Calendar, Filter, Download, FileDown, Upload, Eye, Search, Plus, Minus, RefreshCw, ChevronRight, ChevronDown, BarChart3, PieChart, Activity, Users, Building, Briefcase, ShoppingCart, Coffee, Utensils, Bed, Home } from 'lucide-react';

export default function PlDetailModal(props) {
  const { downloadPLReport, formatCurrency, formatPercent, plData, plDetailModalOpen, setPlDetailModalOpen } = props;
  return (
    <Dialog open={plDetailModalOpen} onOpenChange={setPlDetailModalOpen}>
      <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center space-x-2">
            <BarChart3 className="w-5 h-5 text-green-600" />
            <span>Kar/Zarar Detayı (P&L)</span>
          </DialogTitle>
        </DialogHeader>
    
        {plData ? (
          <div className="space-y-4">
            {/* Period Info */}
            <Card className="bg-gradient-to-r from-green-50 to-blue-50">
              <CardContent className="p-4">
                <div className="text-center">
                  <p className="text-sm text-gray-600">Dönem</p>
                  <p className="text-lg font-bold text-gray-900">
                    {plData.period || new Date().toLocaleDateString('tr-TR', { year: 'numeric', month: 'long' })}
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Revenue Section */}
            <Card>
              <CardHeader className="pb-3 bg-green-50">
                <CardTitle className="text-base text-green-800">Gelirler</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 pt-3">
                <div className="flex justify-between p-2 bg-green-50 rounded">
                  <span className="text-gray-700">Oda Gelirleri:</span>
                  <span className="font-bold">{formatCurrency(plData.room_revenue || 0)}</span>
                </div>
                <div className="flex justify-between p-2">
                  <span className="text-gray-700">F&B Gelirleri:</span>
                  <span className="font-bold">{formatCurrency(plData.fnb_revenue || 0)}</span>
                </div>
                <div className="flex justify-between p-2 bg-green-50 rounded">
                  <span className="text-gray-700">Diğer Gelirler:</span>
                  <span className="font-bold">{formatCurrency(plData.other_revenue || 0)}</span>
                </div>
                <div className="flex justify-between p-3 bg-green-200 rounded-lg border-2 border-green-400 mt-2">
                  <span className="font-bold text-green-900">TOPLAM GELİR:</span>
                  <span className="font-bold text-xl text-green-700">
                    {formatCurrency(plData.total_revenue || 0)}
                  </span>
                </div>
              </CardContent>
            </Card>

            {/* Cost of Sales Section */}
            <Card>
              <CardHeader className="pb-3 bg-amber-50">
                <CardTitle className="text-base text-amber-800">Satış Maliyeti</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 pt-3">
                <div className="flex justify-between p-2 bg-amber-50 rounded">
                  <span className="text-gray-700">F&B Maliyeti:</span>
                  <span className="font-bold">{formatCurrency(plData.fnb_cost || 0)}</span>
                </div>
                <div className="flex justify-between p-2">
                  <span className="text-gray-700">Housekeeping Maliyeti:</span>
                  <span className="font-bold">{formatCurrency(plData.housekeeping_cost || 0)}</span>
                </div>
                <div className="flex justify-between p-3 bg-amber-200 rounded-lg border-2 border-amber-400 mt-2">
                  <span className="font-bold text-amber-900">TOPLAM SATIŞ MALİYETİ:</span>
                  <span className="font-bold text-xl text-amber-700">
                    {formatCurrency(plData.total_cost_of_sales || 0)}
                  </span>
                </div>
              </CardContent>
            </Card>

            {/* Gross Profit */}
            <Card className="bg-blue-50">
              <CardContent className="p-4">
                <div className="flex justify-between items-center">
                  <div>
                    <p className="text-sm text-blue-700 font-medium">BRÜT KAR</p>
                    <p className="text-xs text-blue-600 mt-1">
                      Brüt Kar Marjı: {formatPercent(plData.gross_profit_margin || 0)}
                    </p>
                  </div>
                  <p className="text-3xl font-bold text-blue-700">
                    {formatCurrency(plData.gross_profit || 0)}
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Operating Expenses */}
            <Card>
              <CardHeader className="pb-3 bg-indigo-50">
                <CardTitle className="text-base text-indigo-800">Faaliyet Giderleri</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 pt-3">
                <div className="flex justify-between p-2 bg-indigo-50 rounded">
                  <span className="text-gray-700">Personel Giderleri:</span>
                  <span className="font-bold">{formatCurrency(plData.personnel_cost || 0)}</span>
                </div>
                <div className="flex justify-between p-2">
                  <span className="text-gray-700">Enerji Giderleri:</span>
                  <span className="font-bold">{formatCurrency(plData.utility_cost || 0)}</span>
                </div>
                <div className="flex justify-between p-2 bg-indigo-50 rounded">
                  <span className="text-gray-700">Bakım Onarım:</span>
                  <span className="font-bold">{formatCurrency(plData.maintenance_cost || 0)}</span>
                </div>
                <div className="flex justify-between p-2">
                  <span className="text-gray-700">Pazarlama Giderleri:</span>
                  <span className="font-bold">{formatCurrency(plData.marketing_cost || 0)}</span>
                </div>
                <div className="flex justify-between p-2 bg-indigo-50 rounded">
                  <span className="text-gray-700">Yönetim Giderleri:</span>
                  <span className="font-bold">{formatCurrency(plData.admin_cost || 0)}</span>
                </div>
                <div className="flex justify-between p-3 bg-indigo-200 rounded-lg border-2 border-indigo-400 mt-2">
                  <span className="font-bold text-indigo-900">TOPLAM FAALİYET GİDERİ:</span>
                  <span className="font-bold text-xl text-indigo-700">
                    {formatCurrency(plData.total_operating_expenses || 0)}
                  </span>
                </div>
              </CardContent>
            </Card>

            {/* Net Profit/Loss */}
            <Card className={plData.net_profit >= 0 ? 'bg-green-100' : 'bg-red-100'}>
              <CardContent className="p-5">
                <div className="flex justify-between items-center">
                  <div>
                    <p className={`text-lg font-bold ${plData.net_profit >= 0 ? 'text-green-900' : 'text-red-900'}`}>
                      {plData.net_profit >= 0 ? 'NET KAR' : 'NET ZARAR'}
                    </p>
                    <p className={`text-sm mt-1 ${plData.net_profit >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                      Net Kar Marjı: {formatPercent(plData.net_profit_margin || 0)}
                    </p>
                  </div>
                  <p className={`text-4xl font-bold ${plData.net_profit >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                    {formatCurrency(Math.abs(plData.net_profit || 0))}
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Key Ratios */}
            {plData.key_metrics && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Anahtar Metrikler</CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-2 gap-3">
                  <div className="text-center p-3 bg-blue-50 rounded">
                    <p className="text-xs text-blue-600">RevPAR</p>
                    <p className="text-lg font-bold text-blue-900">
                      {formatCurrency(plData.key_metrics.revpar || 0)}
                    </p>
                  </div>
                  <div className="text-center p-3 bg-green-50 rounded">
                    <p className="text-xs text-green-600">ADR</p>
                    <p className="text-lg font-bold text-green-900">
                      {formatCurrency(plData.key_metrics.adr || 0)}
                    </p>
                  </div>
                  <div className="text-center p-3 bg-indigo-50 rounded">
                    <p className="text-xs text-indigo-600">Occ %</p>
                    <p className="text-lg font-bold text-indigo-900">
                      {formatPercent(plData.key_metrics.occupancy || 0)}
                    </p>
                  </div>
                  <div className="text-center p-3 bg-amber-50 rounded">
                    <p className="text-xs text-amber-600">GOP %</p>
                    <p className="text-lg font-bold text-amber-900">
                      {formatPercent(plData.key_metrics.gop_percentage || 0)}
                    </p>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Download Buttons */}
            <div className="grid grid-cols-2 gap-3">
              <Button 
                className="w-full bg-green-600 hover:bg-green-700"
                onClick={downloadPLReport}
              >
                <Download className="w-4 h-4 mr-2" />
                PDF İndir
              </Button>
              <Button 
                variant="outline"
                className="w-full"
                onClick={() => window.print()}
              >
                <FileDown className="w-4 h-4 mr-2" />
                Yazdır
              </Button>
            </div>
          </div>
        ) : (
          <div className="text-center py-8">
            <FileText className="w-12 h-12 mx-auto text-gray-300 mb-2" />
            <p className="text-gray-500">P&L raporu yükleniyor...</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
