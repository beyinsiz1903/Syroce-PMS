import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Building2, Plus } from 'lucide-react';

const AllotmentGrid = () => {
  const [contracts, setContracts] = useState([]);
  const [showDialog, setShowDialog] = useState(false);
  const [formData, setFormData] = useState({
    tour_operator: '',
    room_type: 'standard',
    allocated_rooms: 0,
    start_date: '',
    end_date: '',
    rate: 0,
    release_days: 7
  });

  useEffect(() => {
    loadContracts();
  }, []);

  const loadContracts = async () => {
    try {
      const response = await axios.get('/pms/allotment-contracts');
      setContracts(response.data);
    } catch (error) {
      console.error('Failed to load contracts:', error);
    }
  };

  const createContract = async () => {
    try {
      await axios.post('/pms/allotment-contracts', formData);
      toast.success('Contract created successfully');
      loadContracts();
      setShowDialog(false);
      setFormData({
        tour_operator: '',
        room_type: 'standard',
        allocated_rooms: 0,
        start_date: '',
        end_date: '',
        rate: 0,
        release_days: 7
      });
    } catch (error) {
      toast.error('Failed to create contract');
    }
  };

  const releaseRooms = async (contractId) => {
    try {
      await axios.post(`/pms/allotment-contracts/${contractId}/release`);
      toast.success('Rooms released successfully');
      loadContracts();
    } catch (error) {
      toast.error('Failed to release rooms');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-2xl font-bold">Allotment & Tour Operator Contracts</h3>
          <p className="text-gray-600">Manage room allocations for tour operators</p>
        </div>
        <Button onClick={() => setShowDialog(true)}>
          <Plus className="w-4 h-4 mr-2" />
          New Contract
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {contracts.map((contract) => (
          <Card key={contract.id} className="hover:shadow-lg transition">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Building2 className="w-5 h-5 text-purple-500" />
                <CardTitle className="text-lg">{contract.tour_operator}</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">Room Type:</span>
                  <span className="font-semibold capitalize">{contract.room_type}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Allocated:</span>
                  <span className="font-semibold">{contract.allocated_rooms} rooms</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Used:</span>
                  <span className="font-semibold">{contract.used_rooms || 0} rooms</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Available:</span>
                  <span className="font-semibold text-green-600">
                    {contract.allocated_rooms - (contract.used_rooms || 0)} rooms
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Rate:</span>
                  <span className="font-semibold">${contract.rate}/night</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Period:</span>
                  <span className="text-xs">
                    {new Date(contract.start_date).toLocaleDateString()} - {new Date(contract.end_date).toLocaleDateString()}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Release Days:</span>
                  <span className="font-semibold">{contract.release_days} days</span>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="w-full mt-2"
                  onClick={() => releaseRooms(contract.id)}
                  disabled={(contract.allocated_rooms - (contract.used_rooms || 0)) === 0}
                >
                  Release Unused Rooms
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Allotment Contract</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Tour Operator Name</Label>
              <Input
                value={formData.tour_operator}
                onChange={(e) => setFormData({ ...formData, tour_operator: e.target.value })}
                placeholder="TUI, Thomas Cook, etc."
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Room Type</Label>
                <Input
                  value={formData.room_type}
                  onChange={(e) => setFormData({ ...formData, room_type: e.target.value })}
                  placeholder="standard, deluxe, suite"
                />
              </div>
              <div>
                <Label>Allocated Rooms</Label>
                <Input
                  type="number"
                  value={formData.allocated_rooms}
                  onChange={(e) => setFormData({ ...formData, allocated_rooms: parseInt(e.target.value) })}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Start Date</Label>
                <Input
                  type="date"
                  value={formData.start_date}
                  onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                />
              </div>
              <div>
                <Label>End Date</Label>
                <Input
                  type="date"
                  value={formData.end_date}
                  onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Contracted Rate ($)</Label>
                <Input
                  type="number"
                  value={formData.rate}
                  onChange={(e) => setFormData({ ...formData, rate: parseFloat(e.target.value) })}
                />
              </div>
              <div>
                <Label>Release Days</Label>
                <Input
                  type="number"
                  value={formData.release_days}
                  onChange={(e) => setFormData({ ...formData, release_days: parseInt(e.target.value) })}
                  placeholder="7"
                />
              </div>
            </div>

            <Button onClick={createContract} className="w-full">Create Contract</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AllotmentGrid;