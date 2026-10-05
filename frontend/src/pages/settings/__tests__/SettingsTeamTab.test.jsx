import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { Crown, Shield, UserCheck, Users } from 'lucide-react';

import { Tabs } from '@/components/ui/tabs';
import SettingsTeamTab from '../SettingsTeamTab';

describe('SettingsTeamTab', () => {
  it('labels destructive user actions and renders loaded visibility roles', () => {
    render(
      <MemoryRouter>
        <Tabs value="team">
          <SettingsTeamTab
          Users={Users}
          team={[{ id: 'agency-1', name: 'Acente Kullanıcısı', email: 'agency@example.com', role: 'agency_admin' }]}
          UserCheck={UserCheck}
          teamMeta={{ tier: 'enterprise', allowed_roles: ['agency_admin'], max_users: 999, can_add: true }}
          Shield={Shield}
          Crown={Crown}
          setActiveTab={vi.fn()}
          setNewMember={vi.fn()}
          setShowAddModal={vi.fn()}
          teamLoading={false}
          getRoleLabel={() => ({ label: 'Acente Yöneticisi', color: '' })}
          isSameUser={() => false}
          handleUpdateRole={vi.fn()}
          handleRemoveMember={vi.fn()}
          isAdmin
          grLoading={false}
          grSettings={{
            visible_roles: ['front_desk'],
            available_roles: [{ value: 'front_desk', label: 'Resepsiyon' }],
            always_allowed: [],
          }}
          toggleGuestRequestRole={vi.fn()}
          saveGuestRequestSettings={vi.fn()}
          grSaving={false}
          />
        </Tabs>
      </MemoryRouter>,
    );

    expect(screen.getAllByText('Acente Yöneticisi')).toHaveLength(2);
    expect(screen.getByText('Resepsiyon')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Acente Kullanıcısı kullanıcısını sil' })).toBeInTheDocument();
  });
});
