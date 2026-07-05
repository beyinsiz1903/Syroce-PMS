import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Button,
  List,
  ListItem,
  ListItemText,
  Divider,
  Chip,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Alert,
} from '@mui/material';
import { Sync as SyncIcon, AccountBalance as BankIcon, Receipt as InvoiceIcon, CheckCircle as CheckIcon } from '@mui/icons-material';
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
      const res = await axios.get('/api/finance/banking/transactions');
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
      const res = await axios.post('/api/finance/banking/sync');
      if (res.data.status === 'success') {
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
      await axios.post('/api/finance/banking/reconcile', {
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
    <Box sx={{ p: 3, maxWidth: 1400, margin: '0 auto' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" fontWeight="bold">
          Açık Bankacılık & Mutabakat
        </Typography>
        <Button 
          variant="contained" 
          startIcon={<SyncIcon />} 
          onClick={handleSyncBank}
          disabled={loading}
          sx={{ borderRadius: 2, textTransform: 'none' }}
        >
          Bankadan Çek (Simülasyon)
        </Button>
      </Box>

      {alertMsg && (
        <Alert severity={alertMsg.type} sx={{ mb: 3 }} onClose={() => setAlertMsg(null)}>
          {alertMsg.text}
        </Alert>
      )}

      {/* Reconcile Action Bar */}
      {(selectedTxn || selectedInvoice) && (
        <Card sx={{ mb: 3, bgcolor: '#e3f2fd', border: '1px solid #90caf9' }}>
          <CardContent sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Box sx={{ display: 'flex', gap: 3, alignItems: 'center' }}>
              <Typography variant="body1">
                <strong>Seçili Banka İşlemi:</strong> {selectedTxn ? `${selectedTxn.amount} ₺ (${selectedTxn.sender_name})` : 'Bekleniyor...'}
              </Typography>
              <Typography variant="h6" color="text.secondary">↔</Typography>
              <Typography variant="body1">
                <strong>Seçili Fatura/Cari:</strong> {selectedInvoice ? `${selectedInvoice.number} - ${selectedInvoice.amount} ₺` : 'Bekleniyor...'}
              </Typography>
            </Box>
            
            <Button 
              variant="contained" 
              color="success" 
              disabled={!selectedTxn || !selectedInvoice}
              onClick={() => setConfirmDialog(true)}
              startIcon={<CheckIcon />}
            >
              Eşleştir (Reconcile)
            </Button>
          </CardContent>
        </Card>
      )}

      <Grid container spacing={4}>
        {/* Sol Taraf: Banka Hareketleri */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%', borderRadius: 3, boxShadow: '0 4px 12px rgba(0,0,0,0.05)' }}>
            <Box sx={{ p: 2, borderBottom: '1px solid #eee', display: 'flex', alignItems: 'center', gap: 1 }}>
              <BankIcon color="primary" />
              <Typography variant="h6" fontWeight="bold">Banka Hesap Hareketleri</Typography>
            </Box>
            <CardContent sx={{ p: 0 }}>
              {loading ? (
                <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>
              ) : (
                <List sx={{ p: 0 }}>
                  {transactions.map((txn, index) => (
                    <React.Fragment key={txn.id}>
                      <ListItem 
                        button 
                        onClick={() => txn.status === 'unmatched' && setSelectedTxn(txn)}
                        selected={selectedTxn?.id === txn.id}
                        disabled={txn.status === 'matched'}
                        sx={{ 
                          p: 2, 
                          transition: '0.2s',
                          '&.Mui-selected': { bgcolor: 'primary.light', '&:hover': { bgcolor: 'primary.light' } },
                          opacity: txn.status === 'matched' ? 0.6 : 1
                        }}
                      >
                        <ListItemText 
                          primary={
                            <Box display="flex" justifyContent="space-between">
                              <Typography variant="subtitle1" fontWeight="bold">{txn.sender_name}</Typography>
                              <Typography variant="subtitle1" fontWeight="bold" color="success.main">+{txn.amount.toLocaleString('tr-TR')} ₺</Typography>
                            </Box>
                          }
                          secondary={
                            <Box display="flex" flexDirection="column" gap={0.5} mt={0.5}>
                              <Typography variant="body2" color="text.secondary">{txn.description}</Typography>
                              <Box display="flex" justifyContent="space-between" alignItems="center">
                                <Typography variant="caption" color="text.disabled">{txn.date} | IBAN: {txn.sender_iban}</Typography>
                                {txn.status === 'matched' ? (
                                  <Chip size="small" label={`Eşleşti: ${txn.matched_with}`} color="success" variant="outlined" />
                                ) : (
                                  <Chip size="small" label="Eşleşme Bekliyor" color="warning" />
                                )}
                              </Box>
                            </Box>
                          }
                        />
                      </ListItem>
                      {index < transactions.length - 1 && <Divider />}
                    </React.Fragment>
                  ))}
                  {transactions.length === 0 && (
                    <Typography variant="body2" sx={{ p: 3, textAlign: 'center', color: 'text.secondary' }}>
                      Banka hareketi bulunmuyor.
                    </Typography>
                  )}
                </List>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Sağ Taraf: PMS Faturalar / Cari */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%', borderRadius: 3, boxShadow: '0 4px 12px rgba(0,0,0,0.05)' }}>
            <Box sx={{ p: 2, borderBottom: '1px solid #eee', display: 'flex', alignItems: 'center', gap: 1 }}>
              <InvoiceIcon color="secondary" />
              <Typography variant="h6" fontWeight="bold">Açık Faturalar & Cari (PMS)</Typography>
            </Box>
            <CardContent sx={{ p: 0 }}>
              <List sx={{ p: 0 }}>
                {invoices.map((inv, index) => (
                  <React.Fragment key={inv.id}>
                    <ListItem 
                      button 
                      onClick={() => setSelectedInvoice(inv)}
                      selected={selectedInvoice?.id === inv.id}
                      sx={{ 
                        p: 2,
                        transition: '0.2s',
                        '&.Mui-selected': { bgcolor: 'secondary.light', '&:hover': { bgcolor: 'secondary.light' } }
                      }}
                    >
                      <ListItemText 
                        primary={
                          <Box display="flex" justifyContent="space-between">
                            <Typography variant="subtitle1" fontWeight="bold">{inv.clientName}</Typography>
                            <Typography variant="subtitle1" fontWeight="bold" color="error.main">{inv.amount.toLocaleString('tr-TR')} ₺</Typography>
                          </Box>
                        }
                        secondary={
                          <Box display="flex" justifyContent="space-between" mt={0.5}>
                            <Typography variant="body2" color="text.secondary">Belge No: {inv.number}</Typography>
                            <Chip size="small" label="Açık Cari" color="error" variant="outlined" />
                          </Box>
                        }
                      />
                    </ListItem>
                    {index < invoices.length - 1 && <Divider />}
                  </React.Fragment>
                ))}
                {invoices.length === 0 && (
                  <Typography variant="body2" sx={{ p: 3, textAlign: 'center', color: 'text.secondary' }}>
                    Açık fatura kalmadı.
                  </Typography>
                )}
              </List>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Confirmation Dialog */}
      <Dialog open={confirmDialog} onClose={() => !reconciling && setConfirmDialog(false)}>
        <DialogTitle>Mutabakat Onayı</DialogTitle>
        <DialogContent>
          <Typography variant="body1" mb={2}>
            Aşağıdaki eşleştirmeyi onaylıyor musunuz? Onayladıktan sonra sistem otomatik olarak tahsilat yevmiye fişini (102 / 120) kesecektir.
          </Typography>
          <Box sx={{ bgcolor: '#f5f5f5', p: 2, borderRadius: 1 }}>
            <Typography variant="body2"><strong>Gelen Para:</strong> {selectedTxn?.amount} ₺ ({selectedTxn?.sender_name})</Typography>
            <Typography variant="body2"><strong>Fatura Borcu:</strong> {selectedInvoice?.amount} ₺ ({selectedInvoice?.number})</Typography>
          </Box>
          {selectedTxn?.amount !== selectedInvoice?.amount && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              Dikkat: Gelen tutar ile fatura tutarı eşleşmiyor! Kalan bakiye cari hesaba işlenecektir (Kısmi tahsilat).
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDialog(false)} disabled={reconciling}>İptal</Button>
          <Button onClick={handleReconcile} variant="contained" color="success" disabled={reconciling}>
            {reconciling ? <CircularProgress size={24} /> : 'Onayla ve Fiş Kes'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
