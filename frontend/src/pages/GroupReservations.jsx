import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Users, Plus, Calendar, Home, Building2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const GroupReservations = () => {
  const { t } = useTranslation();
  const [groups, setGroups] = useState([]);
  const [blocks, setBlocks] = useState([]);
  const [showDialog, setShowDialog] = useState(false);
  const [dialogType, setDialogType] = useState('group'); // 'group' or 'block'
  const [formData, setFormData] = useState({
    group_name: '',
    contact_person: '',
    contact_email: '',
    contact_phone: '',
    check_in: '',
    check_out: '',
    total_rooms: 0,
    room_type: 'standard',
    special_rate: 0,
    notes: ''
  });

  useEffect(() => {
    loadGroups();
    loadBlocks();
  }, []);

  const loadGroups = async () => {
    try {
      const response = await axios.get('/pms/group-reservations');
      setGroups(response.data.groups || []);
    } catch (error) {
      console.error('Failed to load groups:', error);
    }
  };

  const loadBlocks = async () => {
    try {
      const response = await axios.get('/pms/room-blocks');
      setBlocks(response.data.blocks || []);
    } catch (error) {
      console.error('Failed to load blocks:', error);
    }
  };

  const handleCreateGroup = async () => {
    try {
      await axios.post('/pms/group-reservations', formData);
      toast.success('Group reservation created');
      setShowDialog(false);
      resetForm();
      loadGroups();
    } catch (error) {
      toast.error('Grup oluşturulamadı');
    }
  };

  const handleCreateBlock = async () => {
    try {
      await axios.post('/pms/room-blocks', formData);
      toast.success('Room block created');
      setShowDialog(false);
      resetForm();
      loadBlocks();
    } catch (error) {
      toast.error('Blok oluşturulamadı');
    }
  };

  const resetForm = () => {
    setFormData({
      group_name: '',
      contact_person: '',
      contact_email: '',
      contact_phone: '',
      check_in: '',
      check_out: '',
      total_rooms: 0,
      room_type: 'standard',
      special_rate: 0,
      notes: ''
    });
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">Group & Block Reservations</h1>
          <p className="text-gray-600">Manage corporate groups and room blocks</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => {
            setDialogType('group');
            setShowDialog(true);
          }}>
            <Users className="w-4 h-4 mr-2" />
            New Group
          </Button>
          <Button variant="outline" onClick={() => {
            setDialogType('block');
            setShowDialog(true);
          }}>
            <Building2 className="w-4 h-4 mr-2" />
            New Block
          </Button>
        </div>
      </div>

      {/* {t('groups.title')} */}
      <div>
        <h2 className="text-xl font-bold mb-4">Group Reservations</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {groups.map((group) => (
            <Card key={group.id} className="hover:shadow-lg transition">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Users className="w-5 h-5 text-blue-500" />
                  <CardTitle className="text-lg">{group.group_name}</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Contact:</span>
                    <span className="font-semibold">{group.contact_person}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Total Rooms:</span>
                    <span className="font-semibold">{group.total_rooms}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Booked:</span>
                    <span className="font-semibold">{group.booked_rooms || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Available:</span>
                    <span className="font-semibold text-green-600">
                      {group.total_rooms - (group.booked_rooms || 0)}
                    </span>
                  </div>
                  <div className="pt-2 border-t">
                    <div className="text-xs text-gray-600">Dates</div>
                    <div className="font-semibold">
                      {new Date(group.check_in).toLocaleDateString()} - {new Date(group.check_out).toLocaleDateString()}
                    </div>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Group Rate:</span>
                    <span className="font-semibold">${group.special_rate}/night</span>
                  </div>
                  <Button size="sm" variant="outline" className="w-full mt-2">
                    Manage Group
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Room Blocks */}
      <div>
        <h2 className="text-xl font-bold mb-4">Room Blocks</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {blocks.map((block) => (
            <Card key={block.id} className="hover:shadow-lg transition">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Building2 className="w-5 h-5 text-indigo-500" />
                  <CardTitle className="text-lg">{block.block_name}</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Room Type:</span>
                    <span className="font-semibold capitalize">{block.room_type}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Blocked Rooms:</span>
                    <span className="font-semibold">{block.total_rooms}</span>
                  </div>
                  <div className="pt-2 border-t">
                    <div className="text-xs text-gray-600">Block Period</div>
                    <div className="font-semibold">
                      {new Date(block.start_date).toLocaleDateString()} - {new Date(block.end_date).toLocaleDateString()}
                    </div>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Reason:</span>
                    <span className="text-xs">{block.reason}</span>
                  </div>
                  <Badge className={block.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}>
                    {block.status}
                  </Badge>
                  <Button size="sm" variant="outline" className="w-full mt-2">
                    Release Block
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Create Dialog */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Create {dialogType === 'group' ? 'Group Reservation' : 'Room Block'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>{dialogType === 'group' ? 'Group Name' : 'Block Name'}</Label>
              <Input
                value={formData.group_name}
                onChange={(e) => setFormData({ ...formData, group_name: e.target.value })}
                placeholder="Corporate Meeting 2025"
              />
            </div>

            {dialogType === 'group' && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Contact Person</Label>
                  <Input
                    value={formData.contact_person}
                    onChange={(e) => setFormData({ ...formData, contact_person: e.target.value })}
                  />
                </div>
                <div>
                  <Label>Contact Email</Label>
                  <Input
                    type="email"
                    value={formData.contact_email}
                    onChange={(e) => setFormData({ ...formData, contact_email: e.target.value })}
                  />
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>{dialogType === 'group' ? 'Check-in' : 'Start Date'}</Label>
                <Input
                  type="date"
                  value={formData.check_in}
                  onChange={(e) => setFormData({ ...formData, check_in: e.target.value })}
                />
              </div>
              <div>
                <Label>{dialogType === 'group' ? 'Check-out' : 'End Date'}</Label>
                <Input
                  type="date"
                  value={formData.check_out}
                  onChange={(e) => setFormData({ ...formData, check_out: e.target.value })}
                />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <Label>Total Rooms</Label>
                <Input
                  type="number"
                  value={formData.total_rooms}
                  onChange={(e) => setFormData({ ...formData, total_rooms: parseInt(e.target.value) })}
                />
              </div>
              <div>
                <Label>Room Type</Label>
                <select
                  className="w-full border rounded-md p-2"
                  value={formData.room_type}
                  onChange={(e) => setFormData({ ...formData, room_type: e.target.value })}
                >
                  <option value="standard">Standard</option>
                  <option value="deluxe">Deluxe</option>
                  <option value="suite">Suite</option>
                </select>
              </div>
              <div>
                <Label>{dialogType === 'group' ? 'Group Rate' : 'Rate'}</Label>
                <Input
                  type="number"
                  value={formData.special_rate}
                  onChange={(e) => setFormData({ ...formData, special_rate: parseFloat(e.target.value) })}
                />
              </div>
            </div>

            <div>
              <Label>Notes</Label>
              <Input
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                placeholder="Special requirements..."
              />
            </div>

            <Button
              onClick={dialogType === 'group' ? handleCreateGroup : handleCreateBlock}
              className="w-full"
            >
              Create {dialogType === 'group' ? 'Group' : 'Block'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default GroupReservations;