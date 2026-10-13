import React, { useState } from 'react';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import WhatsAppConsent from './WhatsAppConsent';

afterEach(cleanup);
function Form({ phone = '+905551112233', identity = 'guest', open = true }) {
  const [value, setValue] = useState(false);
  return <WhatsAppConsent phone={phone} identity={identity} open={open} value={value} onChange={setValue} />;
}
it('starts unchecked and clears consent on recipient changes and reopen', () => {
  const { rerender } = render(<Form />);
  const box = screen.getByRole('checkbox');
  expect(box.checked).toBe(false);
  fireEvent.click(box);
  expect(box.checked).toBe(true);
  rerender(<Form identity="other" />);
  expect(box.checked).toBe(false);
  fireEvent.click(box);
  rerender(<Form identity="other" phone="+905559999999" />);
  expect(box.checked).toBe(false);
  fireEvent.click(box);
  rerender(<Form open={false} />);
  rerender(<Form />);
  expect(box.checked).toBe(false);
});
it('does not permit consent without a phone', () => {
  render(<Form phone="" />);
  expect(screen.getByRole('checkbox').disabled).toBe(true);
});
