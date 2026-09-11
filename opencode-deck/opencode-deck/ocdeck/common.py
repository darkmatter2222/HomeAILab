import json
import os
from pathlib import Path
import tempfile
import urllib.request


def home():
    return Path(os.environ.get("OCDECK_HOME", Path.home() / ".opencode-deck"))


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def request(method, path, data=None, root=None, timeout=2):
    root = Path(root or home())
    discovery = read_json(root / "discovery.json")
    if not discovery:
        raise ConnectionError("Broker is not running; start its scheduled task.")
    # Discovery cannot redirect a privileged local client to a remote URL.
    port = int(discovery["port"])
    if not 1 <= port <= 65535:
        raise ValueError("Invalid broker port")
    token = (root / "token").read_text(encoding="ascii").strip()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
        data=json.dumps(data).encode() if data is not None else None,
        method=method, headers={"Authorization": "Bearer " + token,
                               "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def identity(pid=None):
    import psutil
    p = psutil.Process(pid or os.getpid())
    return {"pid": p.pid, "created": p.create_time()}


def alive(process):
    import psutil
    try:
        p = psutil.Process(int(process["pid"]))
        return abs(p.create_time() - float(process["created"])) < 0.01 and p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.AccessDenied:
        return None
    except (psutil.NoSuchProcess, KeyError, ValueError, TypeError):
        return False
