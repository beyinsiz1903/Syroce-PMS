import React from 'react';

import Layout from '@/components/Layout';
import CashierTab from '@/components/pms/CashierTab';

export default function CashierWorkspace({ user, tenant, onLogout }) {
  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="cashier_workspace">
      <div className="p-6 space-y-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Kasa</h1>
          <p className="text-sm text-gray-500 mt-1">Tahsilat ve folyo kasa işlemleri</p>
        </div>
        <CashierTab user={user} />
      </div>
    </Layout>
  );
}
