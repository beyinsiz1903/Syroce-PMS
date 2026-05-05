/**
 * Biometric lock helpers (V3). Wraps `expo-local-authentication` so the
 * lock-gate UI doesn't have to know about platform quirks.
 */
import * as LocalAuthentication from 'expo-local-authentication';
import { Platform } from 'react-native';

export type BiometricCapability = {
  hasHardware: boolean;
  enrolled: boolean;
  /** True when biometric prompt CAN be shown on this device. */
  available: boolean;
  /** Localised label for the supported method (Face ID / Parmak izi …). */
  label: string;
};

export async function getBiometricCapability(): Promise<BiometricCapability> {
  if (Platform.OS === 'web') {
    return { hasHardware: false, enrolled: false, available: false, label: 'Biyometrik' };
  }
  try {
    const [hasHardware, enrolled, types] = await Promise.all([
      LocalAuthentication.hasHardwareAsync(),
      LocalAuthentication.isEnrolledAsync(),
      LocalAuthentication.supportedAuthenticationTypesAsync(),
    ]);
    let label = 'Biyometrik';
    if (types.includes(LocalAuthentication.AuthenticationType.FACIAL_RECOGNITION)) {
      label = Platform.OS === 'ios' ? 'Face ID' : 'Yüz tanıma';
    } else if (types.includes(LocalAuthentication.AuthenticationType.FINGERPRINT)) {
      label = Platform.OS === 'ios' ? 'Touch ID' : 'Parmak izi';
    } else if (types.includes(LocalAuthentication.AuthenticationType.IRIS)) {
      label = 'İris';
    }
    return {
      hasHardware,
      enrolled,
      available: hasHardware && enrolled,
      label,
    };
  } catch {
    return { hasHardware: false, enrolled: false, available: false, label: 'Biyometrik' };
  }
}

/**
 * Prompt the user to authenticate with Face ID / fingerprint. Returns true
 * when the prompt succeeded. The lock gate falls back to the device PIN
 * (`disableDeviceFallback: false`) so a user without biometrics enrolled
 * can still unlock — important for mixed teams sharing a phone.
 */
export async function authenticateBiometric(reason: string): Promise<boolean> {
  if (Platform.OS === 'web') return true;
  try {
    const res = await LocalAuthentication.authenticateAsync({
      promptMessage: reason,
      cancelLabel: 'İptal',
      fallbackLabel: 'Cihaz şifresi',
      disableDeviceFallback: false,
    });
    return res.success;
  } catch {
    return false;
  }
}
