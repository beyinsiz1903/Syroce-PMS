import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { User, History, Settings, Tag, Star, AlertTriangle, Calendar } from 'lucide-react';

const GuestProfileComplete = ({ guestId }) => {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editingPreferences, setEditingPreferences] = useState(false);
  const [preferences, setPreferences] = useState({});
  const [selectedTags, setSelectedTags] = useState([]);

  const availableTags = [
    { value: 'vip', label: 'VIP', color: 'bg-yellow-500', icon: Star },
    { value: 'blacklist', label: 'Blacklist', color: 'bg-red-500', icon: AlertTriangle },
    { value: 'honeymoon', label: 'Honeymoon', color: 'bg-pink-500', icon: Calendar },
    { value: 'anniversary', label: 'Anniversary', color: 'bg-indigo-500', icon: Calendar },
    { value: 'business_traveler', label: 'Business', color: 'bg-blue-500', icon: User },
    { value: 'frequent_guest', label: 'Frequent', color: 'bg-green-500', icon: History },
    { value: 'complainer', label: 'Complainer', color: 'bg-amber-500', icon: AlertTriangle },
    { value: 'high_spender', label: 'High Spender', color: 'bg-indigo-500', icon: Star }
  ];

  useEffect(() => {
    if (guestId) {
      fetchGuestProfile();
    }
  }, [guestId]);

  const fetchGuestProfile = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/guests/${guestId}/profile-complete`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setProfile(data);
        setPreferences(data.preferences || {});
        setSelectedTags(data.tags || []);
      }
    } catch (error) {
      console.error('Error fetching guest profile:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdatePreferences = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/guests/${guestId}/preferences`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(preferences)
        }
      );

      if (response.ok) {
        setEditingPreferences(false);
        fetchGuestProfile();
      }
    } catch (error) {
      console.error('Error updating preferences:', error);
    }
  };

  const handleUpdateTags = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/guests/${guestId}/tags`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ tags: selectedTags })
        }
      );

      if (response.ok) {
        fetchGuestProfile();
      }
    } catch (error) {
      console.error('Error updating tags:', error);
    }
  };

  const toggleTag = (tagValue) => {
    if (selectedTags.includes(tagValue)) {
      setSelectedTags(selectedTags.filter(t => t !== tagValue));
    } else {
      setSelectedTags([...selectedTags, tagValue]);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!profile) return <div>Guest not found</div>;

  return (
    <div className="space-y-6">
      {/* Guest Header */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-start justify-between">
            <div className="space-y-2">
              <h2 className="text-2xl font-bold">{profile.guest?.name}</h2>
              <div className="flex items-center gap-4 text-sm text-gray-600">
                <span>{profile.guest?.email}</span>
                <span>{profile.guest?.phone}</span>
                <span>Nationality: {profile.guest?.nationality || 'N/A'}</span>
              </div>
              <div className="flex items-center gap-2 mt-2">
                {profile.vip_status && (
                  <Badge className="bg-yellow-500">
                    <Star className="w-3 h-3 mr-1" /> VIP
                  </Badge>
                )}
                {profile.blacklist_status && (
                  <Badge className="bg-red-500">
                    <AlertTriangle className="w-3 h-3 mr-1" /> Blacklist
                  </Badge>
                )}
              </div>
            </div>
            <div className="text-right space-y-1">
              <div className="text-3xl font-bold text-blue-600">{profile.total_stays}</div>
              <div className="text-sm text-gray-600">Total Stays</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs defaultValue="history" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="history">
            <History className="w-4 h-4 mr-2" />
            Stay History
          </TabsTrigger>
          <TabsTrigger value="preferences">
            <Settings className="w-4 h-4 mr-2" />
            Preferences
          </TabsTrigger>
          <TabsTrigger value="tags">
            <Tag className="w-4 h-4 mr-2" />
            Tags
          </TabsTrigger>
        </TabsList>

        {/* Stay History Tab */}
        <TabsContent value="history">
          <Card>
            <CardHeader>
              <CardTitle>Complete Stay History</CardTitle>
            </CardHeader>
            <CardContent>
              {profile.stay_history && profile.stay_history.length > 0 ? (
                <div className="space-y-3">
                  {profile.stay_history.map((stay, idx) => (
                    <div key={idx} className="border rounded-lg p-4 hover:shadow-md transition-shadow">
                      <div className="flex items-start justify-between">
                        <div className="space-y-1">
                          <div className="flex items-center gap-3">
                            <div className="font-semibold">Room {stay.room_number}</div>
                            <Badge variant="outline">{stay.room_type}</Badge>
                            <Badge className={stay.status === 'checked_out' ? 'bg-gray-500' : 'bg-green-500'}>
                              {stay.status}
                            </Badge>
                          </div>
                          <div className="text-sm text-gray-600">
                            {new Date(stay.check_in).toLocaleDateString()} - {new Date(stay.check_out).toLocaleDateString()}
                          </div>
                          <div className="text-sm text-gray-600">
                            {stay.nights} night{stay.nights !== 1 ? 's' : ''}
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-lg font-bold">${stay.total_amount}</div>
                          <div className="text-xs text-gray-600">Total</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center text-gray-500 py-8">No stay history</div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Preferences Tab */}
        <TabsContent value="preferences">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Guest Preferences</CardTitle>
                <Button
                  onClick={() => editingPreferences ? handleUpdatePreferences() : setEditingPreferences(true)}
                  variant={editingPreferences ? 'default' : 'outline'}
                >
                  {editingPreferences ? 'Save' : 'Edit'}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label>Pillow Type</Label>
                  {editingPreferences ? (
                    <Select
                      value={preferences.pillow_type || ''}
                      onValueChange={(value) => setPreferences({ ...preferences, pillow_type: value })}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select pillow type" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="soft">Soft</SelectItem>
                        <SelectItem value="firm">Firm</SelectItem>
                        <SelectItem value="extra_firm">Extra Firm</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <div className="p-2 bg-gray-50 rounded">{preferences.pillow_type || 'Not specified'}</div>
                  )}
                </div>

                <div>
                  <Label>Floor Preference</Label>
                  {editingPreferences ? (
                    <Select
                      value={preferences.floor_preference || ''}
                      onValueChange={(value) => setPreferences({ ...preferences, floor_preference: value })}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select floor preference" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="low">Low Floors</SelectItem>
                        <SelectItem value="middle">Middle Floors</SelectItem>
                        <SelectItem value="high">High Floors</SelectItem>
                        <SelectItem value="no_preference">No Preference</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <div className="p-2 bg-gray-50 rounded">{preferences.floor_preference || 'Not specified'}</div>
                  )}
                </div>

                <div>
                  <Label>Room Temperature</Label>
                  {editingPreferences ? (
                    <Select
                      value={preferences.room_temperature || ''}
                      onValueChange={(value) => setPreferences({ ...preferences, room_temperature: value })}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select temperature" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="cool">Cool</SelectItem>
                        <SelectItem value="moderate">Moderate</SelectItem>
                        <SelectItem value="warm">Warm</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <div className="p-2 bg-gray-50 rounded">{preferences.room_temperature || 'Not specified'}</div>
                  )}
                </div>

                <div>
                  <Label>Smoking</Label>
                  {editingPreferences ? (
                    <Select
                      value={preferences.smoking ? 'yes' : 'no'}
                      onValueChange={(value) => setPreferences({ ...preferences, smoking: value === 'yes' })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="yes">Yes</SelectItem>
                        <SelectItem value="no">No</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <div className="p-2 bg-gray-50 rounded">{preferences.smoking ? 'Yes' : 'No'}</div>
                  )}
                </div>

                <div className="md:col-span-2">
                  <Label>Special Needs</Label>
                  {editingPreferences ? (
                    <Input
                      value={preferences.special_needs || ''}
                      onChange={(e) => setPreferences({ ...preferences, special_needs: e.target.value })}
                      placeholder="e.g., wheelchair accessible, extra towels"
                    />
                  ) : (
                    <div className="p-2 bg-gray-50 rounded">{preferences.special_needs || 'Not specified'}</div>
                  )}
                </div>

                <div className="md:col-span-2">
                  <Label>Dietary Restrictions</Label>
                  {editingPreferences ? (
                    <Input
                      value={preferences.dietary_restrictions || ''}
                      onChange={(e) => setPreferences({ ...preferences, dietary_restrictions: e.target.value })}
                      placeholder="e.g., vegetarian, gluten-free, halal"
                    />
                  ) : (
                    <div className="p-2 bg-gray-50 rounded">{preferences.dietary_restrictions || 'Not specified'}</div>
                  )}
                </div>

                <div className="md:col-span-2">
                  <Label>Newspaper Preference</Label>
                  {editingPreferences ? (
                    <Input
                      value={preferences.newspaper_preference || ''}
                      onChange={(e) => setPreferences({ ...preferences, newspaper_preference: e.target.value })}
                      placeholder="e.g., Wall Street Journal, Financial Times"
                    />
                  ) : (
                    <div className="p-2 bg-gray-50 rounded">{preferences.newspaper_preference || 'Not specified'}</div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tags Tab */}
        <TabsContent value="tags">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Guest Tags</CardTitle>
                <Button onClick={handleUpdateTags}>Save Tags</Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {availableTags.map((tag) => {
                  const Icon = tag.icon;
                  const isSelected = selectedTags.includes(tag.value);
                  return (
                    <button
                      key={tag.value}
                      onClick={() => toggleTag(tag.value)}
                      className={`p-4 rounded-lg border-2 transition-all ${
                        isSelected
                          ? `${tag.color} text-white border-transparent`
                          : 'bg-white border-gray-200 hover:border-gray-400'
                      }`}
                    >
                      <Icon className="w-6 h-6 mx-auto mb-2" />
                      <div className="text-sm font-medium">{tag.label}</div>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default GuestProfileComplete;