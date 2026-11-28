const REQUIRED = ['Syroce PMS CI/CD Pipeline', 'Frontend Quality Gates'];

// Full backend coverage can outlast the frontend workflow by over ten
// minutes. Allow up to thirty minutes for the same revision, retaining
// failure, supersession and successful-check guards on every poll.
module.exports = async function gate({ github, context, core, sha, sleep = ms => new Promise(resolve => setTimeout(resolve, ms)), attempts = 90 }) {
  const repo = { owner: context.repo.owner, repo: context.repo.repo };
  core.setOutput('ready', 'false');
  for (let attempt = 0; attempt < attempts; attempt++) {
    const main = await github.rest.repos.getBranch({ ...repo, branch: 'main' });
    if (main.data.commit.sha !== sha) {
      core.notice('Superseded revision: not deploying.');
      return;
    }
    const runs = await github.paginate(github.rest.actions.listWorkflowRunsForRepo, {
      ...repo, head_sha: sha, branch: 'main', event: 'push', per_page: 100
    });
    const latest = REQUIRED.map(name => runs.filter(r => r.name === name).sort((a, b) => b.id - a.id)[0]);
    const failed = latest.find(r => r?.status === 'completed' && r.conclusion !== 'success');
    if (failed) {
      core.setFailed(`Required workflow ${failed.name} ended with ${failed.conclusion}; no deployment performed.`);
      return;
    }
    if (latest.every(r => r?.status === 'completed' && r.conclusion === 'success')) {
      core.setOutput('ready', 'true');
      return;
    }
    core.info(`Waiting for exact-revision checks (${attempt + 1}/${attempts}): ${latest.map((r, i) => `${REQUIRED[i]}=${r?.status || 'missing'}`).join(', ')}`);
    if (attempt + 1 < attempts) await sleep(20000);
  }
  core.setFailed('Required workflows are still pending after the readiness window; no deployment performed. Rerun after both checks pass.');
};
