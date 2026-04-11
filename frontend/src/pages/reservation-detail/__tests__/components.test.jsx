import { render, screen } from '@testing-library/react';
import { InfoField, Avatar, EmptyState, SummaryCard, FormField } from '../helpers';

// Mock lucide-react icons
jest.mock('lucide-react', () => ({
  Loader2: (props) => <div data-testid="icon-loader" {...props} />,
  Check: (props) => <div data-testid="icon-check" {...props} />,
  FileText: (props) => <div data-testid="icon-filetext" {...props} />,
}));

describe('reservation-detail helper components', () => {
  describe('InfoField', () => {
    it('renders label and value', () => {
      render(<InfoField label="Giris Tarihi" value="15 Haz 2025" />);
      expect(screen.getByText('Giris Tarihi')).toBeInTheDocument();
      expect(screen.getByText('15 Haz 2025')).toBeInTheDocument();
    });

    it('renders with empty value', () => {
      render(<InfoField label="Oda" value="-" />);
      expect(screen.getByText('Oda')).toBeInTheDocument();
      expect(screen.getByText('-')).toBeInTheDocument();
    });
  });

  describe('Avatar', () => {
    it('renders first letter of name uppercase', () => {
      const { container } = render(<Avatar name="Mehmet" />);
      expect(container.textContent).toBe('M');
    });

    it('renders M for empty/null name', () => {
      const { container } = render(<Avatar name="" />);
      expect(container.textContent).toBe('M');
    });

    it('applies size classes', () => {
      const { container } = render(<Avatar name="Ali" size="lg" />);
      const el = container.firstChild;
      expect(el.className).toContain('w-10');
    });

    it('defaults to md size', () => {
      const { container } = render(<Avatar name="Ali" />);
      const el = container.firstChild;
      expect(el.className).toContain('w-8');
    });
  });

  describe('EmptyState', () => {
    it('renders icon and text', () => {
      const MockIcon = (props) => <div data-testid="mock-icon" {...props} />;
      render(<EmptyState icon={MockIcon} text="Kayit bulunamadi" />);
      expect(screen.getByText('Kayit bulunamadi')).toBeInTheDocument();
      expect(screen.getByTestId('mock-icon')).toBeInTheDocument();
    });
  });

  describe('SummaryCard', () => {
    it('renders label and formatted value', () => {
      render(<SummaryCard label="TOPLAM" value={1500} color="blue" />);
      expect(screen.getByText('TOPLAM')).toBeInTheDocument();
      // fmtTL formats the number
      expect(screen.getByText(/1.*500.*TL/)).toBeInTheDocument();
    });

    it('handles zero value', () => {
      render(<SummaryCard label="BAKIYE" value={0} color="green" />);
      expect(screen.getByText('BAKIYE')).toBeInTheDocument();
      expect(screen.getByText('0 TL')).toBeInTheDocument();
    });
  });

  describe('FormField', () => {
    it('renders label and input', () => {
      const onChange = jest.fn();
      render(<FormField label="Ad" value="Mehmet" onChange={onChange} />);
      expect(screen.getByText('Ad')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Mehmet')).toBeInTheDocument();
    });
  });
});
