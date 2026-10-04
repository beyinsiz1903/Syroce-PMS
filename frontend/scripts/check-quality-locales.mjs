import { readdir, readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const localesDirectory = join(scriptDirectory, "..", "src", "locales");
const requiredStates = ["empty", "forbidden", "setup", "error", "throttled", "staleVersion"];
const requiredActions = ["retry", "retryAgain", "loadLatestVersion", "continue", "backToDashboard"];

const localeFiles = (await readdir(localesDirectory)).filter((file) => file.endsWith(".json"));
const missing = [];

for (const localeFile of localeFiles) {
  const locale = JSON.parse(await readFile(join(localesDirectory, localeFile), "utf8"));
  for (const state of requiredStates) {
    if (!locale.uiQuality?.states?.[state]?.title || !locale.uiQuality?.states?.[state]?.description) {
      missing.push(`${localeFile}: uiQuality.states.${state}.{title,description}`);
    }
  }
  for (const action of requiredActions) {
    if (!locale.uiQuality?.actions?.[action]) {
      missing.push(`${localeFile}: uiQuality.actions.${action}`);
    }
  }
}

if (missing.length) {
  console.error("Product quality state translations are incomplete:\n" + missing.join("\n"));
  process.exit(1);
}

console.log(`Verified product quality state translations in ${localeFiles.length} locales.`);
