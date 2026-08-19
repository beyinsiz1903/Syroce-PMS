import React from 'react';
import { Navigate } from 'react-router-dom';

import { hasAnyModuleAccess } from '@/utils/moduleAccess';

export default function ModuleScopeBoundary({ user, scopes, children }) {
  if (hasAnyModuleAccess(user, scopes)) return children;
  return <Navigate to="/app/dashboard" replace />;
}
