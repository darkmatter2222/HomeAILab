import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from .common import home, atomic_json, read_json, identity, request


def route(args):
    """Global opencode shim: wrap interactive launches; pass CLI utilities through."""
    commands = {'run', 'serve', 'web', 'acp', 'auth', 'models', 'upgrade', 'uninstall',
                'mcp', 'session', 'export', 'import', 'github', 'pr', 'stats', 'debug',
                'agent', 'completion', 'db', 'plugin'}
    passthrough = any(a in ('--help', '-h', '--version', '-v') for a in args) or (args and args[0] in commands)
    if not passthrough:
        launch(args)
        return 0
    root = home()
    install = read_json(root / 'install.json')
    spec = root / 'launches' / (str(uuid.uuid4()) + '.json')
    atomic_json(spec, {'cwd': os.getcwd(), 'args': args, 'executable': install['opencode']})
    try:
        return subprocess.call(['powershell.exe', '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                               '-File', str(Path(install['source']) / 'scripts' / 'Run-OpenCode.ps1'),
                               '-LaunchFile', str(spec)])
    finally:
        spec.unlink(missing_ok=True)


def launch(args, cwd=None):
    if os.name != 'nt':
        raise RuntimeError('Managed launcher requires Windows; see docs/REMOTE-AND-WSL.md')
    root = home()
    install = read_json(root / 'install.json')
    if not install:
        raise RuntimeError('Run scripts/Install.ps1 first')
    wt = shutil.which('wt.exe')
    if not wt:
        raise RuntimeError('Windows Terminal (wt.exe) is required for managed windows')
    key = str(uuid.uuid4())
    spec = root / 'launches' / (key + '.json')
    token = 'OpenCode [' + key + ']'
    atomic_json(spec, {'id': key, 'args': args, 'cwd': cwd or os.getcwd(), 'windowToken': token})
    subprocess.Popen([wt, '-w', key, 'new-tab', '--title', token, '--suppressApplicationTitle',
                      sys.executable, '-m', 'ocdeck', 'worker', str(spec)],
                     close_fds=True)


def worker(spec_path):
    root = home()
    spec_path = Path(spec_path)
    spec = read_json(spec_path)
    install = read_json(root / 'install.json')
    binding_path = spec_path.with_suffix('.binding.json')
    reg = {'id': spec['id'], 'process': identity(), 'windowToken': spec['windowToken'],
           'label': Path(spec['cwd']).name or 'OpenCode', 'managed': True}
    atomic_json(binding_path, reg)
    env = dict(os.environ, OCDECK_HOME=str(root), OCDECK_BINDING=str(binding_path))
    # Arguments are read from JSON by PowerShell, never interpolated into script text.
    spec['executable'] = install['opencode']
    atomic_json(spec_path, spec)
    process = subprocess.Popen(['powershell.exe', '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                '-File', str(Path(install['source']) / 'scripts' / 'Run-OpenCode.ps1'),
                                '-LaunchFile', str(spec_path)], cwd=spec['cwd'], env=env)
    try:
        while process.poll() is None:
            try: request('POST', '/v1/register', reg)
            except Exception: pass  # OpenCode is independent of device availability.
            time.sleep(.5)
        return process.returncode
    finally:
        try: request('DELETE', '/v1/instances/' + reg['id'])
        except Exception: pass
        for p in (spec_path, binding_path, Path(str(binding_path) + '.claim')):
            p.unlink(missing_ok=True)


def install_plugin(mode='server', config_dir=None):
    root = home()
    install = read_json(root / 'install.json')
    config = Path(config_dir or os.environ.get('OPENCODE_CONFIG_DIR') or
                  Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'opencode')
    source = Path(install['source']) / 'plugins'
    entry = config / 'plugins' / 'ocdeck.js'
    marker = '// Managed by OpenCode Deck installer\n'
    entry.parent.mkdir(parents=True, exist_ok=True)
    if mode == 'server':
        if entry.exists() and not entry.read_text(encoding='utf-8').startswith(marker):
            raise RuntimeError('Refusing to replace an unrelated ocdeck.js')
        entry.write_text(marker + 'export { DeckBridge } from ' + json.dumps((source / 'server.mjs').as_uri()) + ';\n', encoding='utf-8')
    else:
        # JSONC can contain comments; do not silently destroy a user's configuration.
        if (config / 'tui.jsonc').exists():
            raise RuntimeError('tui.jsonc exists: follow docs to merge the TUI plugin entry manually')
        tui = config / 'tui.json'
        try: value = json.loads(tui.read_text(encoding='utf-8-sig')) if tui.exists() else {}
        except ValueError:
            raise RuntimeError('tui.json contains JSONC: merge the plugin entry manually')
        uri = (source / 'tui.mjs').as_uri()
        plugins = value.setdefault('plugin', [])
        if uri not in plugins: plugins.append(uri)
        if tui.exists(): shutil.copy2(tui, tui.with_suffix('.json.ocdeck-backup'))
        atomic_json(tui, value)
        if entry.exists() and entry.read_text(encoding='utf-8').startswith(marker): entry.unlink()
    install['pluginMode'], install['configDir'] = mode, str(config)
    atomic_json(root / 'install.json', install)
    print(f'Installed {mode} adapter globally in {config}. Restart OpenCode instances.')
