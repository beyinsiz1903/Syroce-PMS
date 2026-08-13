import { describe, expect, it } from 'vitest';

import { resolutionSuccessMessage } from '../ServiceRecovery';

describe('ServiceRecovery resolution feedback', () => {
  it('does not claim that email was sent when the backend did not send one', () => {
    expect(resolutionSuccessMessage(false)).toBe('Şikayet çözüldü');
  });

  it('mentions email only when the backend confirms delivery', () => {
    expect(resolutionSuccessMessage(true)).toContain('e-postası gönderildi');
  });
});
