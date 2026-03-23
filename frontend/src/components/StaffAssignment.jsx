import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Users, TrendingUp, Clock, CheckCircle, RefreshCw } from 'lucide-react';

const StaffAssignment = () => {
  const [staff, setStaff] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedStaff, setSelectedStaff] = useState(null);

  useEffect(() => {
    loadStaff();
  }, []);

  const loadStaff = async () => {
    try {
      setLoading(true);
      const response = await axios.get('/housekeeping/staff');
      setStaff(response.data.staff || []);
      setStats({
        total: response.data.total,
        totalRooms: response.data.total_rooms_assigned,
        avgEfficiency: response.data.avg_efficiency
      });
    } catch (error) {
      console.error('Failed to load staff:', error);
      toast.error('Failed to load staff');
    } finally {
      setLoading(false);
    }
  };

  const getShiftColor = (shift) => {
    return shift === 'morning' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700';
  };

  const getEfficiencyColor = (efficiency) => {
    if (efficiency >= 90) return 'text-green-600';
    if (efficiency >= 80) return 'text-yellow-600';
    return 'text-red-600';
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-600 mx-auto" />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stats Summary */}
      {stats && (
        <div className="grid grid-cols-3 gap-4">
          <Card className="bg-gradient-to-br from-blue-50 to-blue-100">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-blue-600 font-medium">Total Staff</p>
                  <p className="text-3xl font-bold text-blue-700">{stats.total}</p>
                </div>
                <Users className="w-10 h-10 text-blue-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-green-50 to-green-100">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-green-600 font-medium">Assigned Rooms</p>
                  <p className="text-3xl font-bold text-green-700">{stats.totalRooms}</p>
                </div>
                <CheckCircle className="w-10 h-10 text-green-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-purple-50 to-purple-100">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-purple-600 font-medium">Avg Efficiency</p>
                  <p className="text-3xl font-bold text-purple-700">{stats.avgEfficiency}%</p>
                </div>
                <TrendingUp className="w-10 h-10 text-purple-300" />
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Staff List */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center">
              <Users className="w-5 h-5 mr-2 text-blue-600" />
              Housekeeping Staff ({staff.length})
            </CardTitle>
            <Button variant="outline" size="sm" onClick={loadStaff}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {staff.map((member) => (
              <div
                key={member.id}
                className="flex items-center justify-between p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition cursor-pointer"
                onClick={() => setSelectedStaff(member)}
              >
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-2">
                    <h3 className="font-bold text-gray-900">{member.name}</h3>
                    <Badge className={getShiftColor(member.shift)}>
                      <Clock className="w-3 h-3 mr-1" />
                      {member.shift}
                    </Badge>
                    {member.role === 'Supervisor' && (
                      <Badge className="bg-yellow-100 text-yellow-700">
                        ⭐ {member.role}
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center space-x-4 text-sm text-gray-600">
                    <span>{member.email}</span>
                    <span>•</span>
                    <span>{member.assigned_rooms} rooms assigned</span>
                  </div>
                </div>
                <div className="text-right">
                  <div className="flex items-center space-x-2">
                    <span className="text-sm text-gray-600">Efficiency:</span>
                    <span className={`text-2xl font-bold ${getEfficiencyColor(member.efficiency)}`}>
                      {member.efficiency}%
                    </span>
                  </div>
                  {member.active ? (
                    <Badge className="mt-2 bg-green-100 text-green-700">Active</Badge>
                  ) : (
                    <Badge className="mt-2 bg-gray-100 text-gray-700">Inactive</Badge>
                  )}
                </div>
              </div>
            ))}
          </div>

          {staff.length === 0 && (
            <div className="text-center py-8 text-gray-500">
              No staff members found
            </div>
          )}
        </CardContent>
      </Card>

      {/* Assignment Modal - Simplified */}
      {selectedStaff && (
        <Card className="bg-blue-50 border-blue-200">
          <CardHeader>
            <CardTitle className="text-lg">
              Assign Rooms to {selectedStaff.name}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 bg-white rounded">
                <div>
                  <p className="font-medium">Current Assignment</p>
                  <p className="text-sm text-gray-600">{selectedStaff.assigned_rooms} rooms</p>
                </div>
                <Button
                  onClick={() => {
                    toast.info('Room assignment feature - Connect to room selection UI');
                    setSelectedStaff(null);
                  }}
                >
                  Manage Rooms
                </Button>
              </div>
              <Button
                variant="outline"
                className="w-full"
                onClick={() => setSelectedStaff(null)}
              >
                Close
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Info */}
      <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
        <CardContent className="p-4">
          <div className="flex items-start space-x-3">
            <div className="bg-blue-100 p-2 rounded-full">
              <Users className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <h4 className="font-semibold text-gray-900 mb-1">💡 Staff Management</h4>
              <p className="text-sm text-gray-600">
                {stats && `${stats.total} staff members managing ${stats.totalRooms} rooms. Average efficiency: ${stats.avgEfficiency}%.`}
                Click on any staff member to view details and assign rooms.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default StaffAssignment;
