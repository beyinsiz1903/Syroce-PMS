import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { KpiCard } from '@/components/ui/kpi-card';

afterEach(() => cleanup());

describe('KpiCard', () => {
  it('label + value render eder', () => {
    render(<KpiCard label="Doluluk" value="78%" />);
    expect(screen.getByText('Doluluk')).toBeInTheDocument();
    expect(screen.getByText('78%')).toBeInTheDocument();
  });

  it('sub propu varsa subtitle gösterir', () => {
    render(<KpiCard label="Misafir" value="42" sub="Bugün geliş" />);
    expect(screen.getByText('Bugün geliş')).toBeInTheDocument();
  });

  it('Icon prop: ikon render eder', () => {
    const FakeIcon = (props) => <svg data-testid="kpi-icon" {...props} />;
    render(<KpiCard icon={FakeIcon} label="X" value="1" />);
    expect(screen.getByTestId('kpi-icon')).toBeInTheDocument();
  });

  it('intent palette: success → emerald border class uygular', () => {
    const { container } = render(<KpiCard label="OK" value="1" intent="success" />);
    expect(container.firstChild.className).toContain('border-l-emerald-500');
  });

  it('intent palette: warning → amber border', () => {
    const { container } = render(<KpiCard label="W" value="1" intent="warning" />);
    expect(container.firstChild.className).toContain('border-l-amber-500');
  });

  it('intent palette: danger → rose border', () => {
    const { container } = render(<KpiCard label="D" value="1" intent="danger" />);
    expect(container.firstChild.className).toContain('border-l-rose-500');
  });

  it('intent geçersizse default fallback (slate)', () => {
    const { container } = render(<KpiCard label="X" value="1" intent="bogus" />);
    expect(container.firstChild.className).toContain('border-l-slate-300');
  });

  it('non-interactive (onClick yok): role=button YOK, tabIndex=undefined', () => {
    const { container } = render(<KpiCard label="X" value="1" />);
    const card = container.firstChild;
    expect(card.getAttribute('role')).toBeNull();
    expect(card.getAttribute('tabindex')).toBeNull();
  });

  it('interactive (onClick var): role=button + tabIndex=0 + cursor-pointer', () => {
    const onClick = vi.fn();
    const { container } = render(<KpiCard label="X" value="1" onClick={onClick} />);
    const card = container.firstChild;
    expect(card.getAttribute('role')).toBe('button');
    expect(card.getAttribute('tabindex')).toBe('0');
    expect(card.className).toContain('cursor-pointer');
  });

  it('interactive: click handler tetiklenir', () => {
    const onClick = vi.fn();
    const { container } = render(<KpiCard label="X" value="1" onClick={onClick} />);
    fireEvent.click(container.firstChild);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('interactive: Enter tuşu onClick tetikler (a11y)', () => {
    const onClick = vi.fn();
    const { container } = render(<KpiCard label="X" value="1" onClick={onClick} />);
    fireEvent.keyDown(container.firstChild, { key: 'Enter' });
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('interactive: Space tuşu onClick tetikler (a11y)', () => {
    const onClick = vi.fn();
    const { container } = render(<KpiCard label="X" value="1" onClick={onClick} />);
    fireEvent.keyDown(container.firstChild, { key: ' ' });
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('interactive: rastgele tuş onClick tetiklemez', () => {
    const onClick = vi.fn();
    const { container } = render(<KpiCard label="X" value="1" onClick={onClick} />);
    fireEvent.keyDown(container.firstChild, { key: 'a' });
    expect(onClick).not.toHaveBeenCalled();
  });

  it('active=true → ring class uygular ve aria-pressed=true', () => {
    const onClick = vi.fn();
    const { container } = render(<KpiCard label="X" value="1" onClick={onClick} active />);
    const card = container.firstChild;
    expect(card.className).toContain('ring-2');
    expect(card.getAttribute('aria-pressed')).toBe('true');
  });

  it('highlight=true → amber bg uygular', () => {
    const { container } = render(<KpiCard label="X" value="1" highlight />);
    expect(container.firstChild.className).toContain('bg-amber-50');
  });
});
