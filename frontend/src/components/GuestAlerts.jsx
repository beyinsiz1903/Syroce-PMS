import React from 'react';
import { Badge } from '@/components/ui/badge';
import { Star, Cake, AlertCircle, Gift } from 'lucide-react';

/**
 * Guest Alerts Component
 * Shows VIP, Birthday, Special Request badges prominently
 */
const GuestAlerts = ({ guest, booking }) => {
  const alerts = [];
  
  // VIP Check
  if (guest?.vip || guest?.loyalty_tier === 'gold' || guest?.loyalty_tier === 'platinum') {
    alerts.push({
      type: 'vip',
      icon: Star,
      label: guest?.loyalty_tier ? `${guest.loyalty_tier.toUpperCase()} VIP` : 'VIP',
      color: 'bg-yellow-500'
    });
  }
  
  // Birthday Check
  if (guest?.birthday) {
    const today = new Date().toISOString().split('T')[0].slice(5); // MM-DD
    const birthday = guest.birthday.slice(5); // MM-DD
    if (today === birthday) {
      alerts.push({
        type: 'birthday',
        icon: Cake,
        label: 'Birthday Today! 🎂',
        color: 'bg-pink-500'
      });
    }
  }
  
  // Special Requests
  if (booking?.special_requests && booking.special_requests.length > 0) {
    alerts.push({
      type: 'special_request',
      icon: AlertCircle,
      label: `${booking.special_requests.length} Special Request${booking.special_requests.length > 1 ? 's' : ''}`,
      color: 'bg-orange-500'
    });
  }
  
  // Honeymoon
  if (booking?.tags?.includes('honeymoon') || booking?.occasion === 'honeymoon') {
    alerts.push({
      type: 'honeymoon',
      icon: Gift,
      label: 'Honeymoon 💑',
      color: 'bg-red-500'
    });
  }
  
  if (alerts.length === 0) return null;
  
  return (
    <div className="flex flex-wrap gap-2">
      {alerts.map((alert, idx) => {
        const Icon = alert.icon;
        return (
          <Badge key={idx} className={`${alert.color} text-white flex items-center gap-1`}>
            <Icon className="w-3 h-3" />
            {alert.label}
          </Badge>
        );
      })}
    </div>
  );
};

export default GuestAlerts;
