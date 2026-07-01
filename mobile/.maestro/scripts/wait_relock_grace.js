/*
 * Sleeps long enough to exceed RELOCK_GRACE_MS (5 000 ms in
 * BiometricLockGate.tsx) so a background → foreground transition
 * actually triggers the re-lock instead of being treated as a quick
 * app-switch (e.g. opening the camera for an ID scan).
 */
try {
  Java.type('java.lang.Thread').sleep(6000);
} catch (e) {
  console.log('wait_relock_grace failed: ' + e);
}
