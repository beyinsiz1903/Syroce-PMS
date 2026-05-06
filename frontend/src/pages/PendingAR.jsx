import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { 
  Building2,
  DollarSign,
  AlertCircle,
  Clock,
  Search,
  Download,
  Mail,
  Phone
} from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useTranslation } from 'react-i18next';

const PendingAR = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [arData, setArData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterDays, setFilterDays] = useState('all');

  const [agingData, setAgingData] = useState(null);
  const [agingLoading, setAgingLoading] = useState(true);
  const [selectedAccount, setSelectedAccount] = useState(null);
  const [accountStatement, setAccountStatement] = useState(null);
  const [statementLoading, setStatementLoading] = useState(false);

  useEffect(() => {
    loadARData();
    loadAgingData();
  }, []);

  const loadARData = async () => {
    setLoading(true);
    try {
      // Prefer backend aggregated AR endpoint
      const response = await axios.get('/folio/pending-ar');
      setArData(response.data || []);
    } catch (error) {
      console.error('Failed to load AR data:', error);
      // Fallback: try to get from companies and calculate
      try {
        const companiesRes = await axios.get('/companies');
        const companies = companiesRes.data || [];
        
        // For each company, get their folios and calculate outstanding balance
        const arPromises = companies.map(async (company) => {
          try {
            const foliosRes = await axios.get(`/folio/booking/company/${company.id}`);
            const folios = foliosRes.data || [];
            
            const totalOutstanding = folios.reduce((sum, folio) => {
              if (folio.status === 'open' && folio.balance > 0) {
                return sum + folio.balance;
              }
              return sum;
            }, 0);

            if (totalOutstanding > 0) {
              // Get oldest invoice date
              const openFolios = folios.filter(f => f.status === 'open' && f.balance > 0);
              const oldestFolio = openFolios
                .slice()
                .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))[0];

              return {
                company_id: company.id,
                company_name: company.name,
                corporate_code: company.corporate_code,
                contact_person: company.contact_person,
                contact_email: company.contact_email,
                contact_phone: company.contact_phone,
                payment_terms: company.payment_terms,
                total_outstanding: totalOutstanding,
                open_folios_count: openFolios.length,
                oldest_invoice_date: oldestFolio?.created_at,
                days_outstanding: oldestFolio
                  ? Math.floor((new Date() - new Date(oldestFolio.created_at)) / (1000 * 60 * 60 * 24))
                  : 0
              };
            }
            return null;
          } catch (err) {
            return null;
          }
        });

        const arResults = await Promise.all(arPromises);
        const validAR = arResults.filter(ar => ar !== null);
        setArData(validAR);
      } catch (fallbackError) {
        console.error('Fallback also failed:', fallbackError);
        setArData([]);
      }
    } finally {
      setLoading(false);
    }
  };

  const loadAgingData = async () => {
    setAgingLoading(true);
    try {
      const response = await axios.get('/cashiering/ar-aging-report');
      setAgingData(response.data || null);
    } catch (error) {
      console.error('Failed to load city ledger aging report:', error);
      toast.error('AR aging raporu yüklenemedi');
      setAgingData(null);
    } finally {
      setAgingLoading(false);
    }
  };

  const getAgingBucket = (days) => {
    if (days <= 7) return { label: '0-7 days', color: 'bg-green-500' };
    if (days <= 14) return { label: '8-14 days', color: 'bg-blue-500' };
    if (days <= 30) return { label: '15-30 days', color: 'bg-yellow-500' };
    if (days <= 60) return { label: '31-60 days', color: 'bg-amber-500' };
    return { label: '60+ days', color: 'bg-red-500' };
  };

  const getUrgencyLevel = (days) => {
    if (days <= 7) return { level: 'Low', color: 'text-green-600' };
    if (days <= 30) return { level: 'Medium', color: 'text-yellow-600' };
    if (days <= 60) return { level: 'High', color: 'text-amber-600' };
    return { level: 'Critical', color: 'text-red-600' };
  };

  const filteredData = arData
    .filter(item => {
      const matchesSearch = 
        item.company_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (item.corporate_code || '').toLowerCase().includes(searchTerm.toLowerCase());
      
      if (filterDays === 'all') return matchesSearch;
      
      const days = item.days_outstanding || 0;
      if (filterDays === '0-30') return matchesSearch && days <= 30;
      if (filterDays === '31-60') return matchesSearch && days > 30 && days <= 60;
      if (filterDays === '60+') return matchesSearch && days > 60;
      
      return matchesSearch;
    })
    .sort((a, b) => b.days_outstanding - a.days_outstanding);

  const totalOutstanding = arData.reduce((sum, item) => sum + item.total_outstanding, 0);
  const totalCompanies = arData.length;
  const criticalCount = arData.filter(item => item.days_outstanding > 60).length;

  const handleExportCompanyAging = () => {
    const url = `/api/reports/company-aging/excel`;
    window.open(url, '_blank');
  };

  const flattenAgingRows = () => {
    if (!agingData || !agingData.aging_buckets) return [];

    const bucketLabels = {
      current: '0-30 days',
      '30_days': '31-60 days',
      '60_days': '61-90 days',
      '90_plus': '90+ days'
    };

    const rows = [];
    Object.keys(agingData.aging_buckets).forEach((bucketKey) => {
      const accounts = agingData.aging_buckets[bucketKey] || [];
      accounts.forEach((account) => {
        rows.push({
          ...account,
          bucketKey,
          bucketLabel: bucketLabels[bucketKey] || bucketKey
        });
      });
    });

    return rows.sort((a, b) => b.days_old - a.days_old);
  };

  const openAccountStatement = async (account) => {
    setSelectedAccount(account);
    setStatementLoading(true);
    try {
      const response = await axios.get(`/cashiering/city-ledger/${account.account_id}/transactions`, {
        params: { limit: 200 }
      });
      setAccountStatement(response.data || null);
    } catch (error) {
      console.error('Failed to load account statement:', error);
      toast.error('Hesap ekstresi yüklenemedi');
      setAccountStatement(null);
    } finally {
      setStatementLoading(false);
    }
  };

  const closeAccountStatement = () => {
    setSelectedAccount(null);
    setAccountStatement(null);
  };

  if (loading && agingLoading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="pending-ar">
        <div className="flex items-center justify-center h-screen">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600"></div>
        </div>
      </Layout>
    );
  }

  const agingRows = flattenAgingRows();

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="pending-ar">
      <div className="p-6 space-y-6">
        <Tabs defaultValue="pending-ar">
          <TabsList className="mb-4">
            <TabsTrigger value="pending-ar">Pending AR</TabsTrigger>
            <TabsTrigger value="city-ledger">City Ledger Aging</TabsTrigger>
          </TabsList>

          {/* Pending AR Tab (Company-based) */}
          <TabsContent value="pending-ar" className="space-y-6">
            {/* Header */}
            <div className="flex justify-between items-center">
              <div>
                <h1 className="text-4xl font-bold" style={{ fontFamily: 'Space Grotesk' }}>
                  Accounts Receivable
                </h1>
                <p className="text-gray-600 mt-1">Pending corporate invoices and payments</p>
              </div>
              <Button onClick={handleExportCompanyAging}>
                <Download className="w-4 h-4 mr-2" />
                Export Aging to Excel
              </Button>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
              <Card className="bg-gradient-to-br from-blue-500 to-blue-600 text-white">
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm opacity-90">Total Outstanding</div>
                      <div className="text-3xl font-bold mt-1">
                        ${totalOutstanding.toFixed(2)}
                      </div>
                    </div>
                    <DollarSign className="w-12 h-12 opacity-75" />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm text-gray-600">Companies with AR</div>
                      <div className="text-3xl font-bold text-blue-600 mt-1">{totalCompanies}</div>
                    </div>
                    <Building2 className="w-12 h-12 text-blue-600 opacity-50" />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm text-gray-600">Critical (60+ days)</div>
                      <div className="text-3xl font-bold text-red-600 mt-1">{criticalCount}</div>
                    </div>
                    <AlertCircle className="w-12 h-12 text-red-600 opacity-50" />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm text-gray-600">Avg Days Outstanding</div>
                      <div className="text-3xl font-bold text-amber-600 mt-1">
                        {arData.length > 0
                          ? Math.round(
                              arData.reduce((sum, item) => sum + item.days_outstanding, 0) / arData.length
                            )
                          : 0}
                      </div>
                    </div>
                    <Clock className="w-12 h-12 text-amber-600 opacity-50" />
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Filters */}
            <Card>
              <CardContent className="py-4">
                <div className="flex items-center space-x-4">
                  <div className="flex-1 relative">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                    <Input
                      className="pl-10"
                      placeholder="Search by company name or code..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                    />
                  </div>
                  <div className="flex space-x-2">
                    <Button
                      variant={filterDays === 'all' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilterDays('all')}
                    >
                      All
                    </Button>
                    <Button
                      variant={filterDays === '0-30' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilterDays('0-30')}
                    >
                      0-30 days
                    </Button>
                    <Button
                      variant={filterDays === '31-60' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilterDays('31-60')}
                    >
                      31-60 days
                    </Button>
                    <Button
                      variant={filterDays === '60+' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilterDays('60+')}
                    >
                      60+ days
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* AR List */}
            <Card>
              <CardHeader>
                <CardTitle>{t('finance.pendingAR')}</CardTitle>
                <CardDescription>Outstanding balances by company</CardDescription>
              </CardHeader>
              <CardContent>
                {filteredData.length === 0 ? (
                  <div className="text-center py-12 text-gray-500">
                    <DollarSign className="w-16 h-16 mx-auto mb-4 opacity-50" />
                    <p className="text-lg font-semibold mb-2">No Pending AR</p>
                    <p className="text-sm">All corporate invoices are paid up!</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {filteredData.map((item) => {
                      const aging = getAgingBucket(item.days_outstanding);
                      const urgency = getUrgencyLevel(item.days_outstanding);

                      return (
                        <div
                          key={item.company_id}
                          className="border rounded-lg p-4 hover:shadow-md transition-shadow"
                        >
                          <div className="flex justify-between items-start">
                            <div className="flex-1">
                              <div className="flex items-center space-x-3 mb-2">
                                <h3 className="text-lg font-semibold">{item.company_name}</h3>
                                {item.corporate_code && (
                                  <Badge variant="outline">{item.corporate_code}</Badge>
                                )}
                                <Badge className={aging.color}>{aging.label}</Badge>
                                <span className={`text-sm font-semibold ${urgency.color}`}>
                                  {urgency.level} Priority
                                </span>
                              </div>

                              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                                <div>
                                  <div className="text-gray-600">Outstanding Balance</div>
                                  <div className="text-xl font-bold text-red-600">
                                    ${item.total_outstanding.toFixed(2)}
                                  </div>
                                </div>
                                <div>
                                  <div className="text-gray-600">Open Invoices</div>
                                  <div className="text-xl font-bold">{item.open_folios_count}</div>
                                </div>
                                <div>
                                  <div className="text-gray-600">Days Outstanding</div>
                                  <div className="text-xl font-bold text-amber-600">
                                    {item.days_outstanding} days
                                  </div>
                                </div>
                                <div>
                                  <div className="text-gray-600">Payment Terms</div>
                                  <div className="text-lg font-semibold">{item.payment_terms || 'N/A'}</div>
                                </div>
                              </div>

                              {item.contact_person && (
                                <div className="mt-3 pt-3 border-t">
                                  <div className="text-sm text-gray-600 mb-1">Contact Information:</div>
                                  <div className="flex items-center space-x-4 text-sm">
                                    <div className="flex items-center space-x-1">
                                      <span className="font-medium">{item.contact_person}</span>
                                    </div>
                                    {item.contact_email && (
                                      <div className="flex items-center space-x-1">
                                        <Mail className="w-4 h-4 text-gray-400" />
                                        <a
                                          href={`mailto:${item.contact_email}`}
                                          className="text-blue-600 hover:underline"
                                        >
                                          {item.contact_email}
                                        </a>
                                      </div>
                                    )}
                                    {item.contact_phone && (
                                      <div className="flex items-center space-x-1">
                                        <Phone className="w-4 h-4 text-gray-400" />
                                        <span>{item.contact_phone}</span>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              )}
                            </div>

                            <div className="flex flex-col space-y-2">
                              <Button size="sm">View Details</Button>
                              <Button variant="outline" size="sm">
                                <Mail className="w-4 h-4 mr-2" />
                                Send Reminder
                              </Button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* City Ledger Aging Tab */}
          <TabsContent value="city-ledger" className="space-y-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-2xl font-bold">City Ledger Aging</h2>
                <p className="text-gray-600 mt-1">30/60/90 day aging based on city ledger accounts</p>
              </div>
              <Button variant="outline" onClick={loadAgingData} disabled={agingLoading}>
                {agingLoading ? 'Refreshing...' : 'Refresh'}
              </Button>
            </div>

            {/* Aging Summary */}
            {agingData && agingData.totals ? (
              <div className="grid grid-cols-1 md:grid-cols-5 gap-6">
                <Card>
                  <CardContent className="pt-6">
                    <div className="text-sm text-gray-600">Total AR</div>
                    <div className="text-2xl font-bold text-blue-600 mt-1">
                      ${agingData.totals.total.toFixed(2)}
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <div className="text-sm text-gray-600">0-30 days</div>
                    <div className="text-2xl font-bold text-green-600 mt-1">
                      ${agingData.totals.current.toFixed(2)}
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <div className="text-sm text-gray-600">31-60 days</div>
                    <div className="text-2xl font-bold text-yellow-600 mt-1">
                      ${agingData.totals['30_days'].toFixed(2)}
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <div className="text-sm text-gray-600">61-90 days</div>
                    <div className="text-2xl font-bold text-amber-600 mt-1">
                      ${agingData.totals['60_days'].toFixed(2)}
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <div className="text-sm text-gray-600">90+ days</div>
                    <div className="text-2xl font-bold text-red-600 mt-1">
                      ${agingData.totals['90_plus'].toFixed(2)}
                    </div>
                  </CardContent>
                </Card>
              </div>
            ) : (
              <Card>
                <CardContent className="py-10 text-center text-gray-500">
                  {agingLoading ? 'Loading aging data...' : 'No city ledger aging data available.'}
                </CardContent>
              </Card>
            )}

            {/* Aging Accounts Table */}
            {agingRows.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>City Ledger Accounts</CardTitle>
                  <CardDescription>Accounts with outstanding balances by aging bucket</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-gray-600">
                          <th className="py-2 pr-4">Account</th>
                          <th className="py-2 pr-4 text-right">Balance</th>
                          <th className="py-2 pr-4 text-right">Days Old</th>
                          <th className="py-2 pr-4">Bucket</th>
                          <th className="py-2 pr-4 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {agingRows.map((row) => (
                          <tr key={`${row.account_id}-${row.bucketKey}`} className="border-b last:border-b-0">
                            <td className="py-2 pr-4 font-medium">{row.account_name}</td>
                            <td className="py-2 pr-4 text-right">${row.balance.toFixed(2)}</td>
                            <td className="py-2 pr-4 text-right">{row.days_old}</td>
                            <td className="py-2 pr-4">
                              <Badge variant="outline">{row.bucketLabel}</Badge>
                            </td>
                            <td className="py-2 pr-4 text-right">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => openAccountStatement(row)}
                              >
                                View Statement
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>
        </Tabs>

        {/* Account Statement Dialog */}
        <Dialog open={!!selectedAccount} onOpenChange={(open) => !open && closeAccountStatement()}>
          <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>
                {selectedAccount ? `Account Statement - ${selectedAccount.account_name}` : 'Account Statement'}
              </DialogTitle>
            </DialogHeader>

            {statementLoading ? (
              <div className="py-10 text-center text-gray-500">Loading statement...</div>
            ) : !accountStatement ? (
              <div className="py-10 text-center text-gray-500">No statement data available.</div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                  <div>
                    <div className="text-gray-600">Account</div>
                    <div className="font-semibold">{selectedAccount?.account_name}</div>
                  </div>
                  <div>
                    <div className="text-gray-600">Current Balance</div>
                    <div className="font-semibold text-red-600">
                      ${accountStatement.summary.current_balance.toFixed(2)}
                    </div>
                  </div>
                  <div>
                    <div className="text-gray-600">Transactions</div>
                    <div className="font-semibold">{accountStatement.summary.transaction_count}</div>
                  </div>
                </div>

                <div className="border rounded-md overflow-hidden">
                  <div className="bg-gray-50 px-4 py-2 text-sm font-semibold text-gray-600 flex justify-between">
                    <span>Transactions</span>
                    <span>
                      Charges: ${accountStatement.summary.total_charges.toFixed(2)} | Payments: $
                      {accountStatement.summary.total_payments.toFixed(2)}
                    </span>
                  </div>
                  <div className="max-h-80 overflow-y-auto">
                    <table className="min-w-full text-xs">
                      <thead>
                        <tr className="border-b text-left text-gray-600">
                          <th className="py-2 px-4">Date</th>
                          <th className="py-2 px-4">Type</th>
                          <th className="py-2 px-4">Description</th>
                          <th className="py-2 px-4 text-right">Amount</th>
                          <th className="py-2 px-4">Reference</th>
                        </tr>
                      </thead>
                      <tbody>
                        {accountStatement.transactions.map((tx) => (
                          <tr key={tx.id} className="border-b last:border-b-0">
                            <td className="py-2 px-4">
                              {new Date(tx.transaction_date).toLocaleDateString()}
                            </td>
                            <td className="py-2 px-4 capitalize">{tx.transaction_type}</td>
                            <td className="py-2 px-4">{tx.description}</td>
                            <td className="py-2 px-4 text-right">
                              ${tx.amount.toFixed(2)}
                            </td>
                            <td className="py-2 px-4">{tx.reference_number || '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default PendingAR;
