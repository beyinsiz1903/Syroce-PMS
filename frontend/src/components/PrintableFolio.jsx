import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Printer, Download, X } from 'lucide-react';
import { alertDialog } from '@/lib/dialogs';

const PrintableFolio = ({ folioData, onClose }) => {
  const [guestData, setGuestData] = useState(null);
  const [roomData, setRoomData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (folioData) {
      fetchAdditionalData();
    }
  }, [folioData]);

  const fetchAdditionalData = async () => {
    try {
      const token = localStorage.getItem('token');
      
      // Fetch guest info
      const guestResponse = await fetch(
        `/api/guests/${folioData.booking.guest_id}`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );
      const guestData = await guestResponse.json();
      setGuestData(guestData.guest);
      
      // Fetch room info
      const roomsResponse = await fetch(
        `/api/pms/rooms`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );
      const roomsData = await roomsResponse.json();
      const room = roomsData.rooms.find(r => r.id === folioData.booking.room_id);
      setRoomData(room);
    } catch (error) {
      console.error('Error fetching additional data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const handleDownloadPDF = () => {
    // For actual PDF generation, you would use a library like jsPDF or html2pdf
    alertDialog({ message: 'PDF download functionality - integrate with PDF library like html2pdf.js' });
  };

  const formatDate = (date) => {
    if (!date) return 'N/A';
    try {
      return new Date(date).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
    } catch {
      return date;
    }
  };

  const formatDateTime = (date) => {
    if (!date) return 'N/A';
    try {
      return new Date(date).toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return date;
    }
  };

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <Card className="w-full max-w-4xl">
          <CardContent className="p-6">
            <div className="animate-pulse space-y-4">
              <div className="h-4 bg-gray-200 rounded w-3/4"></div>
              <div className="h-4 bg-gray-200 rounded w-1/2"></div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const { charges, payments } = folioData;
  const totalCharges = charges.reduce((sum, c) => sum + (c.total || c.amount || 0), 0);
  const totalPayments = payments.reduce((sum, p) => sum + (p.amount || 0), 0);
  const balance = totalCharges - totalPayments;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4 overflow-auto">
      <Card className="w-full max-w-5xl max-h-[95vh] overflow-auto bg-white">
        <CardHeader className="border-b-2 print:border-black">
          <div className="flex justify-between items-start">
            <div className="flex-1">
              <div className="text-center mb-4">
                <h1 className="text-3xl font-bold mb-2">GUEST FOLIO</h1>
                <div className="text-sm text-gray-600">
                  Hotel Management System
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="font-semibold">Folio Number:</span> {folioData.folio_number}
                </div>
                <div>
                  <span className="font-semibold">Date Printed:</span> {formatDate(new Date())}
                </div>
              </div>
            </div>
            <div className="flex gap-2 print:hidden">
              <Button onClick={handlePrint} variant="outline" size="sm">
                <Printer className="w-4 h-4 mr-2" />
                Print
              </Button>
              <Button onClick={handleDownloadPDF} variant="outline" size="sm">
                <Download className="w-4 h-4 mr-2" />
                PDF
              </Button>
              <Button onClick={onClose} variant="outline" size="sm">
                <X className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-8 space-y-6">
          {/* Guest and Stay Information */}
          <div className="grid grid-cols-2 gap-8">
            <div>
              <h2 className="text-lg font-bold mb-3 pb-2 border-b-2 border-gray-300">GUEST INFORMATION</h2>
              <div className="space-y-2 text-sm">
                <div>
                  <span className="font-semibold">Name:</span>
                  <div className="text-base">{guestData?.name || 'N/A'}</div>
                </div>
                <div>
                  <span className="font-semibold">Email:</span>
                  <div>{guestData?.email || 'N/A'}</div>
                </div>
                <div>
                  <span className="font-semibold">Phone:</span>
                  <div>{guestData?.phone || 'N/A'}</div>
                </div>
                <div>
                  <span className="font-semibold">ID Number:</span>
                  <div>{guestData?.id_number || 'N/A'}</div>
                </div>
                <div>
                  <span className="font-semibold">Nationality:</span>
                  <div>{guestData?.nationality || 'N/A'}</div>
                </div>
              </div>
            </div>

            <div>
              <h2 className="text-lg font-bold mb-3 pb-2 border-b-2 border-gray-300">STAY DETAILS</h2>
              <div className="space-y-2 text-sm">
                <div>
                  <span className="font-semibold">Room Number:</span>
                  <div className="text-2xl font-bold text-blue-600">{roomData?.room_number || 'N/A'}</div>
                </div>
                <div>
                  <span className="font-semibold">Room Type:</span>
                  <div>{roomData?.room_type || 'N/A'}</div>
                </div>
                <div>
                  <span className="font-semibold">Check-in:</span>
                  <div>{formatDate(folioData.booking.check_in)}</div>
                </div>
                <div>
                  <span className="font-semibold">Check-out:</span>
                  <div>{formatDate(folioData.booking.check_out)}</div>
                </div>
                <div>
                  <span className="font-semibold">Number of Nights:</span>
                  <div>
                    {(() => {
                      try {
                        const checkin = new Date(folioData.booking.check_in);
                        const checkout = new Date(folioData.booking.check_out);
                        return Math.ceil((checkout - checkin) / (1000 * 60 * 60 * 24));
                      } catch {
                        return 'N/A';
                      }
                    })()}
                  </div>
                </div>
                <div>
                  <span className="font-semibold">Guests:</span>
                  <div>{folioData.booking.adults || 0} Adult(s){folioData.booking.children > 0 && `, ${folioData.booking.children} Child(ren)`}</div>
                </div>
              </div>
            </div>
          </div>

          {/* Charges */}
          <div>
            <h2 className="text-lg font-bold mb-3 pb-2 border-b-2 border-gray-300">CHARGES</h2>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b-2 border-gray-400">
                  <th className="text-left py-2 font-semibold">Date</th>
                  <th className="text-left py-2 font-semibold">Description</th>
                  <th className="text-center py-2 font-semibold">Category</th>
                  <th className="text-right py-2 font-semibold">Qty</th>
                  <th className="text-right py-2 font-semibold">Unit Price</th>
                  <th className="text-right py-2 font-semibold">Amount</th>
                </tr>
              </thead>
              <tbody>
                {charges.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="text-center py-4 text-gray-500">No charges</td>
                  </tr>
                ) : (
                  charges.map((charge, idx) => (
                    <tr key={idx} className="border-b border-gray-200">
                      <td className="py-2">
                        {charge.posted_at ? formatDateTime(charge.posted_at).split(',')[0] : 'N/A'}
                      </td>
                      <td className="py-2">{charge.description}</td>
                      <td className="py-2 text-center">
                        <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs">
                          {charge.charge_category}
                        </span>
                      </td>
                      <td className="py-2 text-right">{charge.quantity || 1}</td>
                      <td className="py-2 text-right">${(charge.unit_price || charge.amount || 0).toFixed(2)}</td>
                      <td className="py-2 text-right font-semibold">${(charge.total || charge.amount || 0).toFixed(2)}</td>
                    </tr>
                  ))
                )}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-gray-400">
                  <td colSpan="5" className="py-2 text-right font-semibold">Subtotal:</td>
                  <td className="py-2 text-right font-semibold">${totalCharges.toFixed(2)}</td>
                </tr>
              </tfoot>
            </table>
          </div>

          {/* Payments */}
          <div>
            <h2 className="text-lg font-bold mb-3 pb-2 border-b-2 border-gray-300">PAYMENTS</h2>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b-2 border-gray-400">
                  <th className="text-left py-2 font-semibold">Date</th>
                  <th className="text-left py-2 font-semibold">Payment Method</th>
                  <th className="text-left py-2 font-semibold">Reference</th>
                  <th className="text-right py-2 font-semibold">Amount</th>
                </tr>
              </thead>
              <tbody>
                {payments.length === 0 ? (
                  <tr>
                    <td colSpan="4" className="text-center py-4 text-gray-500">No payments</td>
                  </tr>
                ) : (
                  payments.map((payment, idx) => (
                    <tr key={idx} className="border-b border-gray-200">
                      <td className="py-2">
                        {payment.posted_at ? formatDateTime(payment.posted_at).split(',')[0] : 'N/A'}
                      </td>
                      <td className="py-2">
                        <span className="px-2 py-1 bg-green-100 text-green-800 rounded text-xs">
                          {payment.payment_method}
                        </span>
                      </td>
                      <td className="py-2">{payment.reference || 'N/A'}</td>
                      <td className="py-2 text-right font-semibold text-green-600">
                        ${payment.amount.toFixed(2)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-gray-400">
                  <td colSpan="3" className="py-2 text-right font-semibold">Total Payments:</td>
                  <td className="py-2 text-right font-semibold text-green-600">${totalPayments.toFixed(2)}</td>
                </tr>
              </tfoot>
            </table>
          </div>

          {/* Summary */}
          <div className="border-t-4 border-gray-400 pt-4">
            <div className="grid grid-cols-2 gap-8">
              <div className="space-y-2 text-sm">
                <h3 className="font-bold mb-2">PAYMENT SUMMARY</h3>
                <div className="flex justify-between">
                  <span>Total Charges:</span>
                  <span className="font-semibold">${totalCharges.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span>Total Payments:</span>
                  <span className="font-semibold text-green-600">${totalPayments.toFixed(2)}</span>
                </div>
                <div className="flex justify-between pt-2 border-t-2 border-gray-300">
                  <span className="font-bold text-lg">Balance Due:</span>
                  <span className={`font-bold text-xl ${balance > 0 ? 'text-red-600' : 'text-green-600'}`}>
                    ${Math.abs(balance).toFixed(2)}
                  </span>
                </div>
                {balance <= 0 && (
                  <div className="mt-2 p-2 bg-green-100 text-green-800 rounded text-center font-semibold">
                    ✓ PAID IN FULL
                  </div>
                )}
              </div>

              <div className="text-xs text-gray-600 space-y-2">
                <h3 className="font-bold mb-2 text-sm">NOTES</h3>
                <p>• All prices are in USD unless otherwise stated</p>
                <p>• Tax is included in the total charges</p>
                <p>• Check-out time is 12:00 PM</p>
                <p>• Late check-out is subject to availability and charges</p>
                <p>• Please retain this folio for your records</p>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="border-t-2 border-gray-300 pt-6 mt-6">
            <div className="grid grid-cols-2 gap-8">
              <div>
                <div className="border-t-2 border-gray-400 pt-2 mt-16">
                  <p className="text-center font-semibold">Guest Signature</p>
                  <p className="text-center text-sm text-gray-600">
                    By signing, I acknowledge that all charges are correct
                  </p>
                </div>
              </div>
              <div>
                <div className="border-t-2 border-gray-400 pt-2 mt-16">
                  <p className="text-center font-semibold">Hotel Representative</p>
                  <p className="text-center text-sm text-gray-600">Date: {formatDate(new Date())}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Footer Note */}
          <div className="text-center text-xs text-gray-500 mt-6 pt-4 border-t border-gray-200">
            <p>Thank you for staying with us!</p>
            <p className="mt-1">This is a computer-generated document</p>
          </div>
        </CardContent>
      </Card>

      {/* Print-specific styles */}
      <style jsx>{`
        @media print {
          body * {
            visibility: hidden;
          }
          .fixed, .fixed * {
            visibility: visible;
          }
          .fixed {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: white;
          }
          button {
            display: none !important;
          }
          .print\\:hidden {
            display: none !important;
          }
        }
      `}</style>
    </div>
  );
};

export default PrintableFolio;
