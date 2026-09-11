import {Bridge, registration} from './core.mjs';

// Opt-in replacement for server adapter, after verifying installed TUI support.
export default {
  id: 'ryan.opencode.deck',
  async tui(api) {
    const reg = await registration();
    if (!reg) return;
    const known = new Set();
    const snapshot = () => {
      if (!api.state.ready) return {status: 'unknown', pending: 0};
      const route = api.route.current;
      if (route.name === 'session' && route.params?.sessionID) known.add(route.params.sessionID);
      let status = 'idle', pending = 0;
      for (const id of known) {
        const s = api.state.session.status(id);
        if (s?.type === 'busy' || s?.type === 'retry') status = 'busy';
        pending += api.state.session.permission(id).length + api.state.session.question(id).length;
      }
      return {status, pending};
    };
    const bridge = new Bridge({registration: reg, readSnapshot: snapshot});
    const events = ['session.status', 'permission.asked', 'permission.replied',
                    'question.asked', 'question.replied', 'question.rejected'];
    const unsubscribe = events.map(type => api.event.on(type, event => {
      const id = event.properties?.sessionID;
      // Include descendant activity only when its root belongs to this TUI.
      let s = id && api.state.session.get(id), visited = new Set();
      while (s?.parentID && !visited.has(s.id)) {
        visited.add(s.id);
        if (known.has(s.parentID)) { known.add(id); break; }
        s = api.state.session.get(s.parentID);
      }
      setTimeout(() => void bridge.flush(), 0);
    }));
    bridge.start();
    // Local state observation also catches TUI route changes without a server event.
    const timer = setInterval(() => void bridge.flush(), 500);
    timer.unref?.();
    api.lifecycle.onDispose(async () => {
      clearInterval(timer); unsubscribe.forEach(f => f()); await bridge.close();
    });
  }
};
