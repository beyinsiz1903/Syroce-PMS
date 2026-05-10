import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { PageHeader } from '@/components/ui/page-header';

afterEach(() => cleanup());

describe('PageHeader', () => {
  it('title h1 olarak render eder', () => {
    render(<PageHeader title="Rezervasyonlar" />);
    const h1 = screen.getByRole('heading', { level: 1 });
    expect(h1).toHaveTextContent('Rezervasyonlar');
  });

  it('subtitle render eder', () => {
    render(<PageHeader title="X" subtitle="Bugün 12 misafir" />);
    expect(screen.getByText('Bugün 12 misafir')).toBeInTheDocument();
  });

  it('subtitle yoksa subtitle DOM\'da yer almaz', () => {
    const { container } = render(<PageHeader title="X" />);
    expect(container.querySelectorAll('p').length).toBe(0);
  });

  it('icon prop: icon kutusu render eder', () => {
    const FakeIcon = (props) => <svg data-testid="hdr-icon" {...props} />;
    render(<PageHeader icon={FakeIcon} title="X" />);
    expect(screen.getByTestId('hdr-icon')).toBeInTheDocument();
  });

  it('icon yoksa icon kutusu render edilmez', () => {
    const { container } = render(<PageHeader title="X" />);
    expect(container.querySelector('.bg-slate-100')).toBeNull();
  });

  it('actions slot: sağda render eder', () => {
    render(
      <PageHeader
        title="X"
        actions={<button data-testid="hdr-act">Yenile</button>}
      />
    );
    expect(screen.getByTestId('hdr-act')).toBeInTheDocument();
  });

  it('actions yoksa actions wrapper yok', () => {
    const { container } = render(<PageHeader title="X" />);
    expect(container.querySelectorAll('div.flex.flex-wrap').length).toBe(0);
  });

  it('className prop: dış className eklenir', () => {
    const { container } = render(<PageHeader title="X" className="my-custom" />);
    expect(container.firstChild.className).toContain('my-custom');
  });
});
