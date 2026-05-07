import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, Star, Clock, Utensils, Dumbbell, Wifi } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const UpsellStore = ({ bookingId }) => {
  const { t } = useTranslation();
  const [offers, setOffers] = useState([]);
  const [purchasedItems, setPurchasedItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadOffers();
    loadPurchasedItems();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [bookingId]);

  const loadOffers = async () => {
    try {
      // First try new AI upsell products endpoint
      try {
        const response = await axios.get('/upsell/products');
        const products = response.data.products || [];
        // Convert to offer format
        const converted = products.map(p => ({
          id: p.id,
          title: p.name,
          description: p.description,
          price: p.price,
          type: p.category,
          image_url: p.image_url,
          popular: p.popular,
          ai_score: p.ai_score
        }));
        setOffers(converted);
        setLoading(false);
        return;
      } catch (_err) {
        // AI products not available — fall back to guest upsell endpoint below
      }
      
      // Fallback to original endpoint
      const response = await axios.get(`/guest/upsell-offers/${bookingId}`);
      setOffers(response.data.offers || []);
    } catch (error) {
      console.error('Failed to load offers:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadPurchasedItems = async () => {
    try {
      const response = await axios.get(`/guest/purchased-upsells/${bookingId}`);
      setPurchasedItems(response.data.items || []);
    } catch (error) {
      console.error('Failed to load purchased items');
    }
  };

  const handlePurchase = async (offer) => {
    try {
      await axios.post(`/guest/purchase-upsell/${bookingId}`, {
        offer_id: offer.id,
        offer_type: offer.type,
        amount: offer.price
      });
      
      toast.success(`${offer.title} added to your booking!`);
      loadOffers();
      loadPurchasedItems();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Purchase failed');
    }
  };

  const getOfferIcon = (type) => {
    switch (type) {
      case 'room_upgrade':
        return <Star className="w-5 h-5 text-yellow-500" />;
      case 'early_checkin':
      case 'late_checkout':
        return <Clock className="w-5 h-5 text-blue-500" />;
      case 'breakfast':
      case 'dinner':
        return <Utensils className="w-5 h-5 text-green-500" />;
      case 'spa':
      case 'gym':
        return <Dumbbell className="w-5 h-5 text-indigo-500" />;
      case 'wifi_upgrade':
        return <Wifi className="w-5 h-5 text-cyan-500" />;
      default:
        return <TrendingUp className="w-5 h-5 text-gray-500" />;
    }
  };

  const isPurchased = (offerId) => {
    return purchasedItems.some(item => item.offer_id === offerId);
  };

  if (loading) {
    return (
      <div className="text-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <div>
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <TrendingUp className="w-6 h-6" />
          Enhance Your Stay
        </h2>
        <p className="text-gray-600 mt-1">Exclusive offers just for you</p>
      </div>

      {/* Purchased Items */}
      {purchasedItems.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Your Purchases</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {purchasedItems.map((item, index) => (
                <div key={index} className="flex justify-between items-center p-3 bg-green-50 rounded">
                  <div className="flex items-center gap-3">
                    {getOfferIcon(item.type)}
                    <div>
                      <div className="font-semibold">{item.title}</div>
                      <div className="text-sm text-gray-600">{item.description}</div>
                    </div>
                  </div>
                  <Badge className="bg-green-100 text-green-700 hover:bg-green-100">Purchased</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Available Offers */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {offers.map((offer) => {
          const purchased = isPurchased(offer.id);
          
          return (
            <Card key={offer.id} className={purchased ? 'opacity-50' : 'hover:shadow-lg transition'}>
              <CardContent className="pt-6">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    {getOfferIcon(offer.type)}
                    <div>
                      <h3 className="font-bold text-lg">{offer.title}</h3>
                      {(offer.ai_recommended || offer.ai_score) && (
                        <Badge className="mt-1 bg-indigo-100 text-indigo-700 hover:bg-indigo-100">
                          🤖 AI Score: {offer.ai_score ? `${(offer.ai_score * 100).toFixed(0)}%` : 'Recommended'}
                        </Badge>
                      )}
                      {offer.popular && (
                        <Badge className="mt-1 ml-1 bg-amber-100 text-amber-700 hover:bg-amber-100">
                          🔥 Popular
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-blue-600">${offer.price}</div>
                    {offer.original_price && offer.original_price > offer.price && (
                      <div className="text-sm text-gray-500 line-through">${offer.original_price}</div>
                    )}
                  </div>
                </div>

                <p className="text-gray-600 text-sm mb-4">{offer.description}</p>

                {offer.features && offer.features.length > 0 && (
                  <ul className="text-sm space-y-1 mb-4">
                    {offer.features.map((feature, index) => (
                      <li key={index} className="flex items-center gap-2">
                        <span className="text-green-600">✓</span>
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                )}

                {offer.limited_availability && (
                  <div className="bg-amber-50 text-amber-700 text-xs p-2 rounded mb-4">
                    ⚡ Limited availability - Only {offer.available_count} left!
                  </div>
                )}

                <Button
                  onClick={() => handlePurchase(offer)}
                  disabled={purchased}
                  className="w-full"
                >
                  {purchased ? 'Already Purchased' : 'Add to Booking'}
                </Button>

                {offer.confidence && (
                  <div className="text-xs text-gray-500 text-center mt-2">
                    {(offer.confidence * 100).toFixed(0)}% match based on your preferences
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {offers.length === 0 && (
        <Card>
          <CardContent className="text-center py-12">
            <TrendingUp className="w-16 h-16 mx-auto text-gray-400 mb-4" />
            <p className="text-gray-600">No offers available at this time</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default UpsellStore;