import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Slider } from './ui/slider';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { TrendingUp, DollarSign, Calendar, Target, Award } from 'lucide-react';

const RevenueManagementAdvanced = () => {
  const [activeTab, setActiveTab] = useState('pricing'); // pricing, heatmap, compset
  const [pricingData, setPricingData] = useState(null);
  const [heatmapData, setHeatmapData] = useState([]);
  const [compsetData, setCompsetData] = useState(null);
  const [selectedPrice, setSelectedPrice] = useState(100);
  const [roomType, setRoomType] = useState('Standard');
  const [checkInDate, setCheckInDate] = useState(new Date().toISOString().split('T')[0]);
  const [loading, setLoading] = useState(false);

  const fetchPricingRecommendation = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/rms/price-recommendation-slider?room_type=${roomType}&check_in_date=${checkInDate}`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setPricingData(data);
        setSelectedPrice(data.pricing_recommendation?.recommended_price || 100);
      }
    } catch (error) {
      console.error('Error fetching pricing:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchDemandHeatmap = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/rms/demand-heatmap`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setHeatmapData(data.heatmap_data || []);
      }
    } catch (error) {
      console.error('Error fetching heatmap:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchCompsetAnalysis = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/rms/compset-analysis`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setCompsetData(data);
      }
    } catch (error) {
      console.error('Error fetching compset:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'pricing') {
      fetchPricingRecommendation();
    } else if (activeTab === 'heatmap') {
      fetchDemandHeatmap();
    } else if (activeTab === 'compset') {
      fetchCompsetAnalysis();
    }
  }, [activeTab]);

  const getDemandColor = (level) => {
    const colors = {
      low: 'bg-green-200',
      medium: 'bg-yellow-200',
      high: 'bg-amber-200',
      very_high: 'bg-red-200'
    };
    return colors[level] || 'bg-gray-200';
  };

  const getDemandTextColor = (level) => {
    const colors = {
      low: 'text-green-800',
      medium: 'text-yellow-800',
      high: 'text-amber-800',
      very_high: 'text-red-800'
    };
    return colors[level] || 'text-gray-800';
  };

  return (
    <div className="space-y-4">
      {/* Tab Navigation */}
      <div className="flex gap-2 border-b">
        <Button
          variant={activeTab === 'pricing' ? 'default' : 'ghost'}
          onClick={() => setActiveTab('pricing')}
          className="rounded-b-none"
        >
          <DollarSign className="w-4 h-4 mr-2" />
          Price Optimizer
        </Button>
        <Button
          variant={activeTab === 'heatmap' ? 'default' : 'ghost'}
          onClick={() => setActiveTab('heatmap')}
          className="rounded-b-none"
        >
          <Calendar className="w-4 h-4 mr-2" />
          Demand Heatmap
        </Button>
        <Button
          variant={activeTab === 'compset' ? 'default' : 'ghost'}
          onClick={() => setActiveTab('compset')}
          className="rounded-b-none"
        >
          <Target className="w-4 h-4 mr-2" />
          CompSet Analysis
        </Button>
      </div>

      {/* Price Optimizer Tab */}
      {activeTab === 'pricing' && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Dynamic Pricing Recommendation</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>Room Type</Label>
                    <Input
                      value={roomType}
                      onChange={(e) => setRoomType(e.target.value)}
                      placeholder="e.g., Standard, Deluxe"
                    />
                  </div>
                  <div>
                    <Label>Check-in Date</Label>
                    <Input
                      type="date"
                      value={checkInDate}
                      onChange={(e) => setCheckInDate(e.target.value)}
                    />
                  </div>
                </div>
                <Button onClick={fetchPricingRecommendation} disabled={loading}>
                  {loading ? 'Loading...' : 'Get Recommendation'}
                </Button>

                {pricingData && (
                  <div className="space-y-6">
                    {/* Pricing Slider */}
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <Label>Recommended Price Range</Label>
                        <div className="text-2xl font-bold text-blue-600">
                          ${selectedPrice}
                        </div>
                      </div>
                      <Slider
                        value={[selectedPrice]}
                        onValueChange={(value) => setSelectedPrice(value[0])}
                        min={pricingData.pricing_recommendation?.min_price || 50}
                        max={pricingData.pricing_recommendation?.max_price || 200}
                        step={1}
                        className="w-full"
                      />
                      <div className="flex justify-between text-sm text-gray-600">
                        <span>Min: ${pricingData.pricing_recommendation?.min_price}</span>
                        <span className="font-semibold text-blue-600">
                          Recommended: ${pricingData.pricing_recommendation?.recommended_price}
                        </span>
                        <span>Max: ${pricingData.pricing_recommendation?.max_price}</span>
                      </div>
                    </div>

                    {/* Occupancy Analysis */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="bg-blue-50 p-4 rounded-lg">
                        <div className="text-sm text-gray-600 mb-1">Current Occupancy</div>
                        <div className="text-2xl font-bold text-blue-600">
                          {pricingData.occupancy_analysis?.current_occupancy_pct}%
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          {pricingData.occupancy_analysis?.current_bookings} / {pricingData.occupancy_analysis?.total_rooms} rooms
                        </div>
                      </div>
                      <div className="bg-green-50 p-4 rounded-lg">
                        <div className="text-sm text-gray-600 mb-1">Historical Occupancy</div>
                        <div className="text-2xl font-bold text-green-600">
                          {pricingData.occupancy_analysis?.historical_occupancy_pct}%
                        </div>
                        <div className="text-xs text-gray-500 mt-1">Last year same date</div>
                      </div>
                      <div className="bg-indigo-50 p-4 rounded-lg">
                        <div className="text-sm text-gray-600 mb-1">Base Price</div>
                        <div className="text-2xl font-bold text-indigo-600">
                          ${pricingData.base_price}
                        </div>
                        <div className="text-xs text-gray-500 mt-1">Standard rate</div>
                      </div>
                    </div>

                    {/* Recommendation Reason */}
                    <div className="bg-blue-50 border-l-4 border-blue-500 p-4">
                      <div className="flex items-start gap-2">
                        <TrendingUp className="w-5 h-5 text-blue-600 mt-0.5" />
                        <div>
                          <div className="font-semibold text-blue-900">Pricing Strategy</div>
                          <div className="text-sm text-blue-800 mt-1">
                            {pricingData.recommendation_reason}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Demand Heatmap Tab */}
      {activeTab === 'heatmap' && (
        <Card>
          <CardHeader>
            <CardTitle>90-Day Demand Forecast Heatmap</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="text-center py-8">Loading heatmap...</div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-7 gap-2">
                  {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(day => (
                    <div key={day} className="text-center text-sm font-medium text-gray-600">
                      {day}
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-7 gap-2">
                  {heatmapData.slice(0, 84).map((day, idx) => (
                    <div
                      key={idx}
                      className={`p-3 rounded-lg ${getDemandColor(day.demand_level)} text-center cursor-pointer hover:ring-2 hover:ring-blue-500 transition-all`}
                      title={`${day.date}: ${day.occupancy_pct}% occupancy (${day.bookings_count} bookings)`}
                    >
                      <div className="text-xs font-semibold">
                        {new Date(day.date).getDate()}
                      </div>
                      <div className={`text-xs ${getDemandTextColor(day.demand_level)}`}>
                        {day.occupancy_pct}%
                      </div>
                    </div>
                  ))}
                </div>
                <div className="flex items-center justify-center gap-4 pt-4 border-t">
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 rounded bg-green-200"></div>
                    <span className="text-sm">Low (0-30%)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 rounded bg-yellow-200"></div>
                    <span className="text-sm">Medium (30-60%)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 rounded bg-amber-200"></div>
                    <span className="text-sm">High (60-80%)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 rounded bg-red-200"></div>
                    <span className="text-sm">Very High (80%+)</span>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* CompSet Analysis Tab */}
      {activeTab === 'compset' && (
        <div className="space-y-4">
          {loading ? (
            <Card>
              <CardContent className="p-6 text-center">Loading competitor analysis...</CardContent>
            </Card>
          ) : compsetData && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Competitive Set Summary</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="bg-blue-50 p-4 rounded-lg">
                      <div className="text-sm text-gray-600 mb-1">Competitors</div>
                      <div className="text-2xl font-bold text-blue-600">
                        {compsetData.compset_summary?.total_competitors}
                      </div>
                    </div>
                    <div className="bg-green-50 p-4 rounded-lg">
                      <div className="text-sm text-gray-600 mb-1">Avg Rate</div>
                      <div className="text-2xl font-bold text-green-600">
                        ${compsetData.compset_summary?.avg_rate}
                      </div>
                    </div>
                    <div className="bg-indigo-50 p-4 rounded-lg">
                      <div className="text-sm text-gray-600 mb-1">Avg Occupancy</div>
                      <div className="text-2xl font-bold text-indigo-600">
                        {compsetData.compset_summary?.avg_occupancy_pct}%
                      </div>
                    </div>
                    <div className="bg-yellow-50 p-4 rounded-lg">
                      <div className="text-sm text-gray-600 mb-1">Avg Rating</div>
                      <div className="text-2xl font-bold text-yellow-600">
                        {compsetData.compset_summary?.avg_rating} ⭐
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Award className="w-5 h-5" />
                    Most Wanted Features
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {compsetData.most_wanted_features?.map((feature, idx) => (
                      <div key={idx} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center font-bold">
                            {idx + 1}
                          </div>
                          <span className="font-medium">{feature.feature}</span>
                        </div>
                        <div className="flex items-center gap-4">
                          <Badge variant="outline">
                            {feature.competitor_count} competitors
                          </Badge>
                          <div className="text-sm font-medium text-blue-600">
                            {feature.popularity_pct}%
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default RevenueManagementAdvanced;