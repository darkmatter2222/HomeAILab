# Global installation and other environments

The supplied installer is global **for one native Windows user and OpenCode configuration home**. It works across project directories without adding project files. A config-home override needs its own plugin installation entry. A shell alias or a machine-level PATH entry may outrank the launcher; check command resolution explicitly.

The implemented and tested broker protocol uses native local process IDs plus process creation times. That identity has meaning only on the broker's operating system. The device and focus worker must run on the Windows PC with the Mini and the user's desktop. Loopback in WSL, a container, or a remote host does not automatically mean the same loopback endpoint.

## Supported design boundaries

| Launch type | This bundle |
|---|---|
| Managed native Windows OpenCode, any project directory | Intended primary path; dedicated window identity |
| Native OpenCode launched without wrapper | Global state plugin can register; exact terminal focus is not guaranteed |
| Multiple tabs/panes in a shared terminal window | Exact tab/pane selection not implemented |
| Multiple clients attached to one OpenCode server | Not supported by default process-wide adapter |
| WSL / Docker / SSH runtime | Cross-environment host relay not implemented |
| macOS / Linux desktop | Windows installer/focus not implemented |

This boundary is deliberate and visible: a global configuration is not a cross-machine deployment mechanism. The original request's “any environment” is implemented as any native Windows project directory. If it means WSL, containers, or remote machines, additional work is required.

## Concrete extension plan for a local implementation agent

1. Keep the hardware broker on Windows. Create a managed Windows launcher that owns the exact local terminal identity and a host process lifetime.
2. Create a separate runtime-binding credential per launched remote environment. Do not copy the unrestricted broker token into containers or remote hosts.
3. Relay a narrow authenticated snapshot stream through a local host-side process or SSH tunnel. The relay translates runtime UUID, launch UUID, epoch, sequence and pending state into the Windows registration. Guest PIDs are metadata, never Windows focus/process-liveness identities.
4. Have the Windows launcher own focus and host lifetime. Remote disconnect should show unknown during a bounded grace period, then remove the instance when authoritative host/runtime closure is known. Network loss alone must not masquerade as confirmed process exit.
5. Install the plugin in each runtime's own global OpenCode config home. Add explicit environment transport selection; do not assume the Windows discovery file or 127.0.0.1 endpoint is reachable.
6. Test tunnel loss/reconnect, broker restart, guest process exit, host terminal closure, token revocation, multiple guests with identical PIDs, and exact local-window focus.

Do not expose the present broker on `0.0.0.0`. Its process validation, credential storage and HTTP assumptions are designed for local use, not an Internet-facing service.
