import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Tabs } from '@/components/ui/tabs';
import OverviewTab from '@/components/night-audit/tabs/OverviewTab';

const props = {
  t: key => key, schedule: { enabled: false, scheduled_hour: 3, scheduled_minute: 0 },
  history: [], historyTotal: 0, exceptions: {}, lastRun: null,
};

describe('night audit schedule controls', () => {
  it('does not show schedule modification buttons to reception', () => {
    render(<Tabs defaultValue="overview"><OverviewTab {...props} canRunAudit canManageSchedule={false} /></Tabs>);
    expect(screen.getByTestId('schedule-card')).toBeInTheDocument();
    expect(screen.queryByTestId('schedule-toggle')).not.toBeInTheDocument();
    expect(screen.queryByTestId('schedule-settings-btn')).not.toBeInTheDocument();
  });
  it('shows the schedule settings only with administrator capability', () => {
    render(<Tabs defaultValue="overview"><OverviewTab {...props} canRunAudit canManageSchedule /></Tabs>);
    expect(screen.getByTestId('schedule-toggle')).toBeInTheDocument();
    expect(screen.getByTestId('schedule-settings-btn')).toBeInTheDocument();
  });
});
