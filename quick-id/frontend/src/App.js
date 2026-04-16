import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from './components/ui/sonner';
import { AuthProvider, useAuth } from './lib/AuthContext';
import { ThemeProvider } from './lib/ThemeContext';
import { LanguageProvider } from './lib/LanguageContext';
import ErrorBoundary from './components/ErrorBoundary';
import AppShell from './components/AppShell';
import LoginPage from './pages/LoginPage';
import Dashboard from './pages/Dashboard';
import ScanPage from './pages/ScanPage';
import BulkScanPage from './pages/BulkScanPage';
import GuestList from './pages/GuestList';
import GuestDetail from './pages/GuestDetail';
import UserManagement from './pages/UserManagement';
import SettingsPage from './pages/SettingsPage';
import KvkkCompliancePage from './pages/KvkkCompliancePage';
import ApiDocsPage from './pages/ApiDocsPage';
import FaceMatchPage from './pages/FaceMatchPage';
import TcKimlikPage from './pages/TcKimlikPage';
import PropertiesPage from './pages/PropertiesPage';
import KioskPage from './pages/KioskPage';
import PreCheckinPage from './pages/PreCheckinPage';
import MonitoringPage from './pages/MonitoringPage';
import RoomManagementPage from './pages/RoomManagementPage';
import GroupCheckinPage from './pages/GroupCheckinPage';
import './App.css';

function ProtectedRoute({ children, adminOnly = false }) {
  const { isAuthenticated, isAdmin } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (adminOnly && !isAdmin) return <Navigate to="/" replace />;
  return children;
}

function AppRoutes() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />} />
      
      {/* Public routes - No auth needed */}
      <Route path="/precheckin/:tokenId" element={<PreCheckinPage />} />
      
      {/* Protected routes */}
      <Route path="/" element={<ProtectedRoute><AppShell><Dashboard /></AppShell></ProtectedRoute>} />
      <Route path="/scan" element={<ProtectedRoute><AppShell><ScanPage /></AppShell></ProtectedRoute>} />
      <Route path="/bulk-scan" element={<ProtectedRoute><AppShell><BulkScanPage /></AppShell></ProtectedRoute>} />
      <Route path="/guests" element={<ProtectedRoute><AppShell><GuestList /></AppShell></ProtectedRoute>} />
      <Route path="/guests/:id" element={<ProtectedRoute><AppShell><GuestDetail /></AppShell></ProtectedRoute>} />
      <Route path="/face-match" element={<ProtectedRoute><AppShell><FaceMatchPage /></AppShell></ProtectedRoute>} />
      <Route path="/tc-kimlik" element={<ProtectedRoute><AppShell><TcKimlikPage /></AppShell></ProtectedRoute>} />
      <Route path="/group-checkin" element={<ProtectedRoute><AppShell><GroupCheckinPage /></AppShell></ProtectedRoute>} />
      <Route path="/rooms" element={<ProtectedRoute><AppShell><RoomManagementPage /></AppShell></ProtectedRoute>} />
      
      {/* Admin only routes */}
      <Route path="/monitoring" element={<ProtectedRoute adminOnly><AppShell><MonitoringPage /></AppShell></ProtectedRoute>} />
      <Route path="/users" element={<ProtectedRoute adminOnly><AppShell><UserManagement /></AppShell></ProtectedRoute>} />
      <Route path="/settings" element={<ProtectedRoute adminOnly><AppShell><SettingsPage /></AppShell></ProtectedRoute>} />
      <Route path="/kvkk" element={<ProtectedRoute adminOnly><AppShell><KvkkCompliancePage /></AppShell></ProtectedRoute>} />
      <Route path="/api-docs" element={<ProtectedRoute adminOnly><AppShell><ApiDocsPage /></AppShell></ProtectedRoute>} />
      <Route path="/properties" element={<ProtectedRoute adminOnly><AppShell><PropertiesPage /></AppShell></ProtectedRoute>} />
      <Route path="/kiosk" element={<ProtectedRoute adminOnly><AppShell><KioskPage /></AppShell></ProtectedRoute>} />
      
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <LanguageProvider>
          <AuthProvider>
            <Router>
              <ErrorBoundary>
                <AppRoutes />
              </ErrorBoundary>
              <Toaster richColors position="top-right" />
            </Router>
          </AuthProvider>
        </LanguageProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
