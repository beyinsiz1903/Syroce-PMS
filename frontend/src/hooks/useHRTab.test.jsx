import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, useNavigate, useLocation } from 'react-router-dom';
import { useHRTab } from './useHRTab';

function Harness() {
  const [tab, change] = useHRTab();
  const navigate = useNavigate();
  const location = useLocation();
  return <>
    <output data-testid="tab">{tab}</output>
    <output data-testid="url">{location.search}</output>
    <button onClick={() => navigate('/hr?tab=leave&id=qa')}>Notification</button>
    <button onClick={() => change('overtime')}>Overtime</button>
    <button onClick={() => navigate(-1)}>Back</button>
  </>;
}

it('opens the requested tab on direct load', () => {
  render(<MemoryRouter initialEntries={['/hr?tab=leave&id=qa']}><Harness /></MemoryRouter>);
  expect(screen.getByTestId('tab')).toHaveTextContent('leave');
});

it('tracks same-page notification navigation, manual tabs and browser back', () => {
  render(<MemoryRouter initialEntries={['/hr?tab=payroll']}><Harness /></MemoryRouter>);
  fireEvent.click(screen.getByText('Notification'));
  expect(screen.getByTestId('tab')).toHaveTextContent('leave');
  fireEvent.click(screen.getByText('Overtime'));
  expect(screen.getByTestId('tab')).toHaveTextContent('overtime');
  expect(screen.getByTestId('url')).not.toHaveTextContent('id=qa');
  fireEvent.click(screen.getByText('Back'));
  expect(screen.getByTestId('tab')).toHaveTextContent('leave');
});

it('ignores unsupported tab values', () => {
  render(<MemoryRouter initialEntries={['/hr?tab=unknown']}><Harness /></MemoryRouter>);
  expect(screen.getByTestId('tab')).toHaveTextContent('attendance');
});
