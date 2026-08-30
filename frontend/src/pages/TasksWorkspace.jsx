import React from 'react';

import Layout from '@/components/Layout';
import StaffTaskManager from '@/components/StaffTaskManager';

export default function TasksWorkspace({ user, tenant, onLogout }) {
  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="tasks_workspace">
      <div className="p-6 space-y-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Görevler</h1>
          <p className="text-sm text-gray-500 mt-1">Operasyon görevlerini takip et ve yönet</p>
        </div>
        <StaffTaskManager currentUser={user} />
      </div>
    </Layout>
  );
}
