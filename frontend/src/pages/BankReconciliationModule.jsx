import React, { useState, useEffect } from 'react';
import { RefreshCw, Landmark, FileText, CheckCircle, AlertCircle } from 'lucide-react';
import axios from 'axios';

// Varsayılan açık faturalar (Cari hesaplar) - Mock data
const mockPendingInvoices = [
  { id: 'inv-1', number: 'INV-2026-001', clientName: 'Booking.com B.V.', amount: 15000.00, status: 'pending' },
  { id: 'inv-2', number: 'INV-2026-002', clientName: 'Expedia Inc.', amount: 8400.00, status: 'pending' },
  { id: 'inv-3', number: 'FOL-8493', clientName: 'Ahmet Yılmaz', amount: 2450.50, status: 'pending' },
  { id: 'inv-4', number: 'INV-2026-003', clientName: 'Jolly Tur', amount: 35000.00, status: 'pending' },
];

export default function BankReconciliationModule() {
  const [transactions, setTransactions] = useState([]);
  const [invoices, setInvoices] = useState(mockPendingInvoices);
  const [loading, setLoading] = useState(true);
  
  const [selectedTxn, setSelectedTxn] = useState(null);
  const [selectedInvoice, setSelectedInvoice] = useState(null);
  
  const [confirmDialog, setConfirmDialog] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [alertMsg, setAlertMsg] = useState(null);

  useEffect(() => {
    fetchTransactions();
  }, []);

  const fetchTransactions = async () => {
    try {
      setLoading(true);
      const res = await axios.get('/banking/transactions');
      setTransactions(res.data);
    } catch (err) {
      console.error('Banka hareketleri alınamadı', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSyncBank = async () => {
    try {
      setLoading(true);
      const res = await axios.post('/banking/sync');
      if (res.data?.status === 'success') {
        fetchTransactions();
      }
    } catch (err) {
      console.error('Banka entegrasyonu hatası', err);
    } finally {
      setLoading(false);
    }
  };

  const handleReconcile = async () => {
    if (!selectedTxn || !selectedInvoice) return;
    
    try {
      setReconciling(true);
      await axios.post('/banking/reconcile', {
        transaction_id: selectedTxn.id,
        invoice_id: selectedInvoice.id,
        invoice_number: selectedInvoice.number,
        amount_paid: selectedTxn.amount,
        client_name: selectedInvoice.clientName
      });
      
      setAlertMsg({ type: 'success', text: `Mutabakat başarılı! ${selectedInvoice.number} kapatıldı ve Yevmiye Fişi kesildi.` });
      
      // Remove or mark matched on client side
      setTransactions(prev => prev.map(t => t.id === selectedTxn.id ? { ...t, status: 'matched', matched_with: selectedInvoice.number } : t));
      setInvoices(prev => prev.filter(i => i.id !== selectedInvoice.id));
      
      setSelectedTxn(null);
      setSelectedInvoice(null);
      setConfirmDialog(false);
    } catch (err) {
      setAlertMsg({ type: 'error', text: err.response?.data?.detail || 'Mutabakat işlemi başarısız oldu.' });
    } finally {
      setReconciling(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Açık Bankacılık & Mutabakat</h1>
        <button 
          onClick={handleSyncBank}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Bankadan Çek (Simülasyon)
        </button>
      </div>

      {alertMsg && (
        <div className={`p-4 mb-6 rounded-md flex items-center justify-between ${alertMsg.type === 'success' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'}`}>
          <div className="flex items-center gap-2">
            {alertMsg.type === 'error' ? <AlertCircle className="w-5 h-5" /> : <CheckCircle className="w-5 h-5" />}
            <span>{alertMsg.text}</span>
          </div>
          <button onClick={() => setAlertMsg(null)} className="text-gray-500 hover:text-gray-700">✕</button>
        </div>
      )}

      {/* Reconcile Action Bar */}
      {(selectedTxn || selectedInvoice) && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex flex-col md:flex-row md:items-center gap-4 text-sm">
            <div>
              <strong className="text-gray-700">Seçili Banka İşlemi:</strong><br />
              {selectedTxn ? `${selectedTxn.amount.toLocaleString('tr-TR')} ₺ (${selectedTxn.sender_name})` : <span className="text-gray-500">Bekleniyor...</span>}
            </div>
            <div className="hidden md:block text-2xl text-blue-300">↔</div>
            <div>
              <strong className="text-gray-700">Seçili Fatura/Cari:</strong><br />
              {selectedInvoice ? `${selectedInvoice.number} - ${selectedInvoice.amount.toLocaleString('tr-TR')} ₺` : <span className="text-gray-500">Bekleniyor...</span>}
            </div>
          </div>
          
          <button 
            onClick={() => setConfirmDialog(true)}
            disabled={!selectedTxn || !selectedInvoice}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 whitespace-nowrap"
          >
            <CheckCircle className="w-4 h-4" />
            Eşleştir (Reconcile)
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Sol Taraf: Banka Hareketleri */}
        <div className="bg-white border rounded-lg shadow-sm flex flex-col">
          <div className="p-4 border-b flex items-center gap-2 bg-gray-50 rounded-t-lg">
            <Landmark className="w-5 h-5 text-blue-600" />
            <h2 className="text-lg font-bold text-gray-800">Banka Hesap Hareketleri</h2>
          </div>
          <div className="flex-1 overflow-auto p-0">
            {loading ? (
              <div className="p-8 flex justify-center">
                <RefreshCw className="w-8 h-8 text-blue-500 animate-spin" />
              </div>
            ) : (
              <ul className="divide-y">
                {transactions.map((txn) => {
                  const isMatched = txn.status === 'matched';
                  const isSelected = selectedTxn?.id === txn.id;
                  return (
                    <li 
                      key={txn.id}
                      onClick={() => !isMatched && setSelectedTxn(txn)}
                      className={`p-4 cursor-pointer transition-colors ${
                        isMatched ? 'opacity-60 bg-gray-50 cursor-not-allowed' : 
                        isSelected ? 'bg-blue-50 border-l-4 border-blue-500' : 'hover:bg-gray-50 border-l-4 border-transparent'
                      }`}
                    >
                      <div className="flex justify-between items-start mb-1">
                        <span className="font-bold text-gray-900">{txn.sender_name}</span>
                        <span className="font-bold text-green-600">+{txn.amount.toLocaleString('tr-TR')} ₺</span>
                      </div>
                      <div className="text-sm text-gray-600 mb-2">{txn.description}</div>
                      <div className="flex justify-between items-center text-xs">
                        <span className="text-gray-400">{txn.date} | IBAN: {txn.sender_iban}</span>
                        {isMatched ? (
                          <span className="px-2 py-1 bg-green-100 text-green-800 rounded text-[10px] font-medium border border-green-200">
                            Eşleşti: {txn.matched_with}
                          </span>
                        ) : (
                          <span className="px-2 py-1 bg-orange-100 text-orange-800 rounded text-[10px] font-medium">
                            Eşleşme Bekliyor
                          </span>
                        )}
                      </div>
                    </li>
                  );
                })}
                {transactions.length === 0 && (
                  <div className="p-8 text-center text-gray-500">Banka hareketi bulunmuyor.</div>
                )}
              </ul>
            )}
          </div>
        </div>

        {/* Sağ Taraf: PMS Faturalar / Cari */}
        <div className="bg-white border rounded-lg shadow-sm flex flex-col">
          <div className="p-4 border-b flex items-center gap-2 bg-gray-50 rounded-t-lg">
            <FileText className="w-5 h-5 text-purple-600" />
            <h2 className="text-lg font-bold text-gray-800">Açık Faturalar & Cari (PMS)</h2>
          </div>
          <div className="flex-1 overflow-auto p-0">
            <ul className="divide-y">
              {invoices.map((inv) => {
                const isSelected = selectedInvoice?.id === inv.id;
                return (
                  <li 
                    key={inv.id}
                    onClick={() => setSelectedInvoice(inv)}
                    className={`p-4 cursor-pointer transition-colors ${
                      isSelected ? 'bg-purple-50 border-l-4 border-purple-500' : 'hover:bg-gray-50 border-l-4 border-transparent'
                    }`}
                  >
                    <div className="flex justify-between items-start mb-1">
                      <span className="font-bold text-gray-900">{inv.clientName}</span>
                      <span className="font-bold text-red-600">{inv.amount.toLocaleString('tr-TR')} ₺</span>
                    </div>
                    <div className="flex justify-between items-center text-xs mt-2">
                      <span className="text-gray-600">Belge No: {inv.number}</span>
                      <span className="px-2 py-1 bg-red-50 text-red-700 rounded text-[10px] font-medium border border-red-200">
                        Açık Cari
                      </span>
                    </div>
                  </li>
                );
              })}
              {invoices.length === 0 && (
                <div className="p-8 text-center text-gray-500">Açık fatura kalmadı.</div>
              )}
            </ul>
          </div>
        </div>
      </div>

      {/* Confirmation Dialog */}
      {confirmDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <div className="bg-white rounded-lg shadow-lg w-full max-w-lg overflow-hidden">
            <div className="p-4 border-b">
              <h3 className="text-lg font-bold">Mutabakat Onayı</h3>
            </div>
            <div className="p-4">
              <p className="mb-4 text-sm text-gray-700">
                Aşağıdaki eşleştirmeyi onaylıyor musunuz? Onayladıktan sonra sistem otomatik olarak tahsilat yevmiye fişini (102 / 120) kesecektir.
              </p>
              <div className="bg-gray-50 p-3 rounded-md mb-4 text-sm">
                <div className="mb-1"><strong>Gelen Para:</strong> {selectedTxn?.amount?.toLocaleString('tr-TR')} ₺ ({selectedTxn?.sender_name})</div>
                <div><strong>Fatura Borcu:</strong> {selectedInvoice?.amount?.toLocaleString('tr-TR')} ₺ ({selectedInvoice?.number})</div>
              </div>
              {selectedTxn?.amount !== selectedInvoice?.amount && (
                <div className="bg-orange-50 border border-orange-200 text-orange-800 p-3 rounded text-sm flex gap-2">
                  <AlertCircle className="w-5 h-5 shrink-0" />
                  <p>Dikkat: Gelen tutar ile fatura tutarı eşleşmiyor! Kalan bakiye cari hesaba işlenecektir (Kısmi tahsilat).</p>
                </div>
              )}
            </div>
            <div className="p-4 border-t flex justify-end gap-2 bg-gray-50">
              <button 
                onClick={() => setConfirmDialog(false)} 
                disabled={reconciling}
                className="px-4 py-2 bg-white border rounded hover:bg-gray-100 disabled:opacity-50"
              >
                İptal
              </button>
              <button 
                onClick={handleReconcile} 
                disabled={reconciling}
                className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 flex items-center gap-2"
              >
                {reconciling ? <RefreshCw className="w-4 h-4 animate-spin" /> : 'Onayla ve Fiş Kes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
