/*
 * Dispatches a fingerprint event to the Android emulator so the OS
 * biometric prompt opened by `authenticateBiometric()` resolves with a
 * successful match. Requires that the emulator was started with at
 * least one fingerprint enrolled under id=1 (see README).
 *
 * iOS Simulator simulates Touch/Face ID via `xcrun simctl ui`, but the
 * exact incantation depends on the simulator runtime — keep this script
 * Android-only and document the iOS workaround in the README.
 */
try {
  var ProcessBuilder = Java.type('java.lang.ProcessBuilder');
  // Small delay so the OS biometric prompt has time to render before
  // we deliver the touch event.
  Java.type('java.lang.Thread').sleep(1500);
  var p = new ProcessBuilder(['adb', 'emu', 'finger', 'touch', '1'])
    .redirectErrorStream(true)
    .start();
  p.waitFor();
  // Let the prompt animate away and the React state propagate.
  Java.type('java.lang.Thread').sleep(1500);
} catch (e) {
  console.log('simulate_fingerprint failed: ' + e);
}
