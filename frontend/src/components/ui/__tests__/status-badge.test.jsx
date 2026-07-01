import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { StatusBadge } from '@/components/ui/status-badge';

afterEach(() => cleanup());

describe('StatusBadge', () => {
  it('children render eder', () => {
    render(<StatusBadge>Onaylandı</StatusBadge>);
    expect(screen.getByText('Onaylandı')).toBeInTheDocument();
  });

  it('intent palette: success → emerald classes', () => {
    const { container } = render(<StatusBadge intent="success">OK</StatusBadge>);
    expect(container.firstChild.className).toContain('bg-emerald-100');
    expect(container.firstChild.className).toContain('text-emerald-800');
  });

  it('intent palette: danger → rose classes', () => {
    const { container } = render(<StatusBadge intent="danger">Hata</StatusBadge>);
    expect(container.firstChild.className).toContain('bg-rose-100');
  });

  it('intent palette: warning → amber classes', () => {
    const { container } = render(<StatusBadge intent="warning">Uyarı</StatusBadge>);
    expect(container.firstChild.className).toContain('bg-amber-100');
  });

  it('intent palette: info → sky classes', () => {
    const { container } = render(<StatusBadge intent="info">Bilgi</StatusBadge>);
    expect(container.firstChild.className).toContain('bg-sky-100');
  });

  it('intent palette: neutral → slate classes', () => {
    const { container } = render(<StatusBadge intent="neutral">N</StatusBadge>);
    expect(container.firstChild.className).toContain('bg-slate-100');
  });

  it('default intent: slate', () => {
    const { container } = render(<StatusBadge>X</StatusBadge>);
    expect(container.firstChild.className).toContain('bg-slate-100');
  });

  it('intent geçersiz: default (slate) fallback', () => {
    const { container } = render(<StatusBadge intent="bogus">X</StatusBadge>);
    expect(container.firstChild.className).toContain('bg-slate-100');
  });

  it('icon prop: ikonu çocuktan ÖNCE render eder', () => {
    const FakeIcon = (props) => <svg data-testid="badge-icon" {...props} />;
    render(<StatusBadge icon={FakeIcon}>Tamam</StatusBadge>);
    expect(screen.getByTestId('badge-icon')).toBeInTheDocument();
  });

  it('icon yoksa ikon render edilmez', () => {
    const { container } = render(<StatusBadge>X</StatusBadge>);
    expect(container.querySelector('svg')).toBeNull();
  });

  it('extra className mevcut className ile birleşir', () => {
    const { container } = render(<StatusBadge className="ml-2">X</StatusBadge>);
    expect(container.firstChild.className).toContain('ml-2');
    expect(container.firstChild.className).toContain('rounded-md');
  });

  it('span olarak render eder (inline)', () => {
    const { container } = render(<StatusBadge>X</StatusBadge>);
    expect(container.firstChild.tagName).toBe('SPAN');
  });
});
