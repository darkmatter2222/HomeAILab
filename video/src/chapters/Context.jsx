// 2:20–2:55 — CONTEXT CHANGES EVERYTHING
// One simple model, comfortable in a GPU. A small context stream is fine.
// Then files, code, documents, conversation history — the stream grows,
// a KV cache fills alongside the model. Memory approaches full.
import { motion } from "framer-motion";
import { SceneShell, Statement, MemoryContainer, ContextRibbon, ModelBlock, EASE } from "../prims.jsx";
import { after, clamp01 } from "../clock.js";
import { SCENES } from "../timeline.js";

const SCENE = SCENES[3];

const SOURCES = ["codebase", "agent · hours", "documents", "history"];

export default function Context({ t }) {
  const lt = t - SCENE.from;
  const comfy = after(lt, 1.5, 1.0);      // simple model, comfortable
  const smallCtx = after(lt, 5, 0.8);      // small context stream — fine
  const grow = clamp01((lt - 9) / 22);     // 9..31s: the stream keeps growing
  const ready = after(lt, 20, 0.9);        // "now we're ready for the hardware"

  // context fill of the memory vessel: small → near full
  const ctxFill = smallCtx * 0.08 + grow * 0.42;
  const modelFill = 0.34;
  const total = Math.min(0.98, modelFill + ctxFill);

  return (
    <SceneShell>
      <div style={{ display: "flex", alignItems: "center", gap: 70, opacity: comfy }}>
        {/* the simple model */}
        <ModelBlock size={1.1} active={false} label="MODEL · FITS COMFORTABLY" opacity={comfy} layers={7} />

        <div style={{ width: 120, height: 220, display: "grid", placeItems: "center" }} />

        {/* the memory vessel filling with context */}
        <MemoryContainer
          fill={total}
          model={modelFill}
          context={ctxFill}
          label="MEMORY"
          tension={grow > 0.8}
          caption={grow > 0.8 ? "approaching full" : ""}
        />

        {/* the context stream sources, arriving one by one */}
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {SOURCES.map((s, i) => {
            const on = grow > i / SOURCES.length;
            return (
              <motion.div
                key={s}
                initial={{ opacity: 0, x: 30 }}
                animate={{ opacity: on ? 1 : 0.12, x: 0 }}
                transition={{ duration: 0.8, ease: EASE }}
                style={{
                  fontFamily: "var(--mono)", fontSize: 13, letterSpacing: "0.14em",
                  color: on ? "var(--ink)" : "var(--ink-faint)",
                  borderLeft: `2px solid ${on ? "var(--green)" : "rgba(255,255,255,0.15)"}`,
                  paddingLeft: 14, padding: "4px 0",
                  width: 180,
                }}
              >
                + {s}
              </motion.div>
            );
          })}
          <div style={{ marginTop: 10 }}>
            <ContextRibbon fill={0.1 + grow * 0.9} label="CONTEXT" caption={Math.round((0.1 + grow * 0.9) * 100) + "% of window"} />
          </div>
        </div>
      </div>

      <div style={{ position: "absolute", bottom: 200, opacity: ready }}>
        <Statement text="Context is now a hardware requirement." op={ready} size="clamp(24px, 2.5vw, 38px)" mark={[null, "hardware", null]} />
      </div>
    </SceneShell>
  );
}
