/*
 * Restores wifi + mobile data on the connected Android emulator after
 * an offline assertion. Best-effort cleanup — failures are logged but
 * never fail the flow, since CI runners typically tear the emulator
 * down between suites anyway.
 */
try {
  var ProcessBuilder = Java.type('java.lang.ProcessBuilder');
  var commands = [
    ['adb', 'shell', 'svc', 'wifi', 'enable'],
    ['adb', 'shell', 'svc', 'data', 'enable'],
  ];
  for (var i = 0; i < commands.length; i++) {
    var p = new ProcessBuilder(commands[i])
      .redirectErrorStream(true)
      .start();
    p.waitFor();
  }
} catch (e) {
  console.log('enable_network failed: ' + e);
}
