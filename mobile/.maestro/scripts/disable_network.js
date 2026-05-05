/*
 * Disables the connected Android emulator's wifi + mobile data so the
 * app can be observed in its offline state. Maestro's runScript runs
 * inside the JVM-hosted Rhino interpreter, so we shell out via Java's
 * ProcessBuilder rather than a Node-style child_process.
 *
 * iOS Simulator has no equivalent CLI to flip "Airplane Mode", so this
 * script is a documented Android-only helper. Running offline_today on
 * iOS requires a manual toggle from Control Center between assertions.
 */
try {
  var ProcessBuilder = Java.type('java.lang.ProcessBuilder');
  var commands = [
    ['adb', 'shell', 'svc', 'wifi', 'disable'],
    ['adb', 'shell', 'svc', 'data', 'disable'],
  ];
  for (var i = 0; i < commands.length; i++) {
    var p = new ProcessBuilder(commands[i])
      .redirectErrorStream(true)
      .start();
    p.waitFor();
  }
  // Give @react-native-community/netinfo a moment to propagate the
  // change to onlineManager so the subsequent refetch sees offline.
  Java.type('java.lang.Thread').sleep(2500);
} catch (e) {
  console.log('disable_network failed: ' + e);
}
