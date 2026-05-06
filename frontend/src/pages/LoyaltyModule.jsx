import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Award, Plus, TrendingUp, TrendingDown, Star, Users, Gift, Crown } from 'lucide-react';

const LoyaltyModule = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [programs, setPrograms] = useState([]);
  const [guests, setGuests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openDialog, setOpenDialog] = useState(null);
  const [selectedProgram, setSelectedProgram] = useState(null);
  const [transactions, setTransactions] = useState([]);

  const [newTransaction, setNewTransaction] = useState({
    guest_id: '',
    points: 0,
    transaction_type: 'earned',
    description: ''
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [programsRes, guestsRes] = await Promise.all([
        axios.get('/loyalty/programs'),
        axios.get('/pms/guests')
      ]);
      setPrograms(programsRes.data);
      setGuests(guestsRes.data);
    } catch (error) {
      toast.error('Sadakat verileri yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const loadTransactions = async (guestId) => {
    try {
      const response = await axios.get(`/loyalty/guest/${guestId}`);
      setTransactions(response.data.transactions || []);
    } catch (error) {
      console.error('Failed to load transactions');
    }
  };

  const handleCreateTransaction = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/loyalty/transactions', newTransaction);
      toast.success('Transaction successful');
      setOpenDialog(null);
      loadData();
      setNewTransaction({ guest_id: '', points: 0, transaction_type: 'earned', description: '' });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'İşlem oluşturulamadı');
    }
  };

  const createLoyaltyProgram = async (guestId) => {
    try {
      await axios.post('/loyalty/programs', {
        guest_id: guestId,
        tier: 'bronze',
        points: 0,
        lifetime_points: 0
      });
      toast.success('Guest enrolled in loyalty program');
      loadData();
    } catch (error) {
      toast.error('Misafir kaydedilemedi');
    }
  };

  const getTierColor = (tier) => {
    switch(tier) {
      case 'platinum': return 'from-indigo-500 to-indigo-700';
      case 'gold': return 'from-yellow-400 to-yellow-600';
      case 'silver': return 'from-gray-300 to-gray-500';
      default: return 'from-amber-400 to-amber-600';
    }
  };

  const getTierBadgeColor = (tier) => {
    switch(tier) {
      case 'platinum': return 'bg-indigo-100 text-indigo-700 border-indigo-300';
      case 'gold': return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      case 'silver': return 'bg-gray-100 text-gray-700 border-gray-300';
      default: return 'bg-amber-100 text-amber-700 border-amber-300';
    }
  };

  const getTierIcon = (tier) => {
    switch(tier) {
      case 'platinum': return <Crown className="w-5 h-5 text-white" />;
      case 'gold': return <Award className="w-5 h-5 text-white" />;
      case 'silver': return <Gift className="w-5 h-5 text-white" />;
      default: return <Star className="w-5 h-5 text-white" />;
    }
  };

  const getTierStars = (tier) => {
    const count = tier === 'platinum' ? 4 : tier === 'gold' ? 3 : tier === 'silver' ? 2 : 1;
    return Array(count).fill(0).map((_, i) => <Star key={i} className="w-3 h-3 fill-current" />);
  };

  const getTierBenefits = (tier) => {
    const benefits = {
      bronze: ['5% discount on stays', 'Birthday bonus points', 'Welcome drink', 'Priority support'],
      silver: ['10% discount on stays', 'Birthday bonus points', 'Welcome drink', 'Late checkout until 2 PM', 'Room service discount'],
      gold: ['15% discount on stays', 'Birthday bonus points', 'Complimentary breakfast', 'Late checkout until 4 PM', 'Room upgrade subject to availability', 'Free parking'],
      platinum: ['20% discount on stays', 'Birthday bonus points', 'Complimentary breakfast', 'Late checkout until 6 PM', 'Guaranteed room upgrade', 'Airport transfer', 'Spa discount 15%', 'VIP concierge']
    };
    return benefits[tier] || benefits.bronze;
  };

  const getTotalPoints = () => {
    return programs.reduce((sum, p) => sum + (p?.points || 0), 0);
  };

  const getTotalLifetimePoints = () => {
    return programs.reduce((sum, p) => sum + (p?.lifetime_points || 0), 0);
  };

  const viewProgramDetails = async (program) => {
    setSelectedProgram(program);
    await loadTransactions(program.guest_id);
    setOpenDialog('details');
  };

  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="loyalty">
        <div className="p-6 text-center">{t("common.loading")}</div>
      </Layout>
    );
  }

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="loyalty">
      <div className="p-6 space-y-6">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Space Grotesk' }}>{t('loyalty.title')}</h1>
            <p className="text-gray-600">{t('loyalty.subtitle')}</p>
          </div>
          <Dialog open={openDialog === 'transaction'} onOpenChange={(open) => setOpenDialog(open ? 'transaction' : null)}>
            <DialogTrigger asChild>
              <Button data-testid="add-points-btn" size="lg">
                <Plus className="w-4 h-4 mr-2" />
                {t('loyalty.awardPoints')}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Award or Redeem Points</DialogTitle>
                <DialogDescription>Manage guest loyalty points</DialogDescription>
              </DialogHeader>
              <form onSubmit={handleCreateTransaction} className="space-y-4">
                <div>
                  <Label htmlFor="transaction-guest">Guest</Label>
                  <Select value={newTransaction.guest_id} onValueChange={(v) => setNewTransaction({...newTransaction, guest_id: v})}>
                    <SelectTrigger id="transaction-guest" data-testid="transaction-guest-select">
                      <SelectValue placeholder="Select guest" />
                    </SelectTrigger>
                    <SelectContent>
                      {guests.map(g => (
                        <SelectItem key={g.id} value={g.id}>{g.name} - {g.email}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="transaction-type">Type</Label>
                  <Select value={newTransaction.transaction_type} onValueChange={(v) => setNewTransaction({...newTransaction, transaction_type: v})}>
                    <SelectTrigger id="transaction-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="earned">Earned (Add Points)</SelectItem>
                      <SelectItem value="redeemed">Redeemed (Use Points)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="points">Points</Label>
                  <Input
                    id="points"
                    type="number"
                    min="1"
                    value={newTransaction.points}
                    onChange={(e) => setNewTransaction({...newTransaction, points: parseInt(e.target.value)})}
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="description">Description</Label>
                  <Input
                    id="description"
                    value={newTransaction.description}
                    onChange={(e) => setNewTransaction({...newTransaction, description: e.target.value})}
                    placeholder="e.g., Stay completed, Welcome bonus, etc."
                    required
                  />
                </div>
                <Button type="submit" className="w-full" data-testid="submit-transaction-btn">Submit Transaction</Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        <Tabs defaultValue="enrolled" className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="enrolled">{t('loyalty.enrolledMembers')} ({programs.length})</TabsTrigger>
            <TabsTrigger value="unenrolled">{t('loyalty.notEnrolled')} ({guests.filter(g => !programs.find(p => p.guest_id === g.id)).length})</TabsTrigger>
            <TabsTrigger value="overview">{t('loyalty.overview')}</TabsTrigger>
          </TabsList>

          {/* OVERVIEW TAB */}
          <TabsContent value="overview" className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-600">Total Members</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">{programs.length}</div>
                  <p className="text-xs text-gray-500">Enrolled guests</p>
                </CardContent>
              </Card>
              
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-600">Total Active Points</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold text-blue-600">{getTotalPoints().toLocaleString()}</div>
                  <p className="text-xs text-gray-500">Across all members</p>
                </CardContent>
              </Card>
              
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-600">Lifetime Points</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold text-indigo-600">{getTotalLifetimePoints().toLocaleString()}</div>
                  <p className="text-xs text-gray-500">All-time earned</p>
                </CardContent>
              </Card>
              
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-600">Avg Points per Guest</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold text-green-600">
                    {programs.length > 0 ? Math.round(getTotalPoints() / programs.length) : 0}
                  </div>
                  <p className="text-xs text-gray-500">Average balance</p>
                </CardContent>
              </Card>
            </div>

            {/* Tier Distribution */}
            <Card>
              <CardHeader>
                <CardTitle>Member Distribution by Tier</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {['bronze', 'silver', 'gold', 'platinum'].map(tier => {
                    const count = programs.filter(p => p.tier === tier).length;
                    const percentage = programs.length > 0 ? (count / programs.length * 100).toFixed(1) : 0;
                    return (
                      <div key={tier} className="text-center">
                        <div className={`inline-flex items-center justify-center w-16 h-16 rounded-full bg-gradient-to-br ${getTierColor(tier)} mb-2`}>
                          <span className="text-white text-2xl font-bold">{count}</span>
                        </div>
                        <div className="font-medium capitalize">{tier}</div>
                        <div className="text-sm text-gray-500">{percentage}%</div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* ENROLLED MEMBERS TAB */}
          <TabsContent value="enrolled" className="space-y-4">
            {programs.length === 0 ? (
              <Card>
                <CardContent className="py-12 text-center text-gray-500">
                  <Award className="w-16 h-16 mx-auto mb-4 text-gray-300" />
                  <p className="text-lg font-medium mb-2">{t('loyalty.noMembers')}</p>
                  <p className="text-sm">{t('loyalty.startEnrolling')}</p>
                </CardContent>
              </Card>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {programs.map((program) => {
                  const guest = guests.find(g => g.id === program.guest_id);
                  return (
                    <Card 
                      key={program.id} 
                      data-testid={`loyalty-card-${program.guest_id}`}
                      className="card-hover cursor-pointer"
                      onClick={() => viewProgramDetails(program)}
                    >
                      <CardHeader>
                        <div className="flex justify-between items-start">
                          <div className="flex-1">
                            <CardTitle className="text-lg">{guest?.name || 'Unknown Guest'}</CardTitle>
                            <p className="text-sm text-gray-600">{guest?.email}</p>
                          </div>
                          <div className={`p-2 rounded-lg bg-gradient-to-br ${getTierColor(program.tier)}`}>
                            {getTierIcon(program.tier)}
                          </div>
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        {/* Tier Badge */}
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-gray-600">Membership Tier</span>
                          <div className={`px-3 py-1 rounded-full text-xs font-medium flex items-center space-x-1 border ${getTierBadgeColor(program.tier)}`}>
                            {getTierStars(program.tier)}
                            <span className="ml-1 capitalize">{program.tier}</span>
                          </div>
                        </div>
                        
                        {/* Points Display */}
                        <div className="pt-4 border-t">
                          <div className="text-center">
                            <div className="text-4xl font-bold text-blue-600">{(program.points || 0).toLocaleString()}</div>
                            <div className="text-sm text-gray-600 mt-1">Available Points</div>
                          </div>
                        </div>

                        {/* Lifetime Points */}
                        <div className="pt-2 border-t text-sm flex justify-between">
                          <span className="text-gray-600">Lifetime Points</span>
                          <span className="font-medium">{(program.lifetime_points || 0).toLocaleString()}</span>
                        </div>

                        {/* Benefits Preview */}
                        <div className="pt-2 border-t">
                          <div className="text-xs text-gray-600 mb-2">Member Benefits:</div>
                          <div className="flex flex-wrap gap-1">
                            {getTierBenefits(program.tier).slice(0, 3).map((benefit, idx) => (
                              <span key={idx} className="text-xs bg-gray-100 px-2 py-1 rounded">
                                {benefit}
                              </span>
                            ))}
                            {getTierBenefits(program.tier).length > 3 && (
                              <span className="text-xs bg-gray-100 px-2 py-1 rounded">
                                +{getTierBenefits(program.tier).length - 3} more
                              </span>
                            )}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </TabsContent>

          {/* UNENROLLED GUESTS TAB */}
          <TabsContent value="unenrolled" className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {guests
                .filter(g => !programs.find(p => p.guest_id === g.id))
                .map((guest) => (
                  <Card key={guest.id}>
                    <CardContent className="pt-6">
                      <div className="flex justify-between items-start">
                        <div className="flex-1">
                          <div className="font-semibold text-lg">{guest.name}</div>
                          <div className="text-sm text-gray-600">{guest.email}</div>
                          <div className="text-sm text-gray-500 mt-1">{guest.phone}</div>
                          <div className="text-xs text-gray-400 mt-2">
                            Total stays: {guest.total_stays}
                          </div>
                        </div>
                        <Button 
                          size="sm" 
                          onClick={() => createLoyaltyProgram(guest.id)}
                          data-testid={`enroll-guest-${guest.id}`}
                        >
                          <Plus className="w-4 h-4 mr-1" />
                          Enroll
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
            </div>
            
            {guests.filter(g => !programs.find(p => p.guest_id === g.id)).length === 0 && (
              <Card>
                <CardContent className="py-12 text-center text-gray-500">
                  <Users className="w-16 h-16 mx-auto mb-4 text-gray-300" />
                  <p className="text-lg font-medium mb-2">All guests are enrolled!</p>
                  <p className="text-sm">Every guest in your system has a loyalty account</p>
                </CardContent>
              </Card>
            )}
          </TabsContent>
        </Tabs>

        {/* Program Details Dialog */}
        <Dialog open={openDialog === 'details'} onOpenChange={(open) => !open && setOpenDialog(null)}>
          <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Loyalty Program Details</DialogTitle>
            </DialogHeader>
            {selectedProgram && (
              <div className="space-y-6">
                {/* Guest Info */}
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-xl font-bold">
                      {guests.find(g => g.id === selectedProgram.guest_id)?.name}
                    </h3>
                    <p className="text-gray-600">
                      {guests.find(g => g.id === selectedProgram.guest_id)?.email}
                    </p>
                  </div>
                  <div className={`px-4 py-2 rounded-lg bg-gradient-to-br ${getTierColor(selectedProgram.tier)} text-white font-medium capitalize flex items-center space-x-2`}>
                    {getTierIcon(selectedProgram.tier)}
                    <span>{selectedProgram.tier} Member</span>
                  </div>
                </div>

                {/* Points Summary */}
                <div className="grid grid-cols-2 gap-4">
                  <Card>
                    <CardContent className="pt-6">
                      <div className="text-3xl font-bold text-blue-600">{(selectedProgram?.points || 0).toLocaleString()}</div>
                      <div className="text-sm text-gray-600">Available Points</div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-6">
                      <div className="text-3xl font-bold text-indigo-600">{(selectedProgram?.lifetime_points || 0).toLocaleString()}</div>
                      <div className="text-sm text-gray-600">Lifetime Points</div>
                    </CardContent>
                  </Card>
                </div>

                {/* Benefits */}
                <div>
                  <h4 className="font-semibold mb-3">Member Benefits</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {getTierBenefits(selectedProgram.tier).map((benefit, idx) => (
                      <div key={idx} className="flex items-center space-x-2 text-sm">
                        <Star className="w-4 h-4 text-yellow-500 fill-current" />
                        <span>{benefit}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Transaction History */}
                <div>
                  <h4 className="font-semibold mb-3">Transaction History</h4>
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {!transactions || transactions.length === 0 ? (
                      <p className="text-sm text-gray-500 text-center py-4">No transactions yet</p>
                    ) : (
                      transactions.map((txn, idx) => txn && (
                        <div key={idx} className="flex justify-between items-center py-2 px-3 bg-gray-50 rounded">
                          <div className="flex-1">
                            <div className="font-medium text-sm">{txn.description || 'Transaction'}</div>
                            <div className="text-xs text-gray-500">
                              {txn.created_at ? new Date(txn.created_at).toLocaleDateString() : 'N/A'}
                            </div>
                          </div>
                          <div className="flex items-center space-x-2">
                            <span className={`text-lg font-bold ${txn.transaction_type === 'earned' ? 'text-green-600' : 'text-red-600'}`}>
                              {txn.transaction_type === 'earned' ? '+' : '-'}{txn.points || 0}
                            </span>
                            {txn.transaction_type === 'earned' ? (
                              <TrendingUp className="w-4 h-4 text-green-600" />
                            ) : (
                              <TrendingDown className="w-4 h-4 text-red-600" />
                            )}
                          </div>
                        </div>
                      ))
                    )}
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

export default LoyaltyModule;
