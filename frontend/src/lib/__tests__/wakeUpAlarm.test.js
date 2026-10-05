import { beforeEach, describe, expect, it } from 'vitest';
import {
  getWakeUpAlarmSettings,
  saveWakeUpAlarmSettings,
  snoozeWakeUpTime,
  wakeUpAlertIdentity,
  WAKEUP_VOLUME_OPTIONS,
} from '@/lib/wakeUpAlarm';

describe('wakeUpAlarm', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('uses a quiet disabled default and persists reception settings', () => {
    expect(getWakeUpAlarmSettings()).toEqual({ enabled: false, volume: 'low' });

    saveWakeUpAlarmSettings({ enabled: true, volume: 'normal' });

    expect(getWakeUpAlarmSettings()).toEqual({ enabled: true, volume: 'normal' });
    expect(WAKEUP_VOLUME_OPTIONS.low.gain).toBeLessThan(WAKEUP_VOLUME_OPTIONS.normal.gain);
    expect(WAKEUP_VOLUME_OPTIONS.low.gain).toBeLessThanOrEqual(0.06);
  });

  it('creates a new alert identity after a call is snoozed', () => {
    const original = { id: 'call-1', wake_date: '2026-08-30', wake_time: '07:00' };
    const snoozed = { ...original, wake_time: '07:05' };

    expect(wakeUpAlertIdentity(original)).not.toBe(wakeUpAlertIdentity(snoozed));
  });

  it('moves a five-minute snooze across the Istanbul midnight boundary', () => {
    expect(snoozeWakeUpTime({ wake_date: '2026-08-30', wake_time: '23:58' }, 5)).toEqual({
      wake_date: '2026-08-31',
      wake_time: '00:03',
    });
  });
});
