#!/usr/bin/env python3
"""One-off: add the image-dedicated Spark vision backend to router.py.

Run on Databrick:  python3 patch_router_imageded.py
Idempotent-ish: asserts each anchor is present before replacing; run once.
"""
import sys

PATH = "/home/darkmatter2222/qwen38-router/router.py"
src = open(PATH).read()

# 1. VISION_BACKEND -> VISION_BACKENDS (comma-separated list)
old = '''# Vision routing: when an image request (base64/URL image block in the payload)
# arrives, force it onto the named vision backend (default the DGX Spark) so it
# never lands on a text-only 5090/3090 slot. Empty = no vision pinning.
VISION_BACKEND = os.getenv("VISION_BACKEND", "dgxsparx").strip()'''
new = '''# Vision routing: when an image request (base64/URL image block in the payload)
# arrives, force it onto the named vision backend(s) (default the DGX Spark) so
# it never lands on a text-only 5090/3090 slot. Comma-separated list = the first
# healthy+free vision backend in the list is used (scale-out). Empty = off.
VISION_BACKENDS = [x.strip() for x in os.getenv("VISION_BACKEND", "dgxsparx").split(",") if x.strip()]'''
assert old in src, "vision backend block not found"
src = src.replace(old, new)

# 2. add the imageded backend right after the dgxsparx block
old = '''                    int(os.getenv("SPARK_CAPACITY", "3")),  # Flash-Next qwen4exp llama.cpp: --parallel 3 (full 262K each)
                ),
            ] if os.getenv("SPARK_BACKEND_URL", "http://192.168.86.39:8006").strip() else []),
        ]'''
new = '''                    int(os.getenv("SPARK_CAPACITY", "3")),  # Flash-Next qwen4exp llama.cpp: --parallel 3 (full 262K each)
                ),
            ] if os.getenv("SPARK_BACKEND_URL", "http://192.168.86.39:8006").strip() else []),
            # DGX Spark IMAGE-DEDICATED instance (stack qwen38-flashnext-imageded,
            # host :8016). A second ds4 + Qwen-vision copy so vision capacity = 2x;
            # the router's vision pin picks the first free one (dgxsparx then
            # imageded). Enabled only when SPARK_IMAGEDED_URL is set.
            *([
                Backend(
                    "dgxsparx-imageded",
                    os.getenv("SPARK_IMAGEDED_URL", "http://192.168.86.39:8016").rstrip("/"),
                    os.getenv("SPARK_KIND", "llama").lower(),
                    4,
                    int(os.getenv("SPARK_IMAGEDED_CAP", "3")),
                ),
            ] if os.getenv("SPARK_IMAGEDED_URL", "http://192.168.86.39:8016").strip() else []),
        ]'''
assert old in src, "backend block not found"
src = src.replace(old, new)

# 3. select(): vision pin now iterates the list, picks first usable
old = '''            if vision and force:
                fb = self.by_name.get(force)
                if fb is not None and fb.healthy and self._can_use(fb, sid):
                    fb.inflight += 1
                    fb.req_active += 1
                    if sid:
                        self.sessions[sid] = {"backend": fb.name,
                                              "expires_at": time.monotonic() + SESSION_TTL_SECONDS}
                        self.inflight_by_session[sid] += 1
                    LOG.info("route session=%s backend=%s reason=vision-pinned avail=%s",
                             _hid(sid or "anon"), fb.name, fb.available)
                    return fb
                # The pin did NOT hold -- log WHY (this is the case that caused
                # image requests to spill onto text-only backends).
                reason = ("vision-backend-missing" if fb is None
                          else "vision-backend-unhealthy:" + (fb.error or "?") if not fb.healthy
                          else "vision-backend-full")
                LOG.warning("vision pin NOT honored: session=%s vision=%s reason=%s; "
                            "falling through to sticky/priority",
                            _hid(sid or "anon"), force, reason)'''
new = '''            if vision and force:
                _names = force if isinstance(force, list) else [force]
                picked = next((self.by_name.get(n) for n in _names
                               if self.by_name.get(n) is not None
                               and self.by_name.get(n).healthy
                               and self._can_use(self.by_name.get(n), sid)), None)
                if picked is not None:
                    fb = picked
                    fb.inflight += 1
                    fb.req_active += 1
                    if sid:
                        self.sessions[sid] = {"backend": fb.name,
                                              "expires_at": time.monotonic() + SESSION_TTL_SECONDS}
                        self.inflight_by_session[sid] += 1
                    LOG.info("route session=%s backend=%s reason=vision-pinned avail=%s",
                             _hid(sid or "anon"), fb.name, fb.available)
                    return fb
                # The pin did NOT hold -- log WHY per candidate.
                parts = []
                for n in _names:
                    fb = self.by_name.get(n)
                    if fb is None:
                        parts.append(n + ":missing")
                    elif not fb.healthy:
                        parts.append(n + ":unhealthy:" + (fb.error or "?"))
                    else:
                        parts.append(n + ":full")
                LOG.warning("vision pin NOT honored: session=%s vision=%s reason=%s; "
                            "falling through to sticky/priority",
                            _hid(sid or "anon"), force, " ".join(parts))'''
assert old in src, "vision pin block not found"
src = src.replace(old, new)

# 4. call site: pass the list
old = '''    backend = await state.select(sid, force=VISION_BACKEND if is_vision else None,
                                 vision=is_vision)'''
new = '''    backend = await state.select(sid, force=VISION_BACKENDS if is_vision else None,
                                 vision=is_vision)'''
assert old in src, "call site not found"
src = src.replace(old, new)

# 5. startup log arg
old = '''             os.getenv("LOG_LEVEL", "INFO"), VISION_BACKEND or "(none)",'''
new = '''             os.getenv("LOG_LEVEL", "INFO"), ",".join(VISION_BACKENDS) or "(none)",'''
assert old in src, "log arg not found"
src = src.replace(old, new)

# 6. the is_vision gate references VISION_BACKEND too
old = '''    is_vision = bool(VISION_BACKEND) and body_has_image(body)'''
new = '''    is_vision = bool(VISION_BACKENDS) and body_has_image(body)'''
assert old in src, "is_vision gate not found"
src = src.replace(old, new)

open(PATH, "w").write(src)
print("OK: router.py patched for image-dedicated backend")
