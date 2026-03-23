import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Building2, Plus, Calendar, DollarSign, Users } from 'lucide-react';

const CorporateRatesModule = () => {
  const [contracts, setContracts] = useState([]);
  const [ratePlans, setRatePlans] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchContracts();
    fetchRatePlans();
  }, []);

  const fetchContracts = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/corporate/contracts`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const data = await response.json();
      setContracts(data.contracts || []);
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchRatePlans = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/corporate/rate-plans`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const data = await response.json();
      setRatePlans(data.rate_plans || []);
    } catch (error) {
      console.error('Error:', error);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Building2 className="w-8 h-8 text-blue-600" />
            Corporate Rates & Contracts
          </h1>
          <p className="text-gray-600">Manage corporate agreements and rate plans</p>
        </div>
        <Button>
          <Plus className="w-4 h-4 mr-2" />
          New Contract
        </Button>
      </div>

      {/* Active Contracts */}
      <Card>
        <CardHeader>
          <CardTitle>Active Corporate Contracts</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-8">Loading...</div>
          ) : (
            <div className="space-y-4">
              {contracts.map((contract, idx) => (
                <Card key={idx} className="border-l-4 border-l-blue-500">
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between">
                      <div className="space-y-2 flex-1">
                        <div className="flex items-center gap-3">
                          <h3 className="text-lg font-semibold">{contract.company_name}</h3>
                          <Badge className="bg-green-500">Active</Badge>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                          <div>
                            <div className="text-gray-600">Contract #</div>
                            <div className="font-semibold">{contract.contract_number}</div>
                          </div>
                          <div>
                            <div className="text-gray-600">Valid Period</div>
                            <div className="font-semibold">
                              {contract.valid_from} - {contract.valid_to}
                            </div>
                          </div>
                          <div>
                            <div className="text-gray-600">Discount</div>
                            <div className="font-semibold text-green-600">{contract.discount_percentage}%</div>
                          </div>
                          <div>
                            <div className="text-gray-600">Allotment</div>
                            <div className="font-semibold">{contract.allotment} rooms</div>
                          </div>
                        </div>
                        {contract.blackout_dates && contract.blackout_dates.length > 0 && (
                          <div className="mt-2">
                            <div className="text-sm text-gray-600">Blackout Dates:</div>
                            <div className="flex gap-2 flex-wrap mt-1">
                              {contract.blackout_dates.map((date, i) => (
                                <Badge key={i} variant="outline" className="bg-red-50 text-red-700">
                                  {date}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Rate Plans */}
      <Card>
        <CardHeader>
          <CardTitle>Corporate Rate Plans</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {ratePlans.map((plan, idx) => (
              <Card key={idx}>
                <CardContent className="p-4">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold">{plan.name}</h3>
                      <Badge variant="outline">{plan.room_type}</Badge>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-sm">
                      <div>
                        <div className="text-gray-600">Base Rate</div>
                        <div className="font-semibold">${plan.base_rate}</div>
                      </div>
                      <div>
                        <div className="text-gray-600">Discount</div>
                        <div className="font-semibold text-red-600">-{plan.discount}%</div>
                      </div>
                      <div>
                        <div className="text-gray-600">Net Rate</div>
                        <div className="font-semibold text-green-600">${plan.net_rate}</div>
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600">Valid Days:</div>
                      <div className="flex gap-1 flex-wrap mt-1">
                        {plan.valid_days?.map((day, i) => (
                          <Badge key={i} variant="outline" className="text-xs">
                            {day.slice(0, 3)}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default CorporateRatesModule;