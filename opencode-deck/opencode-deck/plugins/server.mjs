import {Bridge, Facts, registration} from './core.mjs';

// Conventional globally loaded server plugin. No npm package dependencies.
export async function DeckBridge({client, directory}) {
  if (process.argv.some(a => ['serve', 'run', 'web', 'acp'].includes(a)) && !process.env.OCDECK_BINDING) return {};
  const globalKey = Symbol.for('ryan.ocdeck.server.instance');
  // OpenCode may initialize its server plugin more than once per process.
  // Reuse one adapter; do not allocate a key per project initialization.
  if (globalThis[globalKey]) return globalThis[globalKey];
  let reg;
  // Bindings can appear a few milliseconds after process creation.
  try { reg = await registration(); } catch { return {}; }
  if (!reg) return {};
  const facts = new Facts();
  let eventRevision = 0;
  let lastReconcile = 0;
  let lastError = 0;
  async function reconcile() {
    if (Date.now() - lastReconcile < 4000) return;
    lastReconcile = Date.now();
    const revision = eventRevision;
    // These list methods differ between SDK generations. Missing methods are
    // a diagnosed limitation; live events still provide pending request state.
    const jobs = [];
    if (client.session?.status) jobs.push(['status', client.session.status({query: {directory}})]);
    if (client.permission?.list) jobs.push(['permissions', client.permission.list({query: {directory}})]);
    if (client.question?.list) jobs.push(['questions', client.question.list({query: {directory}})]);
    const results = await Promise.all(jobs.map(async ([key, p]) => [key, await Promise.race([
      p, new Promise((_, reject) => setTimeout(() => reject(Error('Snapshot timed out')), 1000))]) ]));
    if (eventRevision !== revision) return; // Never overwrite an intervening event.
    for (const [key, response] of results) {
      if (response.error) throw Error(`OpenCode ${key} snapshot failed`);
      const data = response.data;
      if (key === 'status' && data && !Array.isArray(data)) {
        for (const [id, s] of facts.sessions) s.status = data[id]?.type || 'idle';
        for (const [id, status] of Object.entries(data)) facts.session(id).status = status.type;
      } else if (Array.isArray(data)) {
        for (const s of facts.sessions.values()) s[key].clear();
        for (const r of data) facts.session(r.sessionID)[key].add(r.id);
      }
    }
    facts.trusted = true;
    if (facts.detail === 'OpenCode snapshot unavailable') facts.detail = '';
  }
  const bridge = new Bridge({registration: reg,
    readSnapshot: async () => {
      try { await reconcile(); }
      catch { facts.trusted = false; facts.detail = 'OpenCode snapshot unavailable'; }
      return facts.snapshot();
    },
    onError: error => {
      if (Date.now() - lastError < 30000) return;
      lastError = Date.now();
      try { Promise.resolve(client.app?.log?.({body: {service: 'ocdeck', level: 'warn', message: error}})).catch(() => {}); } catch {}
    }});
  bridge.start();
  const hooks = {
    event: async ({event}) => {
      if (/^(session\.|permission\.|question\.)/.test(event.type)) {
        eventRevision++; facts.event(event); void bridge.flush();
      }
    },
    dispose: async () => { await bridge.close(); delete globalThis[globalKey]; }
  };
  globalThis[globalKey] = hooks;
  return hooks;
}
