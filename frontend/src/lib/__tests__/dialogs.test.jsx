import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, act, fireEvent, cleanup } from '@testing-library/react';
import DialogHost from '@/components/DialogHost';
import { confirmDialog, promptDialog } from '@/lib/dialogs';

function flush() {
  return act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe('dialog system', () => {
  afterEach(() => {
    cleanup();
  });

  describe('confirmDialog', () => {
    it('resolves true when confirm is clicked', async () => {
      render(<DialogHost />);
      let result;
      const promise = confirmDialog({ message: 'Emin misiniz?' }).then((v) => { result = v; });
      await flush();

      expect(screen.getByTestId('app-dialog')).toBeInTheDocument();
      expect(screen.getByText('Emin misiniz?')).toBeInTheDocument();

      fireEvent.click(screen.getByTestId('dialog-confirm-btn'));
      await promise;
      expect(result).toBe(true);
    });

    it('resolves false when cancel is clicked', async () => {
      render(<DialogHost />);
      let result;
      const promise = confirmDialog({ message: 'Sil mi?' }).then((v) => { result = v; });
      await flush();

      fireEvent.click(screen.getByTestId('dialog-cancel-btn'));
      await promise;
      expect(result).toBe(false);
    });
  });

  describe('promptDialog', () => {
    it('returns the typed value on Enter', async () => {
      render(<DialogHost />);
      let result;
      const promise = promptDialog({ message: 'Adınız?' }).then((v) => { result = v; });
      await flush();

      const input = screen.getByTestId('dialog-prompt-input');
      fireEvent.change(input, { target: { value: 'Ahmet' } });
      // jsdom does not auto-submit form on Enter inside <input>; trigger submit explicitly
      fireEvent.submit(input.closest('form'));

      await promise;
      expect(result).toBe('Ahmet');
    });

    it('returns null on Escape (cancel)', async () => {
      render(<DialogHost />);
      let result = 'unset';
      const promise = promptDialog({ message: 'Not?' }).then((v) => { result = v; });
      await flush();

      const input = screen.getByTestId('dialog-prompt-input');
      fireEvent.keyDown(input, { key: 'Escape' });
      // jsdom does not auto-trigger Radix's Escape→close; close via overlay handler
      fireEvent.keyDown(document.body, { key: 'Escape' });

      await promise;
      expect(result).toBeNull();
    });

    it('returns the default value when confirmed without changes', async () => {
      render(<DialogHost />);
      let result;
      const promise = promptDialog({ message: 'İsim?', defaultValue: 'varsayılan' })
        .then((v) => { result = v; });
      await flush();

      fireEvent.click(screen.getByTestId('dialog-confirm-btn'));
      await promise;
      expect(result).toBe('varsayılan');
    });
  });

  describe('FIFO queue', () => {
    it('shows two concurrent dialogs sequentially in order', async () => {
      render(<DialogHost />);
      const results = [];

      const p1 = confirmDialog({ message: 'first' }).then((v) => results.push(['first', v]));
      const p2 = confirmDialog({ message: 'second' }).then((v) => results.push(['second', v]));
      await flush();

      // Only the first dialog is visible
      expect(screen.getByText('first')).toBeInTheDocument();
      expect(screen.queryByText('second')).not.toBeInTheDocument();

      fireEvent.click(screen.getByTestId('dialog-confirm-btn'));
      await p1;
      await flush();

      // Now the second should be visible
      expect(screen.getByText('second')).toBeInTheDocument();
      expect(screen.queryByText('first')).not.toBeInTheDocument();

      fireEvent.click(screen.getByTestId('dialog-cancel-btn'));
      await p2;

      expect(results).toEqual([
        ['first', true],
        ['second', false],
      ]);
    });
  });

  describe('DialogHost unmount', () => {
    it('resolves a pending dialog when host unmounts', async () => {
      const { unmount } = render(<DialogHost />);
      let result = 'unset';
      const promise = confirmDialog({ message: 'pending' }).then((v) => { result = v; });
      await flush();

      expect(screen.getByText('pending')).toBeInTheDocument();

      unmount();
      await promise;
      expect(result).toBeUndefined();
    });

  });
});
