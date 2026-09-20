import React from 'react';

import { ModuleAvailabilityState } from '@/components/shared/ModuleAvailabilityState';
import { hasAnyModuleAccess, canAccessPath } from '@/utils/moduleAccess';

export default function ModuleScopeBoundary({ user, scopes, path, children }) {
  if (hasAnyModuleAccess(user, scopes) && (!path || canAccessPath(user, path))) return children;
  return <ModuleAvailabilityState reason="disabled" />;
}
