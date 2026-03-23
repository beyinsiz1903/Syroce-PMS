import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Shield, Lock, FileText, Download, Eye, AlertTriangle } from 'lucide-react';

const SecurityGDPRModule = () => {
  const [auditLogs, setAuditLogs] = useState([]);
  const [gdprRequests, setGdprRequests] = useState([]);
  const [certifications, setCertifications] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAuditLogs();
    fetchGDPRRequests();
    fetchCertifications();
  }, []);

  const fetchAuditLogs = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/security/audit-logs?days=7`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const data = await response.json();
      setAuditLogs(data.logs || []);
    } catch (error) {
      console.error('Error:', error);
    }
  };

  const fetchGDPRRequests = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/gdpr/data-requests`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const data = await response.json();
      setGdprRequests(data.requests || []);
    } catch (error) {
      console.error('Error:', error);
    }
  };

  const fetchCertifications = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/compliance/certifications`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const data = await response.json();
      setCertifications(data);
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Shield className="w-8 h-8 text-blue-600" />
            Security & GDPR Compliance
          </h1>
          <p className="text-gray-600">Data protection and security management</p>
        </div>
      </div>

      {/* Certifications */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {certifications?.certifications?.map((cert, idx) => (
          <Card key={idx}>
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <Shield className="w-8 h-8 text-blue-600" />
                <Badge className={cert.status === 'certified' ? 'bg-green-500' : 'bg-yellow-500'}>
                  {cert.status}
                </Badge>
              </div>
              <h3 className="font-bold text-lg mb-2">{cert.name}</h3>
              <div className="space-y-1 text-sm">
                {cert.issued_date && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Issued:</span>
                    <span>{cert.issued_date}</span>
                  </div>
                )}
                {cert.expiry_date && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Expires:</span>
                    <span>{cert.expiry_date}</span>
                  </div>
                )}
                {cert.last_audit && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Last Audit:</span>
                    <span>{cert.last_audit}</span>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* System Info */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Lock className="w-5 h-5" />
            System Information
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <div className="text-sm text-gray-600 mb-1">Data Location</div>
              <div className="font-semibold">{certifications?.data_location || 'N/A'}</div>
            </div>
            <div>
              <div className="text-sm text-gray-600 mb-1">Backup Policy</div>
              <div className="font-semibold">{certifications?.backup_policy || 'N/A'}</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* GDPR Requests */}
      <Card>
        <CardHeader>
          <CardTitle>GDPR Data Requests</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left p-3">Guest Email</th>
                <th className="text-left p-3">Request Type</th>
                <th className="text-left p-3">Status</th>
                <th className="text-left p-3">Requested</th>
                <th className="text-left p-3">Completed</th>
              </tr>
            </thead>
            <tbody>
              {gdprRequests.map((req, idx) => (
                <tr key={idx} className="border-b hover:bg-gray-50">
                  <td className="p-3">{req.guest_email}</td>
                  <td className="p-3">
                    <Badge variant="outline">{req.request_type}</Badge>
                  </td>
                  <td className="p-3">
                    <Badge className={req.status === 'completed' ? 'bg-green-500' : 'bg-yellow-500'}>
                      {req.status}
                    </Badge>
                  </td>
                  <td className="p-3">{req.requested_at}</td>
                  <td className="p-3">{req.completed_at || 'Pending'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Audit Logs */}
      <Card>
        <CardHeader>
          <CardTitle>Security Audit Logs (Last 7 Days)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <table className="w-full">
              <thead className="sticky top-0 bg-white">
                <tr className="border-b">
                  <th className="text-left p-2 text-sm">Timestamp</th>
                  <th className="text-left p-2 text-sm">User</th>
                  <th className="text-left p-2 text-sm">Action</th>
                  <th className="text-left p-2 text-sm">IP Address</th>
                  <th className="text-left p-2 text-sm">Status</th>
                </tr>
              </thead>
              <tbody>
                {auditLogs.slice(0, 30).map((log, idx) => (
                  <tr key={idx} className="border-b hover:bg-gray-50 text-sm">
                    <td className="p-2">{new Date(log.timestamp).toLocaleString()}</td>
                    <td className="p-2">{log.user}</td>
                    <td className="p-2">
                      <Badge variant="outline" className="text-xs">{log.action}</Badge>
                    </td>
                    <td className="p-2 font-mono text-xs">{log.ip_address}</td>
                    <td className="p-2">
                      <Badge className="bg-green-500 text-xs">{log.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default SecurityGDPRModule;