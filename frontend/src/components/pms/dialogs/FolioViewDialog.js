import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Plus, X, Calendar, User, CreditCard, BedDouble, Search,
  CheckCircle, Clock, DollarSign, MapPin, Phone, Mail,
  FileText, Download, Trash2, Edit, Eye, Star, Upload
} from 'lucide-react';


const FolioViewDialog = ({ openDialog, setOpenDialog, selectedFolio, setSelectedFolio, guests, bookings }) => {
  const { t } = useTranslation();

  return (
    <>
        <Dialog open={openDialog === 'folio-view'} onOpenChange={(open) => !open && setOpenDialog(null)}>
          <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Folio Management</DialogTitle>
              <DialogDescription>
                {selectedFolio && `Folio ${selectedFolio.folio_number} - ${selectedFolio.folio_type.toUpperCase()}`}
              </DialogDescription>
            </DialogHeader>

            {selectedFolio && (
              <div className="space-y-6">
                {/* Header Summary */}
                <div className="bg-gradient-to-r from-blue-50 to-purple-50 p-6 rounded-lg border">
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <div className="text-sm text-gray-600">Guest</div>
                      <div className="font-semibold">
                        {guests.find(g => g.id === selectedFolio.guest_id)?.name || 'N/A'}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600">Booking</div>
                      <div className="font-semibold">
                        {(() => {
                          const booking = bookings.find(b => b.id === selectedFolio.booking_id);
                          if (!booking) return 'N/A';
                          return `${new Date(booking.check_in).toLocaleDateString()} - ${new Date(booking.check_out).toLocaleDateString()}`;
                        })()}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600">Current Balance</div>
                      <div className={`text-2xl font-bold ${selectedFolio.balance > 0 ? 'text-red-600' : selectedFolio.balance < 0 ? 'text-green-600' : 'text-gray-600'}`}>
                        ${selectedFolio.balance?.toFixed(2) || '0.00'}
                      </div>
                      <div className="text-xs text-gray-500">
                        {selectedFolio.balance > 0 ? 'Guest owes hotel' : selectedFolio.balance < 0 ? 'Hotel owes guest' : 'Balanced'}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="flex gap-2">
                  <Button onClick={() => setOpenDialog('post-charge')} variant="default">
                    <Plus className="w-4 h-4 mr-2" />
                    Post Charge
                  </Button>
                  <Button onClick={() => setOpenDialog('post-payment')} variant="default">
                    <Plus className="w-4 h-4 mr-2" />
                    Post Payment
                  </Button>
                </div>

                {/* Charges and Payments Lists */}
                <div className="grid grid-cols-2 gap-6">
                  {/* Charges List */}
                  <div>
                    <h3 className="text-lg font-semibold mb-3 flex items-center">
                      <ClipboardList className="w-5 h-5 mr-2" />
                      Charges
                    </h3>
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {folioCharges.length === 0 ? (
                        <div className="text-center text-gray-400 py-8">No charges posted</div>
                      ) : 
                        folioCharges.map((charge) => {
                          // Check if this is a POS charge with line items
                          const isPOSCharge = charge.charge_category === 'restaurant' || charge.charge_category === 'bar' || charge.charge_category === 'room_service';
                          const hasLineItems = charge.line_items && charge.line_items.length > 0;
                          const isExpanded = expandedChargeItems[charge.id];
                          
                          return (
                          <Card key={charge.id} className={charge.voided ? 'opacity-50 bg-gray-50' : ''}>
                            <CardContent className="p-4">
                              <div 
                                className={`flex justify-between items-start ${isPOSCharge && hasLineItems ? 'cursor-pointer hover:bg-gray-50' : ''}`}
                                onClick={() => {
                                  if (isPOSCharge && hasLineItems) {
                                    setExpandedChargeItems(prev => ({
                                      ...prev,
                                      [charge.id]: !prev[charge.id]
                                    }));
                                  }
                                }}
                              >
                                <div className="flex-1">
                                  <div className="flex items-center gap-2">
                                    <div className="font-semibold">{charge.description}</div>
                                    {isPOSCharge && hasLineItems && (
                                      <button className="text-blue-600 text-xs">
                                        {isExpanded ? '▼ Hide Items' : '▶ Show Items'}
                                      </button>
                                    )}
                                  </div>
                                  <div className="text-sm text-gray-600">
                                    {charge.charge_category.replace('_', ' ').toUpperCase()}
                                  </div>
                                  <div className="text-xs text-gray-500">
                                    {new Date(charge.date).toLocaleDateString()} • Qty: {charge.quantity}
                                  </div>
                                  {charge.voided && (
                                    <div className="text-xs text-red-600 mt-1">
                                      VOIDED: {charge.void_reason}
                                    </div>
                                  )}
                                </div>
                                <div className="text-right">
                                  <div className="font-bold">${charge.total.toFixed(2)}</div>
                                  {charge.tax_amount > 0 && (
                                    <div className="text-xs text-gray-500">
                                      +${charge.tax_amount.toFixed(2)} tax
                                    </div>
                                  )}
                                </div>
                              </div>

                              {/* POS Line Items Breakdown - NEW */}
                              {isPOSCharge && hasLineItems && isExpanded && (
                                <div className="mt-3 pt-3 border-t bg-blue-50/50 rounded p-3">
                                  <div className="text-xs font-semibold text-gray-700 mb-2">POS Fiş Detayı:</div>
                                  <div className="space-y-1.5">
                                    {charge.line_items.map((item, idx) => (
                                      <div key={idx} className="flex justify-between items-center text-sm">
                                        <div className="flex-1">
                                          <span className="font-medium text-gray-700">
                                            {item.quantity} x {item.item_name}
                                          </span>
                                          {item.modifiers && item.modifiers.length > 0 && (
                                            <div className="text-xs text-gray-500 ml-4">
                                              ({item.modifiers.join(', ')})
                                            </div>
                                          )}
                                        </div>
                                        <span className="font-semibold text-gray-800">
                                          ${(item.unit_price * item.quantity).toFixed(2)}
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                  <div className="mt-2 pt-2 border-t flex justify-between text-sm">
                                    <span className="font-semibold">Subtotal:</span>
                                    <span className="font-bold">${charge.total.toFixed(2)}</span>
                                  </div>
                                </div>
                              )}
                            </CardContent>
                          </Card>
                        );
                        })
                      }
                    </div>
                    <div className="mt-4 pt-4 border-t">
                      <div className="flex justify-between font-semibold">
                        <span>Total Charges:</span>
                        <span>${folioCharges.filter(c => !c.voided).reduce((sum, c) => sum + c.total, 0).toFixed(2)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Payments List */}
                  <div>
                    <h3 className="text-lg font-semibold mb-3 flex items-center">
                      <DollarSign className="w-5 h-5 mr-2" />
                      Payments
                    </h3>
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {folioPayments.length === 0 ? (
                        <div className="text-center text-gray-400 py-8">No payments posted</div>
                      ) : (
                        folioPayments.map((payment) => (
                          <Card key={payment.id} className="bg-green-50">
                            <CardContent className="p-4">
                              <div className="flex justify-between items-start">
                                <div className="flex-1">
                                  <div className="font-semibold">{payment.method.toUpperCase()}</div>
                                  <div className="text-sm text-gray-600">
                                    {payment.payment_type.replace('_', ' ').toUpperCase()}
                                  </div>
                                  <div className="text-xs text-gray-500">
                                    {new Date(payment.processed_at).toLocaleDateString()}
                                  </div>
                                  {payment.reference && (
                                    <div className="text-xs text-gray-500">
                                      Ref: {payment.reference}
                                    </div>
                                  )}
                                </div>
                                <div className="text-right">
                                  <div className="font-bold text-green-600">${payment.amount.toFixed(2)}</div>
                                </div>
                              </div>
                            </CardContent>
                          </Card>
                        ))
                      )}
                    </div>
                    <div className="mt-4 pt-4 border-t">
                      <div className="flex justify-between font-semibold">
                        <span>Total Payments:</span>
                        <span className="text-green-600">${folioPayments.reduce((sum, p) => sum + p.amount, 0).toFixed(2)}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Net Balance */}
                <div className="bg-gray-50 p-6 rounded-lg border-2 border-gray-300">
                  <div className="flex justify-between items-center">
                    <span className="text-xl font-semibold">Net Balance:</span>
                    <span className={`text-3xl font-bold ${selectedFolio.balance > 0 ? 'text-red-600' : selectedFolio.balance < 0 ? 'text-green-600' : 'text-gray-600'}`}>
                      ${selectedFolio.balance?.toFixed(2) || '0.00'}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>
    </>
  );
};

export default FolioViewDialog;
