import React from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

const LeadTimeCurve = ({ data }) => {
  const chartData = {
    labels: data?.labels || ['0-7 days', '8-14 days', '15-30 days', '31-60 days', '61-90 days', '91+ days'],
    datasets: [
      {
        label: 'Bookings',
        data: data?.values || [120, 180, 250, 200, 150, 100],
        borderColor: 'rgb(16, 185, 129)',
        backgroundColor: 'rgba(16, 185, 129, 0.1)',
        tension: 0.4,
        fill: true
      }
    ]
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false
      },
      title: {
        display: true,
        text: 'Booking Lead Time Distribution',
        font: {
          size: 16,
          weight: 'bold'
        }
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        title: {
          display: true,
          text: 'Number of Bookings'
        }
      },
      x: {
        title: {
          display: true,
          text: 'Lead Time (Days Before Arrival)'
        }
      }
    }
  };

  return (
    <div className="h-80">
      <Line data={chartData} options={options} />
    </div>
  );
};

export default LeadTimeCurve;
