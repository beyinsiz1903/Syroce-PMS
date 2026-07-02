import React, { useState, useEffect } from 'react';
import axios from 'axios';
const API_URL = import.meta.env.VITE_BACKEND_URL || '';
const AIHousekeepingBoard = () => {
  const [schedule, setSchedule] = useState(null);
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [tasks, setTasks] = useState([]);
  const [staffPerformance, setStaffPerformance] = useState([]);
  useEffect(() => {
    generateAISchedule();
    fetchStaffPerformance();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [selectedDate]);
  const generateAISchedule = async () => {
    try {
      const response = await axios.post(`/ai/housekeeping/smart-schedule`, {
        date: selectedDate
      }, {
        headers: {}
      });
      setSchedule(response.data);
    } catch (error) {
      console.error('Error generating AI schedule:', error);
    }
  };
  const fetchStaffPerformance = async () => {
    try {
      const response = await axios.get(`/housekeeping/staff-performance-table`, {
        headers: {}
      });
      setStaffPerformance(response.data.staff_performance || []);
    } catch (error) {
      console.error('Error fetching staff performance:', error);
    }
  };
  const updateTaskStatus = async (taskId, newStatus) => {
    try {
      await axios.put(`/housekeeping/tasks/${taskId}`, {
        status: newStatus
      }, {
        headers: {}
      });
      generateAISchedule();
    } catch (error) {
      console.error('Error updating task:', error);
    }
  };
  return <div className="p-6 bg-white">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">AI Housekeeping Board</h1>
        <div className="flex gap-4">
          <button onClick={generateAISchedule} className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">
            Regenerate Schedule
          </button>
          <input type="date" value={selectedDate} onChange={e => setSelectedDate(e.target.value)} className="px-4 py-2 border rounded-lg" />
        </div>
      </div>

      {/* AI Schedule Summary */}
      {schedule && <div className="mb-6">
          <div className="grid grid-cols-4 gap-4 mb-6">
            <div className="bg-blue-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600">Occupied Rooms</div>
              <div className="text-2xl font-bold text-blue-600">{schedule.forecast.occupied_rooms}</div>
            </div>
            <div className="bg-green-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600">Checkout Rooms</div>
              <div className="text-2xl font-bold text-green-600">{schedule.forecast.checkout_rooms}</div>
            </div>
            <div className="bg-indigo-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600">Staff Available</div>
              <div className="text-2xl font-bold text-indigo-600">{schedule.staffing.available_staff}</div>
            </div>
            <div className={`p-4 rounded-lg ${schedule.staffing.capacity_utilization < 90 ? 'bg-green-50' : schedule.staffing.capacity_utilization < 110 ? 'bg-yellow-50' : 'bg-red-50'}`}>
              <div className="text-sm text-gray-600">Capacity</div>
              <div className={`text-2xl font-bold ${schedule.staffing.capacity_utilization < 90 ? 'text-green-600' : schedule.staffing.capacity_utilization < 110 ? 'text-yellow-600' : 'text-red-600'}`}>
                {schedule.staffing.capacity_utilization}%
              </div>
            </div>
          </div>

          {/* Status Message */}
          <div className={`p-4 rounded-lg mb-6 ${schedule.staffing.capacity_utilization < 90 ? 'bg-green-100 border-green-500' : schedule.staffing.capacity_utilization < 110 ? 'bg-yellow-100 border-yellow-500' : 'bg-red-100 border-red-500'} border-l-4`}>
            <div className="font-semibold">{schedule.staffing.status}</div>
            {schedule.recommendations && <ul className="mt-2 space-y-1">
                {schedule.recommendations.map((rec, idx) => <li key={idx} className="text-sm">{rec}</li>)}
              </ul>}
          </div>

          {/* Staff Assignments */}
          <h2 className="text-xl font-semibold mb-4">AI Task Distribution</h2>
          <div className="grid gap-4">
            {schedule.ai_schedule.staff_assignments.map((assignment, idx) => <div key={idx} className="border rounded-lg p-4">
                <div className="flex justify-between items-center mb-3">
                  <h3 className="text-lg font-semibold">{assignment.staff_name}</h3>
                  <div className="flex gap-4">
                    <span className="text-gray-600">{assignment.total_tasks} tasks</span>
                    <span className="text-gray-600">{assignment.estimated_minutes} min</span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {assignment.tasks.slice(0, 10).map((task, tidx) => <span key={tidx} className={`px-3 py-1 rounded-full text-sm ${task.type === 'checkout' ? 'bg-red-100 text-red-800' : 'bg-blue-100 text-blue-800'}`}>
                      Room {task.room_id.slice(0, 4)}
                    </span>)}
                  {assignment.tasks.length > 10 && <span className="px-3 py-1 rounded-full text-sm bg-gray-100 text-gray-800">
                      +{assignment.tasks.length - 10} more
                    </span>}
                </div>
              </div>)}
          </div>
        </div>}

      {/* Staff Performance */}
      <div className="mt-8">
        <h2 className="text-xl font-semibold mb-4">Staff Performance (Last 30 Days)</h2>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-gray-100">
                <th className="p-3 text-left">Staff Name</th>
                <th className="p-3 text-left">Tasks Completed</th>
                <th className="p-3 text-left">Avg Duration</th>
                <th className="p-3 text-left">Quality Score</th>
                <th className="p-3 text-left">Overall Score</th>
                <th className="p-3 text-left">Rating</th>
              </tr>
            </thead>
            <tbody>
              {staffPerformance.map((staff, idx) => <tr key={idx} className="border-b hover:bg-gray-50">
                  <td className="p-3 font-medium">{staff.staff_name}</td>
                  <td className="p-3">{staff.tasks_completed}</td>
                  <td className="p-3">{staff.avg_duration_minutes} min</td>
                  <td className="p-3">
                    <span className={`px-2 py-1 rounded text-sm ${staff.quality_score >= 90 ? 'bg-green-100 text-green-800' : staff.quality_score >= 80 ? 'bg-yellow-100 text-yellow-800' : 'bg-red-100 text-red-800'}`}>
                      {staff.quality_score}%
                    </span>
                  </td>
                  <td className="p-3">
                    <span className={`px-2 py-1 rounded text-sm ${staff.overall_performance_score >= 90 ? 'bg-green-100 text-green-800' : staff.overall_performance_score >= 80 ? 'bg-yellow-100 text-yellow-800' : 'bg-red-100 text-red-800'}`}>
                      {staff.overall_performance_score}
                    </span>
                  </td>
                  <td className="p-3">{staff.rating}</td>
                </tr>)}
            </tbody>
          </table>
        </div>
      </div>
    </div>;
};
export default AIHousekeepingBoard;