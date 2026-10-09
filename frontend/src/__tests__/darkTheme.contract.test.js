import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import postcss from 'postcss';

const css = readFileSync('src/index.css', 'utf8');
const appCss = readFileSync('src/App.css', 'utf8');
const tokens = {};
postcss.parse(css).walkRules('.dark', rule => {
  rule.walkDecls(decl => { tokens[decl.prop] = decl.value; });
});
const rgb = value => {
  if (value.startsWith('#')) return value.slice(1).match(/../g).map(x => parseInt(x, 16) / 255);
  const [h, s, l] = value.match(/[\d.]+/g).map(Number);
  const a = (s / 100) * Math.min(l / 100, 1 - l / 100);
  return [0, 8, 4].map(n => {
    const k = (n + h / 30) % 12;
    return l / 100 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
  });
};
const luminance = value => rgb(value).map(c => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  .reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0);
const contrast = (a, b) => {
  const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (values[0] + 0.05) / (values[1] + 0.05);
};

describe('dark theme readability contracts', () => {
  it.each([
    ['foreground', 'background'], ['card-foreground', 'card'],
    ['muted-foreground', 'card'], ['muted-foreground', 'muted'],
    ['primary-foreground', 'primary'], ['ring', 'card'],
    ...['arrival', 'stay', 'departure'].flatMap(state => [
      [`calendar-${state}-text`, `calendar-${state}-bg`],
      [`calendar-${state}-muted`, `calendar-${state}-bg`],
    ]),
  ])('%s on %s has at least 4.5:1 contrast', (text, background) => {
    expect(contrast(tokens[`--${text}`], tokens[`--${background}`])).toBeGreaterThanOrEqual(4.5);
  });

  it('overrides legacy body ink and canvas only in dark mode', () => {
    const rules = {};
    postcss.parse(appCss).walkRules('html.dark body', rule => {
      rule.walkDecls(decl => { rules[decl.prop] = decl.value; });
    });
    expect(rules).toMatchObject({
      color: 'hsl(var(--foreground))',
      background: 'hsl(var(--background))',
      'color-scheme': 'dark',
    });
  });
});
