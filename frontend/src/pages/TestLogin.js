import React, { useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';

function TestLogin() {
  const { t } = useTranslation();
  const [email, setEmail] = useState('test@test.com');
  const [password, setPassword] = useState('test123');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  
  // Test kullanıcıları
  const testUsers = [
    { email: 'test@test.com', password: 'test123', name: 'Test Kullanıcı' },
    { email: 'demo@demo.com', password: 'demo123', name: 'Demo User' },
    { email: 'patron@hotel.com', password: 'patron123', name: 'Patron' },
    { email: 'admin@hoteltest.com', password: 'admin123', name: 'Admin' },
    { email: 'dashboard@testhotel.com', password: 'testpass123', name: 'Dashboard Tester' }
  ];

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);

    try {
      console.log('Attempting login with:', { email, password });
      
      const response = await axios.post('/auth/login', {
        email: email,
        password: password
      });

      console.log('Login response:', response.data);
      
      if (response.data.access_token) {
        // Store token
        localStorage.setItem('token', response.data.access_token);
        localStorage.setItem('user', JSON.stringify(response.data.user));
        
        setResult({
          success: true,
          message: 'Login successful!',
          data: response.data
        });

        // Redirect to main app after 2 seconds
        setTimeout(() => {
          window.location.href = '/';
        }, 2000);
      } else {
        setResult({
          success: false,
          message: 'No token received',
          data: response.data
        });
      }
    } catch (error) {
      console.error('Login error:', error);
      setResult({
        success: false,
        message: error.response?.data?.detail || error.message,
        error: error.response?.data || error.message
      });
    } finally {
      setLoading(false);
    }
  };

  const testDirectAPI = async () => {
    setLoading(true);
    setResult(null);

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password })
      });

      const data = await response.json();
      
      setResult({
        success: response.ok,
        message: response.ok ? 'Direct API call successful!' : 'Direct API call failed',
        status: response.status,
        data: data
      });

      if (response.ok && data.access_token) {
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('user', JSON.stringify(data.user));
      }
    } catch (error) {
      setResult({
        success: false,
        message: 'Direct API call error',
        error: error.message
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ 
      minHeight: '100vh', 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      padding: '20px'
    }}>
      <div style={{
        background: 'white',
        padding: '40px',
        borderRadius: '20px',
        boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        maxWidth: '500px',
        width: '100%'
      }}>
        <h1 style={{ 
          textAlign: 'center', 
          marginBottom: '10px',
          color: '#333',
          fontSize: '28px'
        }}>
          🔐 Test Login
        </h1>
        <p style={{ 
          textAlign: 'center', 
          color: '#666', 
          marginBottom: '20px',
          fontSize: '14px'
        }}>
          Debug Login Page
        </p>

        {/* Quick Test Users */}
        <div style={{ marginBottom: '20px' }}>
          <p style={{ fontSize: '12px', color: '#666', marginBottom: '10px', textAlign: 'center' }}>
            🚀 Hızlı Giriş:
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
            {testUsers.map((user, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => {
                  setEmail(user.email);
                  setPassword(user.password);
                }}
                style={{
                  padding: '8px 12px',
                  fontSize: '12px',
                  border: '1px solid #667eea',
                  borderRadius: '6px',
                  background: email === user.email ? '#667eea' : 'white',
                  color: email === user.email ? 'white' : '#667eea',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
              >
                {user.name}
              </button>
            ))}
          </div>
        </div>

        <form onSubmit={handleLogin}>
          <div style={{ marginBottom: '20px' }}>
            <label style={{ 
              display: 'block', 
              marginBottom: '8px', 
              fontWeight: '600',
              color: '#333'
            }}>
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{
                width: '100%',
                padding: '12px',
                border: '2px solid #e0e0e0',
                borderRadius: '8px',
                fontSize: '16px',
                boxSizing: 'border-box'
              }}
              required
            />
          </div>

          <div style={{ marginBottom: '25px' }}>
            <label style={{ 
              display: 'block', 
              marginBottom: '8px', 
              fontWeight: '600',
              color: '#333'
            }}>
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{
                width: '100%',
                padding: '12px',
                border: '2px solid #e0e0e0',
                borderRadius: '8px',
                fontSize: '16px',
                boxSizing: 'border-box'
              }}
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%',
              padding: '14px',
              background: loading ? '#ccc' : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              fontSize: '16px',
              fontWeight: '600',
              cursor: loading ? 'not-allowed' : 'pointer',
              marginBottom: '10px'
            }}
          >
            {loading ? '⏳ Logging in...' : '🚀 Login (Axios)'}
          </button>

          <button
            type="button"
            onClick={testDirectAPI}
            disabled={loading}
            style={{
              width: '100%',
              padding: '14px',
              background: loading ? '#ccc' : '#4CAF50',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              fontSize: '16px',
              fontWeight: '600',
              cursor: loading ? 'not-allowed' : 'pointer'
            }}
          >
            {loading ? '⏳ Testing...' : '🧪 Test Direct API'}
          </button>
        </form>

        {result && (
          <div style={{
            marginTop: '25px',
            padding: '15px',
            borderRadius: '8px',
            background: result.success ? '#d4edda' : '#f8d7da',
            border: `2px solid ${result.success ? '#c3e6cb' : '#f5c6cb'}`,
            color: result.success ? '#155724' : '#721c24'
          }}>
            <strong>{result.success ? '✅ Success!' : '❌ Error!'}</strong>
            <p style={{ margin: '10px 0', fontSize: '14px' }}>{result.message}</p>
            {result.status && <p style={{ fontSize: '12px' }}>Status: {result.status}</p>}
            <details style={{ marginTop: '10px', fontSize: '12px' }}>
              <summary style={{ cursor: 'pointer', fontWeight: '600' }}>Show Details</summary>
              <pre style={{ 
                marginTop: '10px', 
                padding: '10px', 
                background: '#f5f5f5', 
                borderRadius: '4px',
                overflow: 'auto',
                maxHeight: '200px'
              }}>
                {JSON.stringify(result.data || result.error, null, 2)}
              </pre>
            </details>
          </div>
        )}

        <div style={{
          marginTop: '30px',
          padding: '15px',
          background: '#f8f9fa',
          borderRadius: '8px',
          fontSize: '13px',
          color: '#666'
        }}>
          <strong>📝 Test Credentials:</strong><br/>
          Email: admin@testhotel.com<br/>
          Password: admin123<br/>
          Role: Admin
        </div>

        <div style={{ 
          marginTop: '20px', 
          textAlign: 'center',
          fontSize: '12px',
          color: '#999'
        }}>
          <a href="/" style={{ color: '#667eea', textDecoration: 'none' }}>
            ← Back to Main App
          </a>
        </div>
      </div>
    </div>
  );
}

export default TestLogin;
