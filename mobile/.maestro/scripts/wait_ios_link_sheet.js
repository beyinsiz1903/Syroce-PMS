// Bounded runner-only wait for the asynchronous iOS custom-scheme sheet.
// Portable across Maestro JavaScript engines; no Java host access required.
var linkSheetDeadline = Date.now() + 15000;
while (Date.now() < linkSheetDeadline) {}
