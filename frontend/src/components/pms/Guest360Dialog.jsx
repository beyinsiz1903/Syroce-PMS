import React, { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Send, FileText, Star, Phone, Mail, MapPin, Calendar,
  Hotel, Award, ShieldCheck, AlertTriangle, MessageSquare,
  Heart, Globe, Tag, Clock, User, DollarSign, TrendingUp, Loader2, Crown
} from 'lucide-react';
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from 'recharts';

const Guest360Dialog = ({
  open,
  onClose,
  guest360Data,
  loadingGuest360,
  selectedGuest360,
  loadGuest360,
}) => {
  const { t } = useTranslation();
  const [newNote, setNewNote] = useState('');
  const [guestTag, setGuestTag] = useState('');
  const [guestNote, setGuestNote] = useState('');

  const addNote = async () => {
    if (!newNote.trim() || !selectedGuest360) return;
    try {
      await axios.post('/crm/guest/note', {
        guest_id: selectedGuest360,
        note: newNote,
        category: 'general'
      });
      toast.success('Note added!');
      setNewNote('');
      loadGuest360(selectedGuest360);
    } catch {
      toast.error('Not eklenemedi');
    }
  };

  const addGuestTag = async () => {
    if (!guestTag.trim() || !selectedGuest360) return;
    try {
      await axios.post(`/crm/guest/add-tag?guest_id=${selectedGuest360}&tag=${guestTag}`);
      toast.success('Tag added');
      setGuestTag('');
      loadGuest360(selectedGuest360);
    } catch {
      toast.error('Etiket eklenemedi');
    }
  };

  const addGuestNote = async () => {
    if (!guestNote.trim() || !selectedGuest360) return;
    try {
      await axios.post(`/crm/guest/note?guest_id=${selectedGuest360}&note=${guestNote}`);
      toast.success('Note added');
      setGuestNote('');
      loadGuest360(selectedGuest360);
    } catch {
      toast.error('Not eklenemedi');
    }
  };

  return (
<Dialog open={open} onOpenChange={(o) => !o && onClose()}>
  <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
    <DialogHeader>
      <DialogTitle className="text-2xl">🌟 Guest 360° Profile</DialogTitle>
      <DialogDescription>Complete guest intelligence and relationship data</DialogDescription>
    </DialogHeader>
    
    {loadingGuest360 ? (
      <div className="text-center py-12">
        <div className="text-4xl mb-4">⏳</div>
        <div>Loading guest profile...</div>
      </div>
    ) : guest360Data ? (
      <div className="space-y-4">
        {/* Quick Action Buttons - NEW */}
        <div className="flex gap-2 p-4 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg border border-blue-200">
          <Button 
            onClick={() => {
              toast.success('Opening offer creation for ' + guest360Data.guest?.name);
              // TODO: Navigate to offer creation or open offer dialog
            }}
            className="flex-1 bg-green-600 hover:bg-green-700"
          >
            <Send className="w-4 h-4 mr-2" />
            Send Offer
          </Button>
          <Button 
            onClick={() => {
              // Scroll to notes section or auto-focus note input
              const noteInput = document.querySelector('textarea[placeholder*="note"]');
              if (noteInput) noteInput.focus();
              toast.info('Note section ready - add your note below');
            }}
            variant="outline"
            className="flex-1 border-blue-400 hover:bg-blue-50"
          >
            <FileText className="w-4 h-4 mr-2" />
            Add Note
          </Button>
          <Button 
            onClick={async () => {
              try {
                const preference = prompt('Enter room preference (e.g., High Floor, Sea View, Quiet Room):');
                if (preference) {
                  await axios.post(`/crm/guest/add-tag?guest_id=${selectedGuest360}&tag=PREF: ${preference}`);
                  toast.success('Room preference saved!');
                  loadGuest360(selectedGuest360);
                }
              } catch (error) {
                toast.error('Tercih kaydedilemedi');
              }
            }}
            variant="outline"
            className="flex-1 border-purple-400 hover:bg-purple-50"
          >
            <Star className="w-4 h-4 mr-2" />
            Block Room Preference
          </Button>
          <Button 
            onClick={() => {
              // Navigate to messaging center with pre-filled guest
              window.location.href = `/ota-messaging-hub?guest=${guest360Data.guest?.id}&name=${guest360Data.guest?.name}`;
            }}
            variant="outline"
            className="flex-1 border-orange-400 hover:bg-orange-50"
          >
            <MessageSquare className="w-4 h-4 mr-2" />
            Message Guest
          </Button>
        </div>

        {/* Identity Card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Identity & Contact</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-sm text-gray-600">Name</div>
              <div className="font-semibold">{guest360Data.guest?.name}</div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Email</div>
              <div className="font-semibold">{guest360Data.guest?.email}</div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Phone</div>
              <div className="font-semibold">{guest360Data.guest?.phone}</div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Country</div>
              <div className="font-semibold">{guest360Data.guest?.country || 'N/A'}</div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Loyalty Status</div>
              <div className={`inline-block px-2 py-1 rounded text-sm font-bold ${
                guest360Data.profile?.loyalty_status === 'vip' ? 'bg-purple-600 text-white' :
                guest360Data.profile?.loyalty_status === 'gold' ? 'bg-yellow-500 text-white' :
                guest360Data.profile?.loyalty_status === 'silver' ? 'bg-gray-400 text-white' :
                'bg-blue-500 text-white'
              }`}>
                {guest360Data.profile?.loyalty_status?.toUpperCase() || 'STANDARD'}
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Last Seen</div>
              <div className="font-semibold">
                {guest360Data.profile?.last_seen_date ? new Date(guest360Data.profile.last_seen_date).toLocaleDateString() : 'N/A'}
              </div>
            </div>
          </CardContent>
        </Card>


        {/* Loyalty Progress Card */}
        <Card className="bg-gradient-to-r from-purple-50 to-pink-50 border-purple-200">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Crown className="w-5 h-5 text-purple-600" />
              Loyalty Program Status
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between items-center">
              <div>
                <div className="text-2xl font-bold">
                  {guest360Data.profile?.loyalty_points || guest360Data.guest?.loyalty_points || 0} pts
                </div>
                <div className="text-sm text-gray-600">Current Balance</div>
              </div>
              <div className={`px-4 py-2 rounded-lg font-bold text-lg ${
                guest360Data.profile?.loyalty_status === 'vip' ? 'bg-purple-600 text-white' :
                guest360Data.profile?.loyalty_status === 'gold' ? 'bg-yellow-500 text-white' :
                guest360Data.profile?.loyalty_status === 'silver' ? 'bg-gray-400 text-white' :
                'bg-blue-500 text-white'
              }`}>
                {(guest360Data.profile?.loyalty_status || guest360Data.guest?.loyalty_tier || 'standard').toUpperCase()}
              </div>
            </div>
            
            {/* Progress to Next Tier */}
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-600">Progress to Next Tier</span>
                <span className="font-semibold">
                  {(() => {
                    const currentPoints = guest360Data.profile?.loyalty_points || guest360Data.guest?.loyalty_points || 0;
                    const currentStatus = guest360Data.profile?.loyalty_status || guest360Data.guest?.loyalty_tier || 'standard';
                    const thresholds = { standard: 1000, silver: 2500, gold: 5000, vip: 10000 };
                    const nextTier = 
                      currentStatus === 'standard' ? 'silver' :
                      currentStatus === 'silver' ? 'gold' :
                      currentStatus === 'gold' ? 'vip' :
                      null;
                    
                    if (!nextTier) return 'MAX TIER';
                    const needed = thresholds[nextTier] - currentPoints;
                    return needed > 0 ? `${needed} pts to ${nextTier.toUpperCase()}` : 'Eligible for upgrade!';
                  })()}
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-3">
                <div 
                  className="bg-gradient-to-r from-purple-600 to-pink-600 h-3 rounded-full transition-all"
                  style={{ 
                    width: `${(() => {
                      const currentPoints = guest360Data.profile?.loyalty_points || guest360Data.guest?.loyalty_points || 0;
                      const currentStatus = guest360Data.profile?.loyalty_status || guest360Data.guest?.loyalty_tier || 'standard';
                      const thresholds = { standard: 1000, silver: 2500, gold: 5000, vip: 10000 };
                      const current = thresholds[currentStatus] || 0;
                      const nextTier = 
                        currentStatus === 'standard' ? 'silver' :
                        currentStatus === 'silver' ? 'gold' :
                        currentStatus === 'gold' ? 'vip' :
                        null;
                      
                      if (!nextTier) return 100;
                      const next = thresholds[nextTier];
                      const progress = ((currentPoints - current) / (next - current)) * 100;
                      return Math.min(Math.max(progress, 0), 100);
                    })()}%` 
                  }}
                ></div>
              </div>
            </div>
            
            {/* Tier Benefits */}
            <div className="text-xs space-y-1">
              <div className="font-semibold mb-2">Current Benefits:</div>
              {guest360Data.profile?.loyalty_status === 'vip' || guest360Data.guest?.loyalty_tier === 'vip' ? (
                <>
                  <div className="flex items-center gap-2">✨ Suite Upgrades</div>
                  <div className="flex items-center gap-2">🎁 Welcome Gifts</div>
                  <div className="flex items-center gap-2">🍾 Complimentary Services</div>
                  <div className="flex items-center gap-2">⚡ Priority Check-in/out</div>
                </>
              ) : guest360Data.profile?.loyalty_status === 'gold' || guest360Data.guest?.loyalty_tier === 'gold' ? (
                <>
                  <div className="flex items-center gap-2">🔄 Free Room Upgrade</div>
                  <div className="flex items-center gap-2">☕ Complimentary Breakfast</div>
                  <div className="flex items-center gap-2">📅 Late Check-out</div>
                </>
              ) : guest360Data.profile?.loyalty_status === 'silver' || guest360Data.guest?.loyalty_tier === 'silver' ? (
                <>
                  <div className="flex items-center gap-2">💰 10% Discount</div>
                  <div className="flex items-center gap-2">🎯 Points on Stays</div>
                </>
              ) : (
                <>
                  <div className="flex items-center gap-2">⭐ Earn Points</div>
                  <div className="flex items-center gap-2">📧 Exclusive Offers</div>
                </>
              )}
            </div>
          </CardContent>
        </Card>


        {/* Stats Dashboard */}
        <div className="grid grid-cols-4 gap-4">
          <Card>
            <CardContent className="pt-4 text-center">
              <div className="text-3xl font-bold text-blue-600">{guest360Data.stats?.total_stays || 0}</div>
              <div className="text-sm text-gray-600">Total Stays</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 text-center">
              <div className="text-3xl font-bold text-green-600">{guest360Data.stats?.total_nights || 0}</div>
              <div className="text-sm text-gray-600">Total Nights</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 text-center">
              <div className="text-3xl font-bold text-purple-600">${guest360Data.stats?.lifetime_value || 0}</div>
              <div className="text-sm text-gray-600">Lifetime Value</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 text-center">
              <div className="text-3xl font-bold text-orange-600">${guest360Data.stats?.average_adr || 0}</div>
              <div className="text-sm text-gray-600">Avg ADR</div>
            </CardContent>
          </Card>
        </div>

        {/* Tags & Notes */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Tags & Notes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <div className="text-sm text-gray-600 mb-2">Tags:</div>
              <div className="flex flex-wrap gap-2">
                {guest360Data.guest?.tags?.map((tag, idx) => (
                  <span key={idx} className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs">
                    {tag}
                  </span>
                ))}
                <div className="flex gap-2">
                  <Input 
                    placeholder="Add tag..."
                    value={guestTag}
                    onChange={(e) => setGuestTag(e.target.value)}
                    className="h-8 w-32"
                  />
                  <Button size="sm" onClick={addGuestTag}>{t("common.add")}</Button>
                </div>
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-600 mb-2">Notes:</div>
              <div className="space-y-2 max-h-32 overflow-y-auto mb-2">
                {guest360Data.guest?.notes?.map((note, idx) => (
                  <div key={idx} className="text-xs bg-gray-50 p-2 rounded">
                    <div className="font-semibold">{note.created_by} - {new Date(note.created_at).toLocaleString()}</div>
                    <div>{note.text}</div>
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <Textarea 
                  placeholder="Add note..."
                  value={guestNote}
                  onChange={(e) => setGuestNote(e.target.value)}
                  className="h-16"
                />
                <Button size="sm" onClick={addGuestNote}>Add Note</Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Booking History - Enhanced Timeline */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Calendar className="w-5 h-5" />
              Stay History Timeline
            </CardTitle>
            <CardDescription>
              {guest360Data.profile?.total_stays || 0} total stays • 
              ${(guest360Data.profile?.total_spending || 0).toFixed(0)} lifetime value
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {guest360Data.recent_bookings && guest360Data.recent_bookings.length > 0 ? (
                guest360Data.recent_bookings.map((booking, idx) => {
                  const nights = Math.ceil((new Date(booking.check_out) - new Date(booking.check_in)) / (1000 * 60 * 60 * 24));
                  const adr = nights > 0 ? (booking.total_amount / nights).toFixed(0) : 0;
                  
                  return (
                    <div key={idx} className="relative pl-8 pb-4 border-l-2 border-blue-300 last:border-0">
                      {/* Timeline Dot */}
                      <div className={`absolute left-[-9px] top-0 w-4 h-4 rounded-full ${
                        booking.status === 'checked_out' ? 'bg-green-500' :
                        booking.status === 'checked_in' ? 'bg-blue-500' :
                        booking.status === 'confirmed' ? 'bg-yellow-500' :
                        'bg-gray-400'
                      } border-2 border-white`}></div>
                      
                      <div className="bg-gray-50 p-3 rounded-lg hover:bg-gray-100 transition">
                        <div className="flex justify-between items-start mb-2">
                          <div>
                            <div className="font-semibold text-base">
                              {new Date(booking.check_in).toLocaleDateString('tr-TR', {
                                day: 'numeric',
                                month: 'long',
                                year: 'numeric'
                              })}
                            </div>
                            <div className="text-xs text-gray-600">
                              {nights} nights • Room {booking.room_number || '?'}
                            </div>
                          </div>
                          <Badge variant={
                            booking.status === 'checked_out' ? 'secondary' :
                            booking.status === 'checked_in' ? 'default' :
                            'outline'
                          }>
                            {booking.status}
                          </Badge>
                        </div>
                        
                        <div className="grid grid-cols-3 gap-2 text-xs">
                          <div>
                            <div className="text-gray-600">Total</div>
                            <div className="font-bold text-green-600">${booking.total_amount?.toFixed(2)}</div>
                          </div>
                          <div>
                            <div className="text-gray-600">ADR</div>
                            <div className="font-bold">${adr}</div>
                          </div>
                          <div>
                            <div className="text-gray-600">Channel</div>
                            <div className="font-bold capitalize">{booking.ota_channel || booking.channel || 'Direct'}</div>
                          </div>
                        </div>
                        
                        {booking.special_requests && (
                          <div className="mt-2 text-xs text-gray-600 italic">
                            💬 &quot;{booking.special_requests}&quot;
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="text-center text-gray-400 py-8">No booking history available</div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Channel Distribution - Enhanced with Pie Chart */}
        {guest360Data.stats?.channel_distribution && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Channel Distribution</CardTitle>
              <CardDescription>Booking sources breakdown</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4">
                {/* Pie Chart */}
                <div>
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart>
                      <Pie
                        data={Object.entries(guest360Data.stats.channel_distribution).map(([channel, count]) => ({
                          name: channel.charAt(0).toUpperCase() + channel.slice(1),
                          value: count
                        }))}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        label={({name, percent}) => `${name} ${(percent * 100).toFixed(0)}%`}
                        outerRadius={80}
                        fill="#8884d8"
                        dataKey="value"
                      >
                        {Object.keys(guest360Data.stats.channel_distribution).map((entry, index) => {
                          const colors = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899'];
                          return <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />;
                        })}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                
                {/* Stats */}
                <div className="flex flex-col justify-center gap-3">
                  {Object.entries(guest360Data.stats.channel_distribution).map(([channel, count], index) => {
                    const colors = ['bg-blue-500', 'bg-green-500', 'bg-orange-500', 'bg-purple-500', 'bg-pink-500'];
                    return (
                      <div key={channel} className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div className={`w-3 h-3 ${colors[index % colors.length]} rounded`}></div>
                          <span className="text-sm capitalize">{channel}</span>
                        </div>
                        <span className="font-bold">{count}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    ) : (
      <div className="text-center py-12 text-gray-500">
        Select a guest to view their 360° profile
      </div>
    )}
  </DialogContent>
</Dialog>


  );
};

export default Guest360Dialog;
