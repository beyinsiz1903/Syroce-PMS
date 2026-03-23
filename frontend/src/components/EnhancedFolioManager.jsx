import React, { useState, useEffect } from 'react';
import axios from 'axios';
import SplitFolioDialog from './SplitFolioDialog';

const API_URL = import.meta.env.VITE_BACKEND_URL || '';

const EnhancedFolioManager = ({ bookingId }) => {
  const [folio, setFolio] = useState(null);
  const [charges, setCharges] = useState([]);
  const [payments, setPayments] = useState([]);
  const [showChargeModal, setShowChargeModal] = useState(false);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [showSplitModal, setShowSplitModal] = useState(false);

  useEffect(() => {
    if (bookingId) {
      fetchFolio();
    }
  }, [bookingId]);

  const fetchFolio = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(
        `${API_URL}/api/folio/${bookingId}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setFolio(response.data.folio);
      setCharges(response.data.charges || []);
      setPayments(response.data.payments || []);
    } catch (error) {
      console.error('Error fetching folio:', error);
    }
  };

  const postCharge = async (chargeData) => {
    try {
      const token = localStorage.getItem('token');
      await axios.post(
        `${API_URL}/api/folio/charge`,
        { ...chargeData, folio_id: folio.id },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      alert('Charge posted successfully');
      setShowChargeModal(false);
      fetchFolio();
    } catch (error) {
      console.error('Error posting charge:', error);
      alert('Failed to post charge');
    }
  };

  const postPayment = async (paymentData) => {
    try {
      const token = localStorage.getItem('token');
      await axios.post(
        `${API_URL}/api/folio/payment`,
        { ...paymentData, folio_id: folio.id },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      alert('Payment posted successfully');
      setShowPaymentModal(false);
      fetchFolio();
    } catch (error) {
      console.error('Error posting payment:', error);
      alert('Failed to post payment');
    }
  };

  const handleCheckout = async () => {
    if (!window.confirm('Are you sure you want to checkout this guest?')) return;
    
    try {
      const token = localStorage.getItem('token');
      await axios.post(
        `${API_URL}/api/bookings/${bookingId}/checkout`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      alert('Guest checked out successfully');
      fetchFolio();
    } catch (error) {
      console.error('Error checking out:', error);
      alert('Failed to checkout');
    }
  };

  if (!folio) {
    return (
      <div className="p-6 bg-white">
        <p>Loading folio...</p>
      </div>
    );
  }

  return (
    <div className="p-6 bg-white">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">Folio - {folio.folio_number}</h1>
        <div className="flex gap-4">
          <button
            onClick={() => setShowChargeModal(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            ➕ Post Charge
          </button>
          <button
            onClick={() => setShowPaymentModal(true)}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
          >
            💳 Post Payment
          </button>
          <button
            onClick={() => setShowSplitModal(true)}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
            disabled={folio.status !== 'open'}
          >
            ✂️ Split Folio
          </button>
          <button
            onClick={handleCheckout}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
          >
            🚪 Checkout
          </button>
        </div>
      </div>

      {/* Folio Summary */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-blue-50 p-4 rounded-lg">
          <div className="text-sm text-gray-600">Total Charges</div>
          <div className="text-2xl font-bold text-blue-600">
            ${charges.reduce((sum, c) => sum + c.total, 0).toFixed(2)}
          </div>
        </div>
        <div className="bg-green-50 p-4 rounded-lg">
          <div className="text-sm text-gray-600">Total Payments</div>
          <div className="text-2xl font-bold text-green-600">
            ${payments.reduce((sum, p) => sum + p.amount, 0).toFixed(2)}
          </div>
        </div>
        <div className={`p-4 rounded-lg ${folio.balance < 0 ? 'bg-red-50' : 'bg-gray-50'}`}>
          <div className="text-sm text-gray-600">Balance</div>
          <div className={`text-2xl font-bold ${folio.balance < 0 ? 'text-red-600' : 'text-gray-800'}`}>
            ${Math.abs(folio.balance).toFixed(2)}
          </div>
        </div>
      </div>

      {/* Charges Table */}
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-4">Charges</h2>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-gray-100">
                <th className="p-3 text-left">Date</th>
                <th className="p-3 text-left">Description</th>
                <th className="p-3 text-left">Category</th>
                <th className="p-3 text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {charges.map((charge, idx) => (
                <tr key={idx} className="border-b hover:bg-gray-50">
                  <td className="p-3">{charge.date}</td>
                  <td className="p-3">{charge.description}</td>
                  <td className="p-3">
                    <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-sm">
                      {charge.charge_category}
                    </span>
                  </td>
                  <td className="p-3 text-right font-semibold">${charge.total.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Payments Table */}
      <div>
        <h2 className="text-xl font-semibold mb-4">Payments</h2>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-gray-100">
                <th className="p-3 text-left">Date</th>
                <th className="p-3 text-left">Method</th>
                <th className="p-3 text-left">Reference</th>
                <th className="p-3 text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {payments.map((payment, idx) => (
                <tr key={idx} className="border-b hover:bg-gray-50">
                  <td className="p-3">{payment.date}</td>
                  <td className="p-3">
                    <span className="px-2 py-1 bg-green-100 text-green-800 rounded text-sm">
                      {payment.payment_method}
                    </span>
                  </td>
                  <td className="p-3">{payment.reference_number}</td>
                  <td className="p-3 text-right font-semibold text-green-600">${payment.amount.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Charge Modal */}
      {showChargeModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-[500px]">
            <h3 className="text-xl font-bold mb-4">Post Charge</h3>
            <form onSubmit={(e) => {
              e.preventDefault();
              const formData = new FormData(e.target);
              postCharge({
                description: formData.get('description'),
                charge_category: formData.get('category'),
                quantity: parseInt(formData.get('quantity')),
                unit_price: parseFloat(formData.get('unit_price'))
              });
            }}>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-2">Description</label>
                <input type="text" name="description" required className="w-full px-4 py-2 border rounded-lg" />
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-2">Category</label>
                <select name="category" required className="w-full px-4 py-2 border rounded-lg">
                  <option value="room">Room</option>
                  <option value="food">Food</option>
                  <option value="beverage">Beverage</option>
                  <option value="minibar">Mini-bar</option>
                  <option value="laundry">Laundry</option>
                  <option value="spa">Spa</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Quantity</label>
                  <input type="number" name="quantity" defaultValue="1" min="1" required className="w-full px-4 py-2 border rounded-lg" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Unit Price</label>
                  <input type="number" name="unit_price" step="0.01" required className="w-full px-4 py-2 border rounded-lg" />
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setShowChargeModal(false)} className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300">Cancel</button>
                <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">Post Charge</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Payment Modal */}
      {showPaymentModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-[500px]">
            <h3 className="text-xl font-bold mb-4">Post Payment</h3>
            <form onSubmit={(e) => {
              e.preventDefault();
              const formData = new FormData(e.target);
              postPayment({
                payment_method: formData.get('method'),
                amount: parseFloat(formData.get('amount')),
                reference_number: formData.get('reference')
              });
            }}>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-2">Payment Method</label>
                <select name="method" required className="w-full px-4 py-2 border rounded-lg">
                  <option value="cash">Cash</option>
                  <option value="credit_card">Credit Card</option>
                  <option value="debit_card">Debit Card</option>
                  <option value="bank_transfer">Bank Transfer</option>
                  <option value="mobile_payment">Mobile Payment</option>
                </select>
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-2">Amount</label>
                <input type="number" name="amount" step="0.01" required className="w-full px-4 py-2 border rounded-lg" placeholder="0.00" />
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-2">Reference Number</label>
                <input type="text" name="reference" className="w-full px-4 py-2 border rounded-lg" placeholder="Optional" />
              </div>
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setShowPaymentModal(false)} className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300">Cancel</button>
                <button type="submit" className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700">Post Payment</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Split Folio Modal */}
      {showSplitModal && folio && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="max-w-4xl w-full">
            <SplitFolioDialog
              folio={folio}
              onClose={() => setShowSplitModal(false)}
              onSuccess={() => {
                setShowSplitModal(false);
                fetchFolio();
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default EnhancedFolioManager;
