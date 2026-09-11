import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';

export class Facts {
  constructor() { this.sessions = new Map(); this.trusted = true; this.detail = ''; }
  session(id) {
    if (!this.sessions.has(id)) this.sessions.set(id, {status: 'idle', permissions: new Set(), questions: new Set()});
    return this.sessions.get(id);
  }
  event(event) {
    const p = event.properties || {};
    const id = p.sessionID || p.info?.id;
    if (!id) return;
    const s = this.session(id);
    switch (event.type) {
      case 'session.status': s.status = p.status?.type || 'unknown'; break;
      case 'session.idle': s.status = 'idle'; break;
      case 'permission.asked': s.permissions.add(p.id); break;
      case 'permission.replied': s.permissions.delete(p.requestID); break;
      case 'question.asked': s.questions.add(p.id); break;
      case 'question.replied': case 'question.rejected': s.questions.delete(p.requestID); break;
      case 'session.deleted': this.sessions.delete(id); break;
      case 'session.error': this.detail = 'Session error; inspect terminal'; break;
    }
  }
  snapshot() {
    let pending = 0, status = 'idle';
    for (const s of this.sessions.values()) {
      pending += s.permissions.size + s.questions.size;
      if (s.status === 'unknown') status = 'unknown';
      else if (status !== 'unknown' && ['busy', 'retry'].includes(s.status)) status = 'busy';
    }
    return {status: this.trusted ? status : 'unknown', pending, detail: this.detail};
  }
}

export class Bridge {
  constructor({root, registration, readSnapshot, onError = () => {}}) {
    this.root = root || process.env.OCDECK_HOME || path.join(os.homedir(), '.opencode-deck');
    this.registration = registration;
    this.readSnapshot = readSnapshot;
    this.onError = onError;
    this.producer = crypto.randomUUID(); this.seq = 0;
    this.closed = false; this.busy = false; this.dirty = false; this.timer = null;
  }
  async call(method, route, body) {
    const discovery = JSON.parse(await fs.readFile(path.join(this.root, 'discovery.json'), 'utf8'));
    const token = (await fs.readFile(path.join(this.root, 'token'), 'utf8')).trim();
    if (!Number.isInteger(discovery.port) || discovery.port < 1 || discovery.port > 65535) throw Error('Bad discovery port');
    const response = await fetch(`http://127.0.0.1:${discovery.port}${route}`, {
      method, headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'},
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(1200)
    });
    if (!response.ok) throw Error(`Broker HTTP ${response.status}`);
    return response.json();
  }
  start() {
    this.timer = setInterval(() => void this.flush(), 2000);
    this.timer.unref?.();
    void this.flush();
  }
  async flush() {
    if (this.closed) return;
    if (this.busy) { this.dirty = true; return; }
    this.busy = true;
    try {
      await this.call('POST', '/v1/register', this.registration);
      const value = await this.readSnapshot();
      if (!this.closed) await this.call('PUT', `/v1/instances/${encodeURIComponent(this.registration.id)}`,
        {...value, producer: this.producer, seq: ++this.seq});
    } catch (e) { this.onError(String(e)); }
    finally {
      this.busy = false;
      if (this.dirty && !this.closed) {
        this.dirty = false;
        setTimeout(() => void this.flush(), 0);
      }
    }
  }
  async close() {
    this.closed = true; clearInterval(this.timer);
    // For wrapper-managed instances the process supervisor owns removal.
    if (!this.registration.managed) {
      try { await this.call('DELETE', `/v1/instances/${encodeURIComponent(this.registration.id)}`); } catch {}
    }
  }
}

export async function registration() {
  // Launcher writes identity using psutil's exact process creation timestamp.
  const root = process.env.OCDECK_HOME || path.join(os.homedir(), '.opencode-deck');
  if (process.env.OCDECK_BINDING) {
    const r = JSON.parse(await fs.readFile(process.env.OCDECK_BINDING, 'utf8'));
    // First OpenCode runtime claims this launch. Nested headless OpenCode jobs
    // inherit environment variables but cannot claim the parent's button.
    const claim = process.env.OCDECK_BINDING + '.claim';
    try {
      const f = await fs.open(claim, 'wx');
      await f.writeFile(String(process.pid)); await f.close();
    } catch (e) {
      if (e.code !== 'EEXIST') throw e;
      const owner = Number(await fs.readFile(claim, 'utf8'));
      if (owner !== process.pid) return null;
    }
    return {...r, managed: true};
  }
  // Outside a managed launch, use the Python helper solely for exact PID identity.
  const install = JSON.parse((await fs.readFile(path.join(root, 'install.json'), 'utf8')).replace(/^\uFEFF/, ''));
  const {execFile} = await import('node:child_process');
  const info = await new Promise((resolve, reject) => execFile(install.python,
    ['-m', 'ocdeck', 'identity', String(process.pid)], {timeout: 2500, windowsHide: true},
    (error, stdout) => error ? reject(error) : resolve(JSON.parse(stdout))));
  return {id: crypto.randomUUID(), process: info, label: path.basename(process.cwd()) || 'OpenCode', windowToken: ''};
}
