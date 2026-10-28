// @vitest-environment node
import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const projectFile = (path) => new URL(`../../${path}`, import.meta.url);

describe('approved Syroce brand assets', () => {
  it('keeps the approved circular logo and responsive variants available', () => {
    for (const asset of ['syroce-circle.png', 'syroce-circle-128.webp', 'syroce-circle-256.webp', 'syroce-circle-512.webp', 'syroce-logo.svg', 'syroce-icon.svg']) {
      expect(existsSync(projectFile(`public/${asset}`)), asset).toBe(true);
    }
  });

  it('does not ship either identical obsolete logo PNG', () => {
    expect(existsSync(projectFile('public/syroce-logo.png'))).toBe(false);
    expect(existsSync(projectFile('src/assets/syroce-logo.png'))).toBe(false);
  });

  it('keeps the workspace header on the current SVG logo', () => {
    const layout = readFileSync(projectFile('src/components/Layout.jsx'), 'utf8');
    expect(layout).toContain('src="/syroce-logo.svg"');
    expect(layout).not.toContain('syroce-logo.png');
  });

  it('keeps sign-in and landing views on the approved circular family', () => {
    const auth = readFileSync(projectFile('src/pages/AuthPage.jsx'), 'utf8');
    const landing = readFileSync(projectFile('src/pages/LandingPage.jsx'), 'utf8');
    expect(auth).toContain('/syroce-circle.png');
    expect(auth).toContain('/syroce-circle-256.webp');
    expect(landing).toContain('/syroce-circle-256.webp');
    expect(auth + landing).not.toContain('syroce-logo.png');
  });
});
