import { lazy } from 'react';

const CashierWorkspace = lazy(() => import('@/pages/CashierWorkspace'));
const TasksWorkspace = lazy(() => import('@/pages/TasksWorkspace'));

export function moduleWorkspaceRoutes({ p }) {
  return [
    { path: '/app/cashier', ...p(CashierWorkspace), wrapLayout: false, moduleScopes: ['cashier'] },
    { path: '/app/tasks', ...p(TasksWorkspace), wrapLayout: false, moduleScopes: ['tasks'] },
  ];
}
