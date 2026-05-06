import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { TrendingUp, DollarSign, Target, BarChart3, PieChart, Award } from 'lucide-react';

const ComprehensiveReportsModule = () => {
  const [menuEngineering, setMenuEngineering] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [compsetPrices, setCompsetPrices] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMenuEngineering();
    fetchCampaigns();
    fetchCompsetPrices();
  }, []);

  const fetchMenuEngineering = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/pos/menu-engineering`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const data = await response.json();
      setMenuEngineering(data);
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchCampaigns = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/marketing/campaigns`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const data = await response.json();
      setCampaigns(data.campaigns || []);
    } catch (error) {
      console.error('Error:', error);
    }
  };

  const fetchCompsetPrices = async () => {
    try {
      const token = localStorage.getItem('token');
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const response = await fetch(
        `/api/rms/compset/real-time-prices?check_in_date=${tomorrow.toISOString().split('T')[0]}&room_type=Standard`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const data = await response.json();
      setCompsetPrices(data);
    } catch (error) {
      console.error('Error:', error);
    }
  };

  const getCategoryColor = (category) => {
    const colors = {
      'Stars': 'bg-green-100 text-green-800',
      'Plowhorses': 'bg-yellow-100 text-yellow-800',
      'Puzzles': 'bg-blue-100 text-blue-800',
      'Dogs': 'bg-red-100 text-red-800'
    };
    return colors[category] || 'bg-gray-100 text-gray-800';
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-2">
          <BarChart3 className="w-8 h-8 text-blue-600" />
          Comprehensive Reports
        </h1>
        <p className="text-gray-600">Advanced analytics and insights</p>
      </div>

      <Tabs defaultValue="menu" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="menu">
            <PieChart className="w-4 h-4 mr-2" />
            Menu Engineering
          </TabsTrigger>
          <TabsTrigger value="campaigns">
            <Target className="w-4 h-4 mr-2" />
            Campaign ROI
          </TabsTrigger>
          <TabsTrigger value="compset">
            <TrendingUp className="w-4 h-4 mr-2" />
            CompSet Prices
          </TabsTrigger>
        </TabsList>

        {/* Menu Engineering Tab */}
        <TabsContent value="menu">
          <Card>
            <CardHeader>
              <CardTitle>Menu Engineering Matrix</CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="text-center py-8">Loading...</div>
              ) : (
                <div>
                  <div className="grid grid-cols-4 gap-4 mb-6">
                    <Card className="bg-green-50">
                      <CardContent className="p-4 text-center">
                        <div className="text-2xl font-bold text-green-600">{menuEngineering?.stars || 0}</div>
                        <div className="text-sm">Stars</div>
                      </CardContent>
                    </Card>
                    <Card className="bg-yellow-50">
                      <CardContent className="p-4 text-center">
                        <div className="text-2xl font-bold text-yellow-600">{menuEngineering?.plowhorses || 0}</div>
                        <div className="text-sm">Plowhorses</div>
                      </CardContent>
                    </Card>
                    <Card className="bg-blue-50">
                      <CardContent className="p-4 text-center">
                        <div className="text-2xl font-bold text-blue-600">{menuEngineering?.puzzles || 0}</div>
                        <div className="text-sm">Puzzles</div>
                      </CardContent>
                    </Card>
                    <Card className="bg-red-50">
                      <CardContent className="p-4 text-center">
                        <div className="text-2xl font-bold text-red-600">{menuEngineering?.dogs || 0}</div>
                        <div className="text-sm">Dogs</div>
                      </CardContent>
                    </Card>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left p-3">Item</th>
                          <th className="text-left p-3">Category</th>
                          <th className="text-right p-3">Qty Sold</th>
                          <th className="text-right p-3">Revenue</th>
                          <th className="text-right p-3">Margin</th>
                          <th className="text-left p-3">Recommendation</th>
                        </tr>
                      </thead>
                      <tbody>
                        {menuEngineering?.menu_items?.map((item, idx) => (
                          <tr key={idx} className="border-b hover:bg-gray-50">
                            <td className="p-3 font-medium">{item.item_name}</td>
                            <td className="p-3">
                              <Badge className={getCategoryColor(item.category)}>
                                {item.category}
                              </Badge>
                            </td>
                            <td className="p-3 text-right">{item.quantity_sold}</td>
                            <td className="p-3 text-right">${item.revenue.toFixed(2)}</td>
                            <td className="p-3 text-right">
                              <span className={item.profit_margin > 50 ? 'text-green-600' : 'text-red-600'}>
                                {item.profit_margin}%
                              </span>
                            </td>
                            <td className="p-3 text-sm">{item.recommendation}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Campaign ROI Tab */}
        <TabsContent value="campaigns">
          <Card>
            <CardHeader>
              <CardTitle>Marketing Campaign Performance</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {campaigns.map((campaign, idx) => (
                  <Card key={idx} className="border-l-4 border-l-blue-500">
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between">
                        <div className="space-y-2 flex-1">
                          <div className="flex items-center gap-3">
                            <h3 className="text-lg font-semibold">{campaign.campaign_name}</h3>
                            <Badge className={campaign.status === 'active' ? 'bg-green-500' : 'bg-gray-500'}>
                              {campaign.status}
                            </Badge>
                          </div>
                          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
                            <div>
                              <div className="text-gray-600">Budget</div>
                              <div className="font-semibold">${campaign.budget.toFixed(2)}</div>
                            </div>
                            <div>
                              <div className="text-gray-600">Bookings</div>
                              <div className="font-semibold">{campaign.bookings_generated}</div>
                            </div>
                            <div>
                              <div className="text-gray-600">Revenue</div>
                              <div className="font-semibold text-green-600">${campaign.revenue_generated.toFixed(2)}</div>
                            </div>
                            <div>
                              <div className="text-gray-600">Cost/Booking</div>
                              <div className="font-semibold">${campaign.cost_per_booking.toFixed(2)}</div>
                            </div>
                            <div>
                              <div className="text-gray-600">ROI</div>
                              <div className="font-semibold text-blue-600">{campaign.roi_percentage}%</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* CompSet Prices Tab */}
        <TabsContent value="compset">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Real-Time Competitor Prices</CardTitle>
                <Button onClick={fetchCompsetPrices} size="sm">
                  Refresh Prices
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {compsetPrices && (
                <div className="space-y-6">
                  <div className="grid grid-cols-3 gap-4">
                    <Card className="bg-blue-50">
                      <CardContent className="p-4">
                        <div className="text-sm text-gray-600">Your Price</div>
                        <div className="text-3xl font-bold text-blue-600">${compsetPrices.your_price}</div>
                      </CardContent>
                    </Card>
                    <Card className="bg-green-50">
                      <CardContent className="p-4">
                        <div className="text-sm text-gray-600">Market Position</div>
                        <div className="text-xl font-bold text-green-600 capitalize">{compsetPrices.market_position}</div>
                      </CardContent>
                    </Card>
                    <Card className="bg-indigo-50">
                      <CardContent className="p-4">
                        <div className="text-sm text-gray-600">Check-in Date</div>
                        <div className="text-lg font-semibold">{compsetPrices.check_in_date}</div>
                      </CardContent>
                    </Card>
                  </div>

                  <div className="bg-blue-50 border-l-4 border-blue-500 p-4">
                    <div className="font-semibold text-blue-900">Recommendation</div>
                    <div className="text-sm text-blue-800 mt-1">{compsetPrices.recommended_action}</div>
                  </div>

                  <table className="w-full">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left p-3">Competitor</th>
                        <th className="text-right p-3">Price</th>
                        <th className="text-left p-3">Availability</th>
                        <th className="text-left p-3">Source</th>
                        <th className="text-left p-3">Updated</th>
                      </tr>
                    </thead>
                    <tbody>
                      {compsetPrices.competitor_prices?.map((comp, idx) => (
                        <tr key={idx} className="border-b hover:bg-gray-50">
                          <td className="p-3 font-medium">{comp.competitor}</td>
                          <td className="p-3 text-right">
                            <span className={comp.price > compsetPrices.your_price ? 'text-red-600' : 'text-green-600'}>
                              ${comp.price.toFixed(2)}
                            </span>
                          </td>
                          <td className="p-3">
                            <Badge variant="outline">{comp.availability}</Badge>
                          </td>
                          <td className="p-3 text-sm">{comp.source}</td>
                          <td className="p-3 text-sm text-gray-600">{comp.last_updated}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default ComprehensiveReportsModule;