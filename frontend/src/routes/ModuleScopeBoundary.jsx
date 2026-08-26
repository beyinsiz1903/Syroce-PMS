import React from 'react';

import { ModuleAvailabilityState } from '@/components/shared/ModuleAvailabilityState';
import { hasAnyModuleAccess } from '@/utils/moduleAccess';

export default function ModuleScopeBoundary({ user, scopes, children }) {
  if (hasAnyModuleAccess(user, scopes)) return children;
  return <ModuleAvailabilityState reason="disabled" />;
}
