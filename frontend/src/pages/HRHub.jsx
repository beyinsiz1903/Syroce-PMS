import React from 'react';
import HRComplete from '@/pages/HRComplete';

export default function HRHub({ user, tenant }) {
  return (
    <div className="p-0 m-0 w-full" data-testid="hr-hub">
      <HRComplete tenant={tenant} user={user} />
    </div>
  );
}

