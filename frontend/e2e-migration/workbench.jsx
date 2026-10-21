import React from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import DataMigrationPage from '../src/pages/DataMigrationPage';
import '../src/index.css';

axios.defaults.baseURL = '/api';
createRoot(document.getElementById('root')).render(
  <MemoryRouter><DataMigrationPage user={{ tenant_id: 'synthetic-property', role: 'admin' }} /></MemoryRouter>,
);
