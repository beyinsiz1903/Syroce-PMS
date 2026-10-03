import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const component = readFileSync(resolve(process.cwd(), 'src/components/EmptyState.jsx'), 'utf8');

describe('shared EmptyState quality contract', () => {
  it('announces content with an accessible title and description', () => {
    expect(component).toContain('role="status"');
    expect(component).toContain('aria-live="polite"');
    expect(component).toContain('aria-labelledby={titleId}');
    expect(component).toContain('aria-describedby={descriptionId}');
    expect(component).toContain('aria-hidden="true"');
  });

  it('uses translated defaults and does not submit a surrounding form', () => {
    expect(component).toContain("t('uiQuality.emptyState.defaultTitle'");
    expect(component).toContain("t('uiQuality.emptyState.defaultDescription'");
    expect(component).toContain("t('uiQuality.emptyState.comingSoon'");
    expect(component).toContain("t('uiQuality.emptyState.setupRequired'");
    expect(component).toContain('<Button type="button"');
  });
});
