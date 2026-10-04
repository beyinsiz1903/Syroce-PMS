import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const app = JSON.parse(readFileSync(resolve(root, 'app.json'), 'utf8')).expo;
const eas = JSON.parse(readFileSync(resolve(root, 'eas.json'), 'utf8'));
const pkg = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'));
const errors = [];
const warnings = [];
const easProjectId = 'ea230577-f8d5-40b1-8df1-5b58dd1ea73a';

function assert(condition, message) {
  if (!condition) errors.push(message);
}

assert(app?.ios?.bundleIdentifier === 'com.syroce.pms', 'iOS bundleIdentifier com.syroce.pms olmalı.');
assert(app?.owner === 'syroces-team', 'Expo owner syroces-team olmalı.');
assert(app?.extra?.eas?.projectId === easProjectId, 'Syroce PMS EAS projectId eksik veya hatalı.');
assert(app?.updates?.url === `https://u.expo.dev/${easProjectId}`, 'EAS Update URL proje kimliğiyle eşleşmeli.');
assert(app?.android?.package === 'com.syroce.pms', 'Android package com.syroce.pms olmalı.');
assert(/^[~^]?57\./.test(pkg?.dependencies?.expo || ''), 'Expo SDK 57 bekleniyor.');
assert(/^[~^]?57\./.test(pkg?.dependencies?.['expo-updates'] || ''), 'Expo SDK 57 uyumlu expo-updates bekleniyor.');

for (const profileName of ['pilot', 'production']) {
  const profile = eas?.build?.[profileName];
  assert(profile, `${profileName} build profili eksik.`);
  assert(profile?.env?.EXPO_PUBLIC_API_URL === 'https://pms.syroce.com', `${profileName} API adresi production PMS olmalı.`);
  assert(profile?.env?.EXPO_PUBLIC_QUICKID_URL === 'https://pms.syroce.com', `${profileName} QuickID adresi production PMS olmalı.`);
}

assert(eas?.submit?.pilot?.android?.track === 'internal', 'Pilot Android gönderimi internal track kullanmalı.');
assert(eas?.submit?.pilot?.android?.releaseStatus === 'draft', 'Pilot Android sürümü draft olmalı.');

const serialized = JSON.stringify(eas);
assert(!serialized.includes('app.syroce.com'), 'Eski app.syroce.com alan adı EAS yapılandırmasında kalmamalı.');

const iosSubmit = eas?.submit?.pilot?.ios || {};
if (String(iosSubmit.ascAppId || '').startsWith('REPLACE_')) warnings.push('App Store Connect App ID henüz girilmedi.');
if (String(iosSubmit.appleTeamId || '').startsWith('REPLACE_')) warnings.push('Apple Team ID henüz girilmedi.');
if (!existsSync(resolve(root, 'play-service-account.json'))) warnings.push('Google Play service-account dosyası yerelde bulunmuyor.');

for (const warning of warnings) console.warn(`[mobile-config] UYARI: ${warning}`);
if (errors.length) {
  for (const error of errors) console.error(`[mobile-config] HATA: ${error}`);
  process.exit(1);
}

console.log(`[mobile-config] OK: pilot ve production profilleri pms.syroce.com için doğrulandı (${warnings.length} dış hesap adımı bekliyor).`);
