import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { FileText, Send, Download, CheckCircle, XCircle, Clock } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const EFaturaModule = () => {
  const { t } = useTranslation();
  const [invoices, setInvoices] = useState([]);
  const [posClosures, setPosClosures] = useState([]);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [invoicesRes, posRes, settingsRes] = await Promise.all([
        axios.get('/efatura/invoices'),
        axios.get('/pos/daily-closures'),
        axios.get('/efatura/settings')
      ]);

      setInvoices(invoicesRes.data.invoices || []);
      setPosClosures(posRes.data.closures || []);
      setSettings(settingsRes.data);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSendEFatura = async (invoiceId) => {
    try {
      await axios.post(`/efatura/send/${invoiceId}`);
      toast.success('E-Fatura sent successfully');
      loadData();
    } catch (error) {
      toast.error('Failed to send e-fatura');
    }
  };

  const handlePOSClosure = async () => {
    try {
      const response = await axios.post('/pos/daily-closure');
      toast.success(`Daily closure completed: ${response.data.total_sales} TL`);
      loadData();
    } catch (error) {
      toast.error('Failed to complete closure');
    }
  };

  const getStatusBadge = (status) => {
    const configs = {
      pending: { color: 'bg-yellow-100 text-yellow-700', icon: <Clock className="w-3 h-3" /> },
      sent: { color: 'bg-blue-100 text-blue-700', icon: <Send className="w-3 h-3" /> },
      accepted: { color: 'bg-green-100 text-green-700', icon: <CheckCircle className="w-3 h-3" /> },
      rejected: { color: 'bg-red-100 text-red-700', icon: <XCircle className="w-3 h-3" /> }
    };
    const config = configs[status] || configs.pending;
    return (
      <Badge className={config.color}>
        {config.icon}
        <span className="ml-1">{status}</span>
      </Badge>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">E-Fatura & POS Integration</h1>
          <p className="text-gray-600">Electronic invoicing & daily closures</p>
        </div>
        <Button onClick={handlePOSClosure}>
          <FileText className="w-4 h-4 mr-2" />
          Daily POS Closure
        </Button>
      </div>

      {/* E-Fatura Settings */}
      <Card>
        <CardHeader>
          <CardTitle>E-Fatura Settings</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Company VKN</Label>
              <Input value={settings?.vkn || ''} readOnly />
            </div>
            <div>
              <Label>E-Fatura Status</Label>
              <Badge className="bg-green-100 text-green-700 mt-2">
                {settings?.enabled ? 'Active' : 'Inactive'}
              </Badge>
            </div>
            <div>
              <Label>Auto-send</Label>
              <Badge className={settings?.auto_send ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}>
                {settings?.auto_send ? 'Enabled' : 'Disabled'}
              </Badge>
            </div>
            <div>
              <Label>Last Sync</Label>
              <div className="text-sm text-gray-600 mt-2">
                {settings?.last_sync ? new Date(settings.last_sync).toLocaleString() : 'Never'}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* E-Fatura List */}
      <Card>
        <CardHeader>
          <CardTitle>Recent E-Fatura Documents</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-2">Invoice No</th>
                  <th className="text-left p-2">Customer</th>
                  <th className="text-left p-2">Date</th>
                  <th className="text-right p-2">Amount</th>
                  <th className="text-left p-2">Status</th>
                  <th className="text-left p-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((invoice) => (
                  <tr key={invoice.id} className="border-b hover:bg-gray-50">
                    <td className="p-2 font-semibold">{invoice.invoice_number}</td>
                    <td className="p-2">{invoice.customer_name}</td>
                    <td className="p-2">{new Date(invoice.created_at).toLocaleDateString()}</td>
                    <td className="p-2 text-right font-semibold">{invoice.total_amount} TL</td>
                    <td className="p-2">{getStatusBadge(invoice.efatura_status)}</td>
                    <td className="p-2">
                      <div className="flex gap-2">
                        {invoice.efatura_status === 'pending' && (
                          <Button size="sm" onClick={() => handleSendEFatura(invoice.id)}>
                            <Send className="w-3 h-3 mr-1" />
                            Send
                          </Button>
                        )}
                        <Button size="sm" variant="outline">
                          <Download className="w-3 h-3 mr-1" />
                          PDF
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* POS Daily Closures */}
      <Card>
        <CardHeader>
          <CardTitle>POS Daily Closures</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {posClosures.slice(0, 7).map((closure) => (
              <div key={closure.id} className="flex justify-between items-center p-4 bg-gray-50 rounded">
                <div>
                  <div className="font-semibold">{new Date(closure.closure_date).toLocaleDateString()}</div>
                  <div className="text-sm text-gray-600">
                    {closure.transaction_count} transactions
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-bold text-green-600">{closure.total_sales} TL</div>
                  <div className="text-xs text-gray-600">Cash: {closure.cash_sales} TL | Card: {closure.card_sales} TL</div>
                </div>
                <Button size="sm" variant="outline">
                  <Download className="w-4 h-4 mr-1" />
                  Report
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default EFaturaModule;