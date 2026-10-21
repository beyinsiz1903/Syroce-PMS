import { cloneElement, isValidElement, useId } from 'react';
import {
  Card, CardContent, CardHeader, CardTitle,
} from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import './mice-print.css';

export const Stat = ({ label, value, cls = 'text-gray-900' }) => (
  <Card><CardContent className="p-4">
    <div className="text-xs text-gray-500">{label}</div>
    <div className={`text-xl font-bold ${cls}`}>{value}</div>
  </CardContent></Card>
);

export const Field = ({ label, children }) => {
  const generated = useId();
  const id = children?.props?.id || generated;
  return <div><Label htmlFor={id} className="text-xs">{label}</Label>{isValidElement(children) ? cloneElement(children, { id }) : children}</div>;
};

export const Info = ({ l, v, cls = '' }) => (
  <div><div className="text-gray-500">{l}</div><div className={cls || 'font-medium'}>{v == null || v === '' ? '—' : v}</div></div>
);

export const Modal = ({ title, onClose, children, wide }) => (
  <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent data-mice-print-root overlayClassName="mice-dialog-overlay" className={`${wide ? 'max-w-5xl' : 'max-w-lg'} max-h-[90vh] overflow-y-auto`}
      onPointerDownOutside={e => e.preventDefault()}>
      <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
      {children}
    </DialogContent>
  </Dialog>
);
