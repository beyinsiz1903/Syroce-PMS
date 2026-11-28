const { test } = require('node:test');
const assert = require('node:assert/strict');
const gate = require('./deploy-readiness.cjs');
const names = ['Syroce PMS CI/CD Pipeline', 'Frontend Quality Gates'];
const green = () => names.map((name, id) => ({ name, id, status: 'completed', conclusion: 'success' }));
async function run(batches, main = 'sha', options = {}) {
  const outputs = {}; const failures = []; let calls = 0;
  await gate({ sha: 'sha', attempts: 2, ...options, sleep: async () => {}, context: { repo: { owner: 'o', repo: 'r' } },
    core: { setOutput: (k,v) => outputs[k]=v, setFailed: m => failures.push(m), notice() {}, info() {} },
    github: { rest: { repos: { getBranch: async () => ({ data: { commit: { sha: main } } }) }, actions: { listWorkflowRunsForRepo() {} } },
      paginate: async (_, params) => { assert.equal(params.head_sha, 'sha'); assert.equal(params.event, 'push'); return batches[Math.min(calls++, batches.length-1)]; } }
  }); return { outputs, failures, calls };
}
test('waits for pending counterpart then deploys', async () => {
  const pending = green(); pending[0].status='in_progress'; pending[0].conclusion=null;
  const r=await run([pending,green()]); assert.equal(r.calls,2); assert.equal(r.outputs.ready,'true'); assert.equal(r.failures.length,0);
});
test('failed checks fail deployment gate', async () => { const rows=green(); rows[0].conclusion='failure'; const r=await run([rows]); assert.equal(r.outputs.ready,'false'); assert.equal(r.failures.length,1); });
test('pending timeout is not green', async () => { const r=await run([[]]); assert.equal(r.outputs.ready,'false'); assert.equal(r.failures.length,1); });
test('superseded revision never deploys', async () => { const r=await run([green()],'new'); assert.equal(r.calls,0); assert.equal(r.outputs.ready,'false'); });
test('latest rerun takes precedence over earlier success', async () => { const rows=green(); rows.push({ ...rows[0], id:99,status:'completed',conclusion:'cancelled' }); const r=await run([rows]); assert.equal(r.outputs.ready,'false'); assert.equal(r.failures.length,1); });

test('default window accommodates full CI beyond ten minutes without releasing early', async () => {
  const pending = green(); pending[0].status = 'in_progress'; pending[0].conclusion = null;
  const r = await run([...Array(31).fill(pending), green()], 'sha', { attempts: undefined });
  assert.equal(r.calls, 32);
  assert.equal(r.outputs.ready, 'true');
  assert.equal(r.failures.length, 0);
});
