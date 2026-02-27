import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Home,
  Clock,
  Calendar,
  DollarSign,
  Briefcase,
  UserPlus,
  Download,
  Users,
  FileSpreadsheet
} from 'lucide-react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

const demoStaff = [
  { id: 'staff-frontdesk-1', name: 'Mehmet Demir', department: 'front_desk' },
  { id: 'staff-housekeeping-1', name: 'Ayşe Kaya', department: 'housekeeping' },
  { id: 'staff-fnb-1', name: 'Chef Marco', department: 'fnb' }
];

const HRComplete = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('attendance');
  const [attendanceSummary, setAttendanceSummary] = useState(null);
  const [attendanceRecords, setAttendanceRecords] = useState([]);
  const [recordsRange, setRecordsRange] = useState({ start: '', end: '' });
  const [selectedStaff, setSelectedStaff] = useState(demoStaff[0]);
  const [exportMonth, setExportMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  });
  const [exporting, setExporting] = useState(false);

  const loadAttendance = async () => {
    try {
      const [summaryRes, recordsRes] = await Promise.all([
        axios.get('/hr/attendance/summary'),
        axios.get('/hr/attendance/records', { params: { limit: 50 } })
      ]);
      setAttendanceSummary(summaryRes.data);
      setAttendanceRecords(recordsRes.data.records || []);
      setRecordsRange(recordsRes.data.range || {});
    } catch (error) {
      console.error('Attendance load failed', error);
      toast.error('Attendance verileri yüklenemedi');
    }
  };

  useEffect(() => {
    loadAttendance();
  }, []);

  const clockIn = async (staffId) => {
    try {
      await axios.post('/hr/clock-in', { staff_id: staffId });
      toast.success('Clock-in kaydedildi!');
      loadAttendance();
    } catch (error) {
      toast.error('Hata');
    }
  };

  const clockOut = async (staffId) => {
    try {
      await axios.post('/hr/clock-out', { staff_id: staffId });
      toast.success('Clock-out kaydedildi!');
      loadAttendance();
    } catch (error) {
      toast.error('Hata');
    }
  };

  const handlePayrollExport = async () => {
    try {
      setExporting(true);
      const res = await axios.get('/hr/payroll/export', {
        params: { month: exportMonth, format: 'csv' }
      });
      if (res.data.csv) {
        const link = document.createElement('a');
        link.href = `data:text/csv;base64,${res.data.csv}`;
        link.download = `payroll_${res.data.month}.csv`;
        link.click();
        toast.success('Payroll CSV indirildi');
      }
    } catch (error) {
      console.error('Payroll export failed', error);
      toast.error('Payroll indirilemedi');
    } finally {
      setExporting(false);
    }
  };

  const attendanceMetrics = attendanceSummary?.metrics || {
    staff_count: 0,
    total_hours: 0,
    avg_hours_per_staff: 0
  };

  const topPerformers = useMemo(() => {
    if (!attendanceSummary?.summary) return [];
    return [...attendanceSummary.summary]
      .sort((a, b) => b.total_hours - a.total_hours)
      .slice(0, 3);
  }, [attendanceSummary]);

  return (
    <div className="p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <Button variant="outline" size="icon" onClick={() => navigate('/')}>
            <Home className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">👥 HR Management Suite</h1>
            <p className="text-gray-600">Time & Attendance, Payroll, Leave, Recruitment</p>
          </div>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="attendance">
            <Clock className="w-4 h-4 mr-2" />Attendance
          </TabsTrigger>
          <TabsTrigger value="payroll">
            <DollarSign className="w-4 h-4 mr-2" />Payroll
          </TabsTrigger>
          <TabsTrigger value="leave">
            <Calendar className="w-4 h-4 mr-2" />Leave
          </TabsTrigger>
          <TabsTrigger value="performance">
            <Briefcase className="w-4 h-4 mr-2" />Performance
          </TabsTrigger>
          <TabsTrigger value="recruitment">
            <UserPlus className="w-4 h-4 mr-2" />Recruitment
          </TabsTrigger>
        </TabsList>

        <TabsContent value="attendance">
          <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-3">
              <Card className="bg-blue-50 border-blue-200">
                <CardHeader>
                  <CardTitle className="text-sm text-blue-700">Toplam Çalışan</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-3xl font-bold text-blue-900">
                    {attendanceMetrics.staff_count}
                  </p>
                  <p className="text-xs text-blue-600">aktif takip edilen personel</p>
                </CardContent>
              </Card>
              <Card className="bg-green-50 border-green-200">
                <CardHeader>
                  <CardTitle className="text-sm text-green-700">Toplam Saat</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-3xl font-bold text-green-900">
                    {attendanceMetrics.total_hours?.toFixed(1)}
                  </p>
                  <p className="text-xs text-green-600">son 30 gün</p>
                </CardContent>
              </Card>
              <Card className="bg-yellow-50 border-yellow-200">
                <CardHeader>
                  <CardTitle className="text-sm text-yellow-700">Ortalama Saat</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-3xl font-bold text-yellow-900">
                    {attendanceMetrics.avg_hours_per_staff?.toFixed(1)}
                  </p>
                  <p className="text-xs text-yellow-600">personel başı</p>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <CardTitle>Time & Attendance</CardTitle>
                <div className="flex flex-wrap gap-3 items-center">
                  <div className="flex items-center gap-2">
                    <Label className="text-xs">Personel</Label>
                    <select
                      value={selectedStaff.id}
                      onChange={(e) =>
                        setSelectedStaff(demoStaff.find((s) => s.id === e.target.value) || demoStaff[0])
                      }
                      className="rounded-md border border-input px-3 py-1 text-sm"
                    >
                      {demoStaff.map((staff) => (
                        <option key={staff.id} value={staff.id}>
                          {staff.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Button
                    size="sm"
                    className="bg-green-600"
                    onClick={() => clockIn(selectedStaff.id)}
                  >
                    ⏱️ Clock In
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => clockOut(selectedStaff.id)}
                  >
                    ⏱️ Clock Out
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-md border bg-gray-50 p-3 text-xs text-gray-600">
                  İzlenen aralık: {recordsRange.start} → {recordsRange.end}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-gray-500">
                        <th className="py-2">Personel</th>
                        <th>Departman</th>
                        <th>Gün</th>
                        <th>Clock-in</th>
                        <th>Clock-out</th>
                        <th>Saat</th>
                      </tr>
                    </thead>
                    <tbody>
                      {attendanceRecords.map((record) => (
                        <tr key={record.id || record.clock_in} className="border-t border-gray-100">
                          <td className="py-2 font-semibold">{record.staff_name || record.staff_id}</td>
                          <td className="capitalize">{record.department || '-'}</td>
                          <td>{record.date}</td>
                          <td>{new Date(record.clock_in).toLocaleTimeString('tr-TR')}</td>
                          <td>
                            {record.clock_out
                              ? new Date(record.clock_out).toLocaleTimeString('tr-TR')
                              : '—'}
                          </td>
                          <td>{record.total_hours?.toFixed(2) ?? '—'}</td>
                        </tr>
                      ))}
                      {attendanceRecords.length === 0 && (
                        <tr>
                          <td colSpan={6} className="py-6 text-center text-gray-500">
                            Kayıt bulunamadı
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Top Performers</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {topPerformers.map((staff) => (
                  <div
                    key={staff.staff_id}
                    className="flex items-center justify-between rounded border border-gray-100 bg-white px-3 py-2 text-sm"
                  >
                    <div>
                      <p className="font-semibold text-gray-800">{staff.staff_name}</p>
                      <p className="text-xs text-gray-500">{staff.department}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-gray-400">Toplam Saat</p>
                      <p className="text-lg font-bold text-gray-900">
                        {staff.total_hours?.toFixed(1)}
                      </p>
                    </div>
                  </div>
                ))}
                {topPerformers.length === 0 && (
                  <p className="text-sm text-gray-500">Yeterli veri yok</p>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="payroll">
          <Card>
            <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <CardTitle className="flex items-center gap-2">
                <DollarSign className="w-4 h-4" />
                Payroll Export
              </CardTitle>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <Label className="text-xs">Ay</Label>
                  <Input
                    type="month"
                    value={exportMonth}
                    onChange={(e) => setExportMonth(e.target.value)}
                    className="w-40"
                  />
                </div>
                <Button
                  className="bg-emerald-600"
                  onClick={handlePayrollExport}
                  disabled={exporting}
                >
                  <Download className="w-4 h-4 mr-2" />
                  {exporting ? 'İndiriliyor...' : 'CSV İndir'}
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-md border bg-gray-50 p-4 text-sm text-gray-600">
                Export, attendance verilerini otomatik olarak toplar, fazla mesaiyi hesaplar ve
                Logo/Netsis için hazır CSV dosyası üretir.
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <Card>
                  <CardContent className="p-4">
                    <p className="text-xs text-gray-500 flex items-center gap-2">
                      <Users className="w-4 h-4" />
                      Personel
                    </p>
                    <p className="text-2xl font-bold">
                      {attendanceMetrics.staff_count}
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4">
                    <p className="text-xs text-gray-500 flex items-center gap-2">
                      <Clock className="w-4 h-4" />
                      Ortalama Saat
                    </p>
                    <p className="text-2xl font-bold">
                      {attendanceMetrics.avg_hours_per_staff?.toFixed(1)}
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4">
                    <p className="text-xs text-gray-500 flex items-center gap-2">
                      <FileSpreadsheet className="w-4 h-4" />
                      CSV Formatı
                    </p>
                    <p className="text-sm text-gray-600">
                      staff_id, total_hours, overtime_hours, gross_pay
                    </p>
                  </CardContent>
                </Card>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="leave">
          <Card>
            <CardHeader><CardTitle>Leave Management</CardTitle></CardHeader>
            <CardContent>
              <p className="text-center text-gray-600 py-8">Leave request ve approval sistemi</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="performance">
          <Card>
            <CardHeader><CardTitle>Performance Management</CardTitle></CardHeader>
            <CardContent>
              <p className="text-center text-gray-600 py-8">KPI tracking, goal setting, 360 feedback</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="recruitment">
          <Card>
            <CardHeader><CardTitle>Recruitment & Onboarding</CardTitle></CardHeader>
            <CardContent>
              <p className="text-center text-gray-600 py-8">Job posting, applicant tracking, onboarding workflow</p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default HRComplete;