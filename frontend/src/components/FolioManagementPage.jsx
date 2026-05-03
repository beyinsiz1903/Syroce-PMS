import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Search, FileText, CreditCard, Plus, DollarSign, Receipt, Eye, Printer } from 'lucide-react';
import RegistrationCard from './RegistrationCard';
import PrintableFolio from './PrintableFolio';

const FolioManagementPage = () => {
  const [folios, setFolios] = useState([]);
  const [selectedFolio, setSelectedFolio] = useState(null);
  const [charges, setCharges] = useState([]);
  const [payments, setPayments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [showChargeModal, setShowChargeModal] = useState(false);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [showRegistrationCard, setShowRegistrationCard] = useState(false);
  const [showPrintableFolio, setShowPrintableFolio] = useState(false);
  const [selectedBookingId, setSelectedBookingId] = useState(null);

  useEffect(() => {
    fetchAllFolios();
  }, []);

  useEffect(() => {
    if (selectedFolio) {
      fetchFolioDetails(selectedFolio.id);
    }
  }, [selectedFolio]);

  const fetchAllFolios = async () => {
    try {
      const token = localStorage.getItem('token');
      
      // Fetch all bookings to get folios
      const bookingsResponse = await fetch(
        `/api/pms/bookings`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );
      const bookingsData = await bookingsResponse.json();
      
      // Filter checked-in and checked-out bookings
      const activeBookings = bookingsData.bookings.filter(
        b => ['checked_in', 'checked_out'].includes(b.status)
      );
      
      // Create folio list
      const folioList = [];
      for (const booking of activeBookings.slice(0, 50)) {
        // Fetch guest info
        try {
          const guestResponse = await fetch(
            `/api/guests/${booking.guest_id}`,
            {
              headers: { 'Authorization': `Bearer ${token}` }
            }
          );
          const guestData = await guestResponse.json();
          
          // Get room info
          const roomsResponse = await fetch(
            `/api/pms/rooms`,
            {
              headers: { 'Authorization': `Bearer ${token}` }
            }
          );
          const roomsData = await roomsResponse.json();
          const room = roomsData.rooms.find(r => r.id === booking.room_id);
          
          folioList.push({
            id: booking.id,
            folio_number: `F-${booking.id.slice(0, 8).toUpperCase()}`,
            guest_name: guestData.guest?.name || 'Unknown',
            room_number: room?.room_number || 'N/A',
            status: booking.status,
            check_in: booking.check_in,
            check_out: booking.check_out,
            total_amount: booking.total_amount || 0,
            booking: booking
          });
        } catch (error) {
          console.error(`Error fetching details for booking ${booking.id}:`, error);
        }
      }
      
      setFolios(folioList);
    } catch (error) {
      console.error('Error fetching folios:', error);
    } finally {
      setLoading(false);
    }
  };

  const resolveFolioId = async (bookingId, token) => {
    const res = await fetch(`/api/folio/booking/${bookingId}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.ok) {
      const data = await res.json();
      const folioList = Array.isArray(data) ? data : [data];
      const openFolio = folioList.find(f => f.status === 'open') || folioList[0];
      return openFolio?.id || openFolio?.folio_id || null;
    }
    return null;
  };

  const fetchFolioDetails = async (bookingId) => {
    try {
      const token = localStorage.getItem('token');
      const folioId = await resolveFolioId(bookingId, token);

      if (folioId) {
        const detailRes = await fetch(`/api/folio/${folioId}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (detailRes.ok) {
          const folioData = await detailRes.json();
          setCharges(folioData.charges || []);
          setPayments(folioData.payments || []);
          return;
        }
      }

      const booking = folios.find(f => f.id === bookingId);
      if (booking) {
        const nights = Math.max(1, Math.ceil(
          (new Date(booking.check_out) - new Date(booking.check_in)) / (1000 * 60 * 60 * 24)
        ));
        const mockCharges = [];
        for (let i = 0; i < nights; i++) {
          mockCharges.push({
            description: `Room Charge - Night ${i + 1}`,
            charge_category: 'room',
            quantity: 1,
            unit_price: booking.total_amount / nights,
            amount: booking.total_amount / nights,
            tax_amount: (booking.total_amount / nights) * 0.18,
            total: (booking.total_amount / nights) * 1.18,
            posted_at: new Date(new Date(booking.check_in).getTime() + i * 24 * 60 * 60 * 1000).toISOString()
          });
        }
        setCharges(mockCharges);
        setPayments([]);
      }
    } catch (error) {
      console.error('Error fetching folio details:', error);
    }
  };

  const postCharge = async (chargeData) => {
    try {
      const token = localStorage.getItem('token');
      let folioId = await resolveFolioId(selectedFolio.id, token);

      if (!folioId) {
        const createRes = await fetch(`/api/folio/create`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
            'Idempotency-Key': `folio-${selectedFolio.id}-${Date.now()}`
          },
          body: JSON.stringify({
            booking_id: selectedFolio.id,
            folio_type: 'guest'
          })
        });
        if (!createRes.ok) throw new Error('Folio oluşturulamadı');
        const newFolio = await createRes.json();
        folioId = newFolio.id || newFolio.folio_id;
      }

      const chargeRes = await fetch(`/api/folio/${folioId}/charge`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(chargeData)
      });

      if (!chargeRes.ok) {
        const err = await chargeRes.json().catch(() => ({}));
        throw new Error(err.detail || 'Charge failed');
      }

      alert('Charge posted successfully');
      setShowChargeModal(false);
      fetchFolioDetails(selectedFolio.id);
    } catch (error) {
      console.error('Error posting charge:', error);
      alert('Masraf kaydedilemedi: ' + error.message);
    }
  };

  const postPayment = async (paymentData) => {
    try {
      const token = localStorage.getItem('token');
      const folioId = await resolveFolioId(selectedFolio.id, token);

      if (!folioId) throw new Error('Folio not found');

      const payRes = await fetch(`/api/folio/${folioId}/payment`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(paymentData)
      });

      if (!payRes.ok) {
        const err = await payRes.json().catch(() => ({}));
        throw new Error(err.detail || 'Payment failed');
      }

      alert('Payment posted successfully');
      setShowPaymentModal(false);
      fetchFolioDetails(selectedFolio.id);
    } catch (error) {
      console.error('Error posting payment:', error);
      alert('Ödeme kaydedilemedi: ' + error.message);
    }
  };

  const filteredFolios = folios.filter(f =>
    f.guest_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    f.room_number.toLowerCase().includes(searchTerm.toLowerCase()) ||
    f.folio_number.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const totalCharges = charges.reduce((sum, c) => sum + (c.total || 0), 0);
  const totalPayments = payments.reduce((sum, p) => sum + (p.amount || 0), 0);
  const balance = totalCharges - totalPayments;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Folio Management</h1>
          <p className="text-gray-600">Manage guest folios, charges, and payments</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Folio List */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Receipt className="w-5 h-5" />
              Active Folios
            </CardTitle>
            <div className="mt-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                <Input
                  placeholder="Search folios..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="text-center py-8">Loading...</div>
            ) : (
              <div className="space-y-2 max-h-[600px] overflow-y-auto">
                {filteredFolios.map((folio, idx) => (
                  <div
                    key={idx}
                    onClick={() => setSelectedFolio(folio)}
                    className={`p-3 border rounded-lg cursor-pointer transition-all ${
                      selectedFolio?.id === folio.id
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 hover:border-blue-300'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="font-semibold">{folio.guest_name}</div>
                        <div className="text-sm text-gray-600">
                          Room {folio.room_number}
                        </div>
                        <div className="text-xs text-gray-500">{folio.folio_number}</div>
                      </div>
                      <Badge className={folio.status === 'checked_in' ? 'bg-green-500' : 'bg-gray-500'}>
                        {folio.status}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Folio Details */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>
                {selectedFolio ? `Folio Details - ${selectedFolio.folio_number}` : 'Select a Folio'}
              </CardTitle>
              {selectedFolio && (
                <div className="flex gap-2">
                  <Button
                    onClick={() => {
                      setSelectedBookingId(selectedFolio.id);
                      setShowRegistrationCard(true);
                    }}
                    variant="outline"
                    size="sm"
                  >
                    <FileText className="w-4 h-4 mr-2" />
                    Registration Card
                  </Button>
                  <Button
                    onClick={() => setShowPrintableFolio(true)}
                    variant="outline"
                    size="sm"
                  >
                    <Printer className="w-4 h-4 mr-2" />
                    Print Folio
                  </Button>
                  <Button onClick={() => setShowChargeModal(true)} size="sm">
                    <Plus className="w-4 h-4 mr-2" />
                    Add Charge
                  </Button>
                  <Button onClick={() => setShowPaymentModal(true)} size="sm" variant="outline">
                    <CreditCard className="w-4 h-4 mr-2" />
                    Add Payment
                  </Button>
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {!selectedFolio ? (
              <div className="text-center py-16 text-gray-500">
                <Receipt className="w-16 h-16 mx-auto mb-4 text-gray-400" />
                <p>Select a folio from the list to view details</p>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Summary Cards */}
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-blue-50 p-4 rounded-lg">
                    <div className="text-sm text-gray-600">Total Charges</div>
                    <div className="text-2xl font-bold text-blue-600">
                      ${totalCharges.toFixed(2)}
                    </div>
                  </div>
                  <div className="bg-green-50 p-4 rounded-lg">
                    <div className="text-sm text-gray-600">Total Payments</div>
                    <div className="text-2xl font-bold text-green-600">
                      ${totalPayments.toFixed(2)}
                    </div>
                  </div>
                  <div className={`p-4 rounded-lg ${balance > 0 ? 'bg-red-50' : 'bg-gray-50'}`}>
                    <div className="text-sm text-gray-600">Balance</div>
                    <div className={`text-2xl font-bold ${balance > 0 ? 'text-red-600' : 'text-green-600'}`}>
                      ${Math.abs(balance).toFixed(2)}
                    </div>
                  </div>
                </div>

                {/* Charges */}
                <div>
                  <h3 className="text-lg font-semibold mb-3">Charges</h3>
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="p-3 text-left text-sm font-medium">Date</th>
                          <th className="p-3 text-left text-sm font-medium">Description</th>
                          <th className="p-3 text-left text-sm font-medium">Category</th>
                          <th className="p-3 text-right text-sm font-medium">Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {charges.length === 0 ? (
                          <tr>
                            <td colSpan="4" className="p-6 text-center text-gray-500">
                              No charges posted
                            </td>
                          </tr>
                        ) : (
                          charges.map((charge, idx) => (
                            <tr key={idx} className="border-t">
                              <td className="p-3 text-sm">
                                {charge.posted_at ? new Date(charge.posted_at).toLocaleDateString() : 'N/A'}
                              </td>
                              <td className="p-3 text-sm">{charge.description}</td>
                              <td className="p-3">
                                <Badge variant="outline">{charge.charge_category}</Badge>
                              </td>
                              <td className="p-3 text-right font-semibold">
                                ${(charge.total || charge.amount || 0).toFixed(2)}
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Payments */}
                <div>
                  <h3 className="text-lg font-semibold mb-3">Payments</h3>
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="p-3 text-left text-sm font-medium">Date</th>
                          <th className="p-3 text-left text-sm font-medium">Method</th>
                          <th className="p-3 text-left text-sm font-medium">Reference</th>
                          <th className="p-3 text-right text-sm font-medium">Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {payments.length === 0 ? (
                          <tr>
                            <td colSpan="4" className="p-6 text-center text-gray-500">
                              No payments received
                            </td>
                          </tr>
                        ) : (
                          payments.map((payment, idx) => (
                            <tr key={idx} className="border-t">
                              <td className="p-3 text-sm">
                                {payment.posted_at ? new Date(payment.posted_at).toLocaleDateString() : 'N/A'}
                              </td>
                              <td className="p-3">
                                <Badge className="bg-green-100 text-green-800">
                                  {payment.payment_method}
                                </Badge>
                              </td>
                              <td className="p-3 text-sm">{payment.reference || 'N/A'}</td>
                              <td className="p-3 text-right font-semibold text-green-600">
                                ${payment.amount.toFixed(2)}
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Charge Modal */}
      {showChargeModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle>Post Charge</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={(e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                postCharge({
                  description: formData.get('description'),
                  charge_category: formData.get('category'),
                  quantity: parseInt(formData.get('quantity')),
                  amount: parseFloat(formData.get('unit_price'))
                });
              }}>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium mb-2">Description</label>
                    <Input name="description" required />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">Category</label>
                    <Select name="category" required>
                      <SelectTrigger>
                        <SelectValue placeholder="Select category" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="room">Room</SelectItem>
                        <SelectItem value="food">Food</SelectItem>
                        <SelectItem value="beverage">Beverage</SelectItem>
                        <SelectItem value="minibar">Mini-bar</SelectItem>
                        <SelectItem value="laundry">Laundry</SelectItem>
                        <SelectItem value="spa">Spa</SelectItem>
                        <SelectItem value="other">Other</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium mb-2">Quantity</label>
                      <Input name="quantity" type="number" defaultValue="1" min="1" required />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2">Unit Price</label>
                      <Input name="unit_price" type="number" step="0.01" required />
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button type="submit" className="flex-1">Post Charge</Button>
                    <Button type="button" variant="outline" onClick={() => setShowChargeModal(false)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Payment Modal */}
      {showPaymentModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle>Post Payment</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={(e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                postPayment({
                  method: formData.get('method'),
                  payment_type: formData.get('payment_type'),
                  amount: parseFloat(formData.get('amount')),
                  reference: formData.get('reference') || null
                });
              }}>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium mb-2">Payment Method</label>
                    <Select name="method" required>
                      <SelectTrigger>
                        <SelectValue placeholder="Select method" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="cash">Cash</SelectItem>
                        <SelectItem value="card">Credit/Debit Card</SelectItem>
                        <SelectItem value="bank_transfer">Bank Transfer</SelectItem>
                        <SelectItem value="online">Online</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">Payment Type</label>
                    <Select name="payment_type" required>
                      <SelectTrigger>
                        <SelectValue placeholder="Select type" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="prepayment">Prepayment</SelectItem>
                        <SelectItem value="deposit">Deposit</SelectItem>
                        <SelectItem value="interim">Interim</SelectItem>
                        <SelectItem value="final">Final</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">Amount</label>
                    <Input name="amount" type="number" step="0.01" required />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">Reference Number</label>
                    <Input name="reference" placeholder="Optional" />
                  </div>
                  <div className="flex gap-2">
                    <Button type="submit" className="flex-1">Post Payment</Button>
                    <Button type="button" variant="outline" onClick={() => setShowPaymentModal(false)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Registration Card Modal */}
      {showRegistrationCard && selectedBookingId && (
        <RegistrationCard
          bookingId={selectedBookingId}
          onClose={() => {
            setShowRegistrationCard(false);
            setSelectedBookingId(null);
          }}
        />
      )}

      {/* Printable Folio Modal */}
      {showPrintableFolio && selectedFolio && (
        <PrintableFolio
          folioData={{
            folio_number: selectedFolio.folio_number,
            booking: selectedFolio.booking,
            charges: charges,
            payments: payments
          }}
          onClose={() => setShowPrintableFolio(false)}
        />
      )}
    </div>
  );
};

export default FolioManagementPage;
