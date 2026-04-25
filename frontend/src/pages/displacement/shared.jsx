import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { CheckCircle2, XCircle, AlertTriangle, Info, RefreshCw } from 'lucide-react';

export const REC_STYLES = {
  accept: { bg: 'bg-emerald-50', border: 'border-emerald-300', icon: CheckCircle2, color: 'text-emerald-700' },
  reject: { bg: 'bg-red-50', border: 'border-red-300', icon: XCircle, color: 'text-red-700' },
  conditional: { bg: 'bg-amber-50', border: 'border-amber-300', icon: AlertTriangle, color: 'text-amber-700' },
};

export const MetricCard = ({ icon: Icon, label, value, prefix = '' }) => (
  <Card>
    <CardContent className="p-4 flex items-center gap-3">
      <div className="p-2.5 rounded-lg bg-blue-50">
        <Icon className="w-5 h-5 text-blue-600" />
      </div>
      <div>
        <p className="text-xs text-gray-500">{label}</p>
        <p className="text-lg font-bold">{prefix}{value}</p>
      </div>
    </CardContent>
  </Card>
);

export const SummaryCard = ({ label, value, icon: Icon, color }) => (
  <Card>
    <CardContent className="p-3 text-center">
      <Icon className={`w-5 h-5 mx-auto mb-1 ${color}`} />
      <p className={`text-sm font-bold ${color}`}>{value}</p>
      <p className="text-[10px] text-gray-500 mt-0.5">{label}</p>
    </CardContent>
  </Card>
);

export const LoadingState = ({ text }) => (
  <div className="flex items-center justify-center py-20 text-gray-500">
    <RefreshCw className="w-5 h-5 animate-spin mr-2" />
    {text}
  </div>
);

export const EmptyState = ({ text }) => (
  <div className="flex flex-col items-center justify-center py-20 text-gray-400">
    <Info className="w-10 h-10 mb-3" />
    <p className="text-sm text-center max-w-md">{text}</p>
  </div>
);
