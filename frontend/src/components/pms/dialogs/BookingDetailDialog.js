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


const BookingDetailDialog = ({ openDialog, setOpenDialog, selectedBooking, rooms, guests, loadBookingFolios }) => {
  const { t } = useTranslation();
  const [companies, setCompanies] = useState([]);

  return (
    <>
        <Dialog open={openDialog === 'bookingDetail'} onOpenChange={(open) => !open && setOpenDialog(null)}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>📋 Booking Details</DialogTitle>
              <DialogDescription>Full reservation information and actions</DialogDescription>
            </DialogHeader>
            
            {selectedBookingDetail && (
              <div className="space-y-4">
                {/* Guest & Room Info */}
                <div className="grid grid-cols-2 gap-4">
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm">Guest Information</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-600">Name:</span>
                        <span className="font-semibold">
                          {guests.find(g => g.id === selectedBookingDetail.guest_id)?.name || 'N/A'}
                        </span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-600">Email:</span>
                        <span className="text-xs">
                          {guests.find(g => g.id === selectedBookingDetail.guest_id)?.email || 'N/A'}
                        </span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-600">Phone:</span>
                        <span className="text-xs">
                          {guests.find(g => g.id === selectedBookingDetail.guest_id)?.phone || 'N/A'}
                        </span>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm">Room & Dates</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-600">Room:</span>
                        <span className="font-semibold">
                          {rooms.find(r => r.id === selectedBookingDetail.room_id)?.room_number || 'N/A'}
                        </span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-600">Check-in:</span>
                        <span className="font-semibold">
                          {new Date(selectedBookingDetail.check_in).toLocaleDateString()}
                        </span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-600">Check-out:</span>
                        <span className="font-semibold">
                          {new Date(selectedBookingDetail.check_out).toLocaleDateString()}
                        </span>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {/* Financial & Corporate Info */}
                <Card className="bg-gradient-to-r from-green-50 to-emerald-50">
                  <CardContent className="pt-4 space-y-3">
                    <div className="grid grid-cols-3 gap-4 text-center">
                      <div>
                        <div className="text-2xl font-bold text-green-700">
                          ${selectedBookingDetail.total_amount || 0}
                        </div>
                        <div className="text-xs text-gray-600">Total Amount</div>
                      </div>
                      <div>
                        <div className="text-2xl font-bold text-blue-700">
                          {selectedBookingDetail.adults || 1}
                        </div>
                        <div className="text-xs text-gray-600">Adults</div>
                      </div>
                      <div>
                        <div className="text-2xl font-bold text-purple-700">
                          {selectedBookingDetail.status?.toUpperCase() || 'N/A'}
                        </div>
                        <div className="text-xs text-gray-600">Status</div>
                      </div>
                    </div>

                    {selectedBookingDetail.company_id && (
                      <div className="grid grid-cols-2 gap-4 text-xs text-left bg-white/60 p-3 rounded border border-emerald-100">
                        <div className="space-y-1">
                          <div className="text-[11px] font-semibold text-gray-700">Corporate</div>
                          <div className="text-gray-800 font-medium">
                            {(() => {
                              const company = companies.find(c => c.id === selectedBookingDetail.company_id);
                              return company ? company.name : 'Corporate Booking';
                            })()}
                          </div>
                          <div className="text-[11px] text-gray-500">
                            Code: {
                              (() => {
                                const company = companies.find(c => c.id === selectedBookingDetail.company_id);
                                return company?.corporate_code || 'N/A';
                              })()
                            }
                          </div>
                        </div>
                        <div className="space-y-1">
                          <div className="text-[11px] font-semibold text-gray-700">Rate Details</div>
                          <div className="text-[11px] text-gray-600">
                            Contracted: <span className="font-medium">{selectedBookingDetail.contracted_rate || 'N/A'}</span>
                          </div>
                          <div className="text-[11px] text-gray-600">
                            Segment: <span className="font-medium">{selectedBookingDetail.market_segment || 'corporate'}</span>
                          </div>
                          <div className="text-[11px] text-gray-600">
                            Policy: <span className="font-medium">{selectedBookingDetail.cancellation_policy || 'standard'}</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Quick Actions */}
                <div className="grid grid-cols-3 gap-2">
                  <Button 
                    size="sm"
                    onClick={() => {
                      loadBookingFolios(selectedBookingDetail.id);
                      setOpenDialog(null);
                    }}
                    className="bg-green-600 hover:bg-green-700"
                  >
                    <DollarSign className="w-4 h-4 mr-1" />
                    View Folio
                  </Button>
                  <Button 
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      toast.info('Editing booking...');
                      // TODO: Open edit form
                    }}
                  >
                    <FileText className="w-4 h-4 mr-1" />
                    Edit Details
                  </Button>
                  <Button 
                    size="sm"
                    variant="outline"
                    className="border-red-400 text-red-700 hover:bg-red-50"
                    onClick={() => {
                      if (confirm('Cancel this booking?')) {
                        toast.success('Booking cancelled');
                        setOpenDialog(null);
                      }
                    }}
                  >
                    Cancel Booking
                  </Button>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>
    </>
  );
};

export default BookingDetailDialog;
