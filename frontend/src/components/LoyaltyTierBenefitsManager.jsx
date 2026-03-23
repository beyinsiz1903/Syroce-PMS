import React, { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Award, Coffee, Clock, TrendingUp, Gift, Save } from 'lucide-react';

/**
 * Loyalty Tier Benefits Manager
 * Configure benefits for each loyalty tier (Silver, Gold, Platinum)
 * Example: Gold → Free breakfast, Late checkout, Room upgrade
 */
const LoyaltyTierBenefitsManager = () => {
  const [tiers, setTiers] = useState([
    {
      name: 'Silver',
      color: 'gray',
      icon: '🥈',
      benefits: {
        free_breakfast: false,
        late_checkout: false,
        late_checkout_hours: 0,
        room_upgrade: false,
        welcome_gift: false,
        priority_checkin: false,
        bonus_points_multiplier: 1
      }
    },
    {
      name: 'Gold',
      color: 'yellow',
      icon: '🥇',
      benefits: {
        free_breakfast: true,
        late_checkout: true,
        late_checkout_hours: 2,
        room_upgrade: false,
        welcome_gift: true,
        priority_checkin: true,
        bonus_points_multiplier: 1.5
      }
    },
    {
      name: 'Platinum',
      color: 'purple',
      icon: '💎',
      benefits: {
        free_breakfast: true,
        late_checkout: true,
        late_checkout_hours: 4,
        room_upgrade: true,
        welcome_gift: true,
        priority_checkin: true,
        bonus_points_multiplier: 2
      }
    }
  ]);
  const [loading, setLoading] = useState(false);

  const updateBenefit = (tierName, benefitKey, value) => {
    setTiers(tiers.map(tier => 
      tier.name === tierName
        ? {
            ...tier,
            benefits: {
              ...tier.benefits,
              [benefitKey]: value
            }
          }
        : tier
    ));
  };

  const saveBenefits = async () => {
    setLoading(true);
    try {
      await axios.post('/loyalty/tier-benefits/update', { tiers });
      toast.success('Loyalty tier benefits saved!');
    } catch (error) {
      toast.error('Failed to save benefits');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="border-2 border-yellow-300">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Award className="w-5 h-5 text-yellow-600" />
            Loyalty Tier Benefits Manager
          </CardTitle>
          <CardDescription>
            Configure benefits for each loyalty tier - What does Gold member get?
          </CardDescription>
        </CardHeader>
      </Card>

      {/* Tier Cards */}
      <div className="grid grid-cols-3 gap-4">
        {tiers.map((tier) => (
          <Card key={tier.name} className={`border-2 border-${tier.color}-300`}>
            <CardHeader className={`bg-${tier.color}-50 pb-3`}>
              <CardTitle className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-2xl">{tier.icon}</span>
                  <span>{tier.name}</span>
                </div>
                <Badge className={`bg-${tier.color}-500`}>Tier</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 pt-4">
              {/* Free Breakfast */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Coffee className="w-4 h-4 text-gray-600" />
                  <span className="text-sm">Free Breakfast</span>
                </div>
                <Switch
                  checked={tier.benefits.free_breakfast}
                  onCheckedChange={(checked) => updateBenefit(tier.name, 'free_breakfast', checked)}
                />
              </div>

              {/* Late Checkout */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Clock className="w-4 h-4 text-gray-600" />
                    <span className="text-sm">Late Checkout</span>
                  </div>
                  <Switch
                    checked={tier.benefits.late_checkout}
                    onCheckedChange={(checked) => updateBenefit(tier.name, 'late_checkout', checked)}
                  />
                </div>
                {tier.benefits.late_checkout && (
                  <div className="ml-6">
                    <label className="text-xs text-gray-600">Hours:</label>
                    <Input
                      type="number"
                      value={tier.benefits.late_checkout_hours}
                      onChange={(e) => updateBenefit(tier.name, 'late_checkout_hours', parseInt(e.target.value))}
                      className="w-20 h-8 text-sm"
                      min={0}
                      max={6}
                    />
                  </div>
                )}
              </div>

              {/* Room Upgrade */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-gray-600" />
                  <span className="text-sm">Room Upgrade</span>
                </div>
                <Switch
                  checked={tier.benefits.room_upgrade}
                  onCheckedChange={(checked) => updateBenefit(tier.name, 'room_upgrade', checked)}
                />
              </div>

              {/* Welcome Gift */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Gift className="w-4 h-4 text-gray-600" />
                  <span className="text-sm">Welcome Gift</span>
                </div>
                <Switch
                  checked={tier.benefits.welcome_gift}
                  onCheckedChange={(checked) => updateBenefit(tier.name, 'welcome_gift', checked)}
                />
              </div>

              {/* Priority Check-in */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Award className="w-4 h-4 text-gray-600" />
                  <span className="text-sm">Priority Check-in</span>
                </div>
                <Switch
                  checked={tier.benefits.priority_checkin}
                  onCheckedChange={(checked) => updateBenefit(tier.name, 'priority_checkin', checked)}
                />
              </div>

              {/* Bonus Points Multiplier */}
              <div className="space-y-2">
                <label className="text-sm font-semibold">Points Multiplier:</label>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    value={tier.benefits.bonus_points_multiplier}
                    onChange={(e) => updateBenefit(tier.name, 'bonus_points_multiplier', parseFloat(e.target.value))}
                    className="w-20 h-8 text-sm"
                    min={1}
                    max={5}
                    step={0.5}
                  />
                  <span className="text-xs text-gray-600">x points</span>
                </div>
              </div>

              {/* Summary */}
              <div className="mt-4 pt-3 border-t bg-gray-50 -mx-4 -mb-4 p-3 rounded-b">
                <div className="text-xs text-gray-600">
                  <strong>Active Benefits:</strong>
                  <div className="mt-1">
                    {Object.entries(tier.benefits).filter(([key, value]) => 
                      typeof value === 'boolean' && value
                    ).length} benefits enabled
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Save Button */}
      <Button
        onClick={saveBenefits}
        disabled={loading}
        className="w-full bg-yellow-600 hover:bg-yellow-700"
      >
        <Save className="w-4 h-4 mr-2" />
        {loading ? 'Saving...' : 'Save All Tier Benefits'}
      </Button>

      {/* Info Banner */}
      <Card className="bg-blue-50 border-blue-200">
        <CardContent className="p-4">
          <div className="text-sm text-blue-900">
            <strong>💡 Pro Tip:</strong> These benefits are automatically applied when guest books.
            Arrivals screen shows "VIP / Loyalty Gold" tags. Messaging Center sends auto-congratulation
            when guest upgrades tier.
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default LoyaltyTierBenefitsManager;
