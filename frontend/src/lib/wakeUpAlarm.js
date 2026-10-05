export const WAKEUP_ALARM_EVENT = 'syroce:wakeup-alarm-settings';
export const WAKEUP_ALARM_SETTINGS_KEY = 'syroce-wakeup-alarm-settings-v1';
export const WAKEUP_ALERTED_KEY = 'syroce-wakeup-alerted-v1';

export const WAKEUP_VOLUME_OPTIONS = {
  silent: { label: 'Yalnız görsel', gain: 0 },
  low: { label: 'Düşük ses', gain: 0.055 },
  normal: { label: 'Normal ses', gain: 0.12 },
};

const DEFAULT_SETTINGS = { enabled: false, volume: 'low' };
let alarmContext = null;

export function getWakeUpAlarmSettings() {
  if (typeof window === 'undefined') return DEFAULT_SETTINGS;
  try {
    const stored = JSON.parse(window.localStorage.getItem(WAKEUP_ALARM_SETTINGS_KEY) || '{}');
    return {
      enabled: Boolean(stored.enabled),
      volume: WAKEUP_VOLUME_OPTIONS[stored.volume] ? stored.volume : 'low',
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveWakeUpAlarmSettings(next) {
  const current = getWakeUpAlarmSettings();
  const settings = {
    enabled: next.enabled == null ? current.enabled : Boolean(next.enabled),
    volume: WAKEUP_VOLUME_OPTIONS[next.volume] ? next.volume : current.volume,
  };
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(WAKEUP_ALARM_SETTINGS_KEY, JSON.stringify(settings));
    window.dispatchEvent(new CustomEvent(WAKEUP_ALARM_EVENT, { detail: settings }));
  }
  return settings;
}

export function wakeUpAlertIdentity(call) {
  return [call?.id, call?.wake_date, String(call?.wake_time || '').slice(0, 5)].join(':');
}

export function getAlertedWakeUpIds() {
  if (typeof window === 'undefined') return new Set();
  try {
    return new Set(JSON.parse(window.localStorage.getItem(WAKEUP_ALERTED_KEY) || '[]'));
  } catch {
    return new Set();
  }
}

export function rememberWakeUpAlerts(calls) {
  if (typeof window === 'undefined') return;
  const alerted = getAlertedWakeUpIds();
  calls.forEach((call) => alerted.add(wakeUpAlertIdentity(call)));
  window.localStorage.setItem(WAKEUP_ALERTED_KEY, JSON.stringify([...alerted].slice(-300)));
}

export function todayInIstanbul(now = new Date()) {
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Europe/Istanbul', year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(now);
  } catch {
    return new Date(now.getTime() + 3 * 3600 * 1000).toISOString().split('T')[0];
  }
}

export function snoozeWakeUpTime(call, minutes = 5) {
  const scheduled = new Date(`${call.wake_date}T${String(call.wake_time).slice(0, 5)}:00+03:00`);
  scheduled.setMinutes(scheduled.getMinutes() + minutes);
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Istanbul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(scheduled);
  const part = (type) => parts.find((candidate) => candidate.type === type)?.value;
  return {
    wake_date: `${part('year')}-${part('month')}-${part('day')}`,
    wake_time: `${part('hour')}:${part('minute')}`,
  };
}

function getAlarmContext() {
  if (typeof window === 'undefined') return null;
  const Context = window.AudioContext || window.webkitAudioContext;
  if (!Context) return null;
  if (!alarmContext) {
    try {
      alarmContext = new Context();
    } catch {
      return null;
    }
  }
  return alarmContext;
}

export async function unlockWakeUpAudio() {
  const context = getAlarmContext();
  if (context?.state === 'suspended') await context.resume();
  return context;
}

export async function playWakeUpChime(volume = 'low') {
  const gainValue = WAKEUP_VOLUME_OPTIONS[volume]?.gain ?? WAKEUP_VOLUME_OPTIONS.low.gain;
  if (gainValue <= 0) return false;
  const context = await unlockWakeUpAudio();
  if (!context) return false;

  const tone = (start, frequency) => {
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = 'sine';
    oscillator.frequency.value = frequency;
    oscillator.connect(gain).connect(context.destination);
    gain.gain.setValueAtTime(0.0001, context.currentTime + start);
    gain.gain.exponentialRampToValueAtTime(gainValue, context.currentTime + start + 0.025);
    gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + start + 0.28);
    oscillator.start(context.currentTime + start);
    oscillator.stop(context.currentTime + start + 0.31);
  };

  tone(0, 660);
  tone(0.34, 820);
  return true;
}
