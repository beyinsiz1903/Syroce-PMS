import fs from 'node:fs';
import path from 'node:path';

const AUTH_DIR = path.join(process.cwd(), 'frontend', 'e2e-stress', '.auth');
const TOKEN_FILE = path.join(AUTH_DIR, 'stress-token.json');
const STATE_FILE = path.join(AUTH_DIR, 'stress-state.json');

const tokens = JSON.parse(fs.readFileSync(TOKEN_FILE, 'utf-8'));
const state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));

async function run() {
    console.log("Token length:", tokens.stress_token.length);
    const r = await fetch(state.base_url + '/api/lockdown/runtime/cockpit', {
        headers: { Authorization: `Bearer ${tokens.stress_token}` }
    });
    console.log("Status:", r.status);
    console.log("Body:", await r.text());
}
run().catch(console.error);
