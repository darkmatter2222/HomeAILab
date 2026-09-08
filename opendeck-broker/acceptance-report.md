# opendeck-broker acceptance matrix

Generated: 2026-09-07T22:35:49

Headless rows run with an in-memory device + fake observer + injected
window/foreground fakes. Physical rows require the real Mini and are
listed separately so a simulated pass is never mistaken for hardware
evidence (research section 14).

## Headless rows

| ID | Row | Result |
|---|---|---|
| B-01 | Cold reboot, no OpenCode -> six black | PASS |
| B-02 | Launch one TUI at home screen -> exactly one amber key | PASS |
| B-03 | Launch six simultaneously -> six unique stable assignments | PASS |
| B-04 | Launch two in the same directory -> separate buttons + focus targets | PASS |
| B-05 | Generate a long response -> green, amber on completion | PASS |
| B-06 | Run a long tool without tokens -> stays green | PASS |
| B-07 | Automatic model retry -> green | PASS |
| B-08 | Request permission -> red until answered | PASS |
| B-09 | Request structured question -> red until replied | PASS |
| B-10 | Two pending requests -> red until both resolve | PASS |
| B-11 | Child completes while parent runs -> parent stays green | PASS |
| B-12 | Child requires user input -> owning TUI red, no extra slot | PASS |
| B-13 | Final answer asks ordinary prose -> amber (no structured request) | PASS |
| B-14 | Click each of six keys (mixed states) -> focus, no state mutation | PASS |
| B-15 | Click a black key -> no window/process/command/state change | PASS |
| B-16 | Single press -> single focus (no double execution / cycling) | PASS |
| B-17 | Switch conversation inside TUI -> same slot, same binding | PASS |
| B-18 | Close OpenCode while shell stays open -> slot clears | PASS |
| B-19 | Kill OpenCode or its terminal -> slot clears via liveness | PASS |
| B-20 | Reuse OS PID / reuse slot -> old press does not hit new occupant | PASS |
| B-21 | Restart broker while INPUT pending -> re-register restores red | PASS |
| B-22 | Device reconnect -> complete six-slot frame restored | PASS |
| B-23 | Seventh instance -> no live assignment stolen, overflow explicit | PASS |
| B-24 | Bridge unavailable -> UNKNOWN (amber ?), not an indefinite lie | PASS |

**Headless: 24/24 passed**

## Physical rows (need the Mini)

| ID | Row | Evidence tool |
|---|---|---|
| A-own | Mini ownership + 6 black + 6 numbered images + 6 key events (no OpenCode) | tools/probe_device.py |
| A-focus | Real Mini press foregrounds the correct terminal while another app is active | tools/probe_focus.py |
| A-boot | Cold reboot with no OpenCode: six black after init, no old sessions resurrected | reboot host, observe Mini |
| A-order | Broker started before and after Elgato: selected ownership works in both orders | start/stop ordering with Elgato app |
| A-replug | USB disconnect/reconnect restores the complete current frame | replug the Mini |
| A-power | Lock/unlock/sleep/resume: no stale green; correct state after resume | sleep/wake the host |
| A-min | Focus a minimized instance from another app: restored + foreground verified | minimize target, press from another app |

_Physical rows are not claimed as passed by the headless run._
