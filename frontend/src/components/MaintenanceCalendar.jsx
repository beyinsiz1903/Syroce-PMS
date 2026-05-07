import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Calendar, Clock, ChevronLeft, ChevronRight } from 'lucide-react';

const MaintenanceCalendar = () => {
  const [calendarItems, setCalendarItems] = useState([]);
  const [currentMonth, setCurrentMonth] = useState(new Date().toISOString().slice(0, 7));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadCalendar();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [currentMonth]);

  const loadCalendar = async () => {
    try {
      const response = await axios.get(`/maintenance/calendar?month=${currentMonth}`);
      setCalendarItems(response.data.calendar || []);
    } catch (error) {
      console.error('Failed to load calendar:', error);
    } finally {
      setLoading(false);
    }
  };

  const changeMonth = (direction) => {
    const [year, month] = currentMonth.split('-').map(Number);
    let newMonth = month + direction;
    let newYear = year;

    if (newMonth > 12) {
      newMonth = 1;
      newYear++;
    } else if (newMonth < 1) {
      newMonth = 12;
      newYear--;
    }

    setCurrentMonth(`${newYear}-${newMonth.toString().padStart(2, '0')}`);
  };

  const getMonthName = (monthStr) => {
    const months = [
      'Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
      'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'
    ];
    const [year, month] = monthStr.split('-');
    return `${months[parseInt(month) - 1]} ${year}`;
  };

  if (loading) {
    return <div className="text-center py-4">Yükleniyor...</div>;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-lg">
          <span className="flex items-center">
            <Calendar className="w-5 h-5 mr-2" />
            Rutin Bakım Takvimi
          </span>
          <div className="flex items-center space-x-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => changeMonth(-1)}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="text-sm font-medium">{getMonthName(currentMonth)}</span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => changeMonth(1)}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {calendarItems.length === 0 ? (
            <p className="text-center text-gray-500 py-8">Bu ay için planlanmış bakım yok</p>
          ) : (
            calendarItems.map((item) => (
              <div
                key={item.id}
                className="p-3 bg-gradient-to-r from-indigo-50 to-pink-50 border border-indigo-200 rounded-lg"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="font-bold text-sm">{item.task_name}</div>
                    <div className="text-xs text-gray-600 mt-1">
                      {item.assigned_to}
                    </div>
                    <div className="flex items-center space-x-3 mt-2">
                      <div className="flex items-center text-xs text-gray-500">
                        <Calendar className="w-3 h-3 mr-1" />
                        {new Date(item.scheduled_date).toLocaleDateString('tr-TR')}
                      </div>
                      <div className="flex items-center text-xs text-gray-500">
                        <Clock className="w-3 h-3 mr-1" />
                        {item.estimated_duration}
                      </div>
                    </div>
                  </div>
                  <div>
                    <Badge className="bg-indigo-500">
                      {item.frequency === 'monthly' ? 'Aylık' : item.frequency}
                    </Badge>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs">
          <div className="font-medium text-blue-900 mb-1">📅 Bu Ay Toplam:</div>
          <div className="text-blue-700">
            {calendarItems.length} rutin bakım görevi planlanmış
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default MaintenanceCalendar;
