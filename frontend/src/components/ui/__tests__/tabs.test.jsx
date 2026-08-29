import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

afterEach(() => cleanup());

describe('Tabs focus styling', () => {
  it('does not draw a full-panel ring while preserving trigger focus styling', () => {
    render(
      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general">Genel</TabsTrigger>
        </TabsList>
        <TabsContent value="general" data-testid="tab-panel">
          İçerik
        </TabsContent>
      </Tabs>,
    );

    const panel = screen.getByTestId('tab-panel');
    const trigger = screen.getByRole('tab', { name: 'Genel' });

    expect(panel.className).toContain('focus:outline-none');
    expect(panel.className).not.toContain('focus-visible:ring-2');
    expect(panel.className).not.toContain('focus-visible:ring-ring');
    expect(trigger.className).toContain('focus-visible:ring-2');
  });
});
