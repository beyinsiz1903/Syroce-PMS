import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { CreditCard } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const PaymentGateway = () => {
  const { t } = useTranslation();
  const [amount, setAmount] = useState(100);
  const [months, setMonths] = useState(1);
  const [calc, setCalc] = useState(null);

  useEffect(() => {
    if (amount > 0) {
      axios.get(`/payments/installment?amount=${amount}&months=${months}`)
        .then(res => setCalc(res.data))
        .catch(() => {});
    }
  }, [amount, months]);

  return (
    <div className="p-6">
      <h1 className="text-3xl font-bold mb-8">💳 {t('dashboard.paymentGatewayModule')}</h1>
      <Card>
        <CardHeader><CardTitle>Taksit Hesaplama</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm">Tutar (€)</label>
            <Input type="number" value={amount} onChange={(e) => setAmount(parseFloat(e.target.value))} />
          </div>
          <div>
            <label className="text-sm">Taksit</label>
            <Select value={String(months)} onValueChange={(v) => setMonths(parseInt(v))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="1">Peşin</SelectItem>
                <SelectItem value="3">3 Taksit</SelectItem>
                <SelectItem value="6">6 Taksit</SelectItem>
                <SelectItem value="12">12 Taksit</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {calc && (
            <div className="p-4 bg-blue-50 rounded-lg">
              <p className="text-sm">Aylık:</p>
              <p className="text-2xl font-bold text-blue-600">€{calc.monthly}</p>
              <p className="text-xs text-gray-500">Toplam: €{calc.total}</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default PaymentGateway;