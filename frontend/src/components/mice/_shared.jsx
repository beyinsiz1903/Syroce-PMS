import {
  Card, CardContent, CardHeader, CardTitle,
} from '@/components/ui/card';
import { Label } from '@/components/ui/label';

export const Stat = ({ label, value, cls = 'text-gray-900' }) => (
  <Card><CardContent className="p-4">
    <div className="text-xs text-gray-500">{label}</div>
    <div className={`text-xl font-bold ${cls}`}>{value}</div>
  </CardContent></Card>
);

export const Field = ({ label, children }) => (
  <div><Label className="text-xs">{label}</Label>{children}</div>
);

export const Info = ({ l, v, cls = '' }) => (
  <div><div className="text-gray-500">{l}</div><div className={cls || 'font-medium'}>{v || '—'}</div></div>
);

export const Modal = ({ title, onClose, children, wide }) => (
  <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
    <Card className={`w-full ${wide ? 'max-w-5xl' : 'max-w-lg'} max-h-[90vh] overflow-hidden flex flex-col`}
          onClick={(e) => e.stopPropagation()}>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent className="overflow-y-auto">{children}</CardContent>
    </Card>
  </div>
);
