import { motion } from "framer-motion";
import { SceneShell, SceneTitle, ArchitectureDiagram } from "../ui.jsx";

export default function Topology({ num }) {
  return (
    <SceneShell>
      <SceneTitle num={num} kicker="FLEET TOPOLOGY" title="Client → router → three GPUs" />
      <div style={{ flex: 1, minHeight: 0, width: "100%" }}>
        <ArchitectureDiagram animate={true} />
      </div>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 3 }}
        style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-faint)", marginTop: 12, display: "flex", gap: 24, flexWrap: "wrap" }}
      >
        <span>SSH key-based · StrictHostKeyChecking off</span>
        <span>Portainer CE 2.39 · every stack is a deploy unit</span>
        <span>all engines on <b style={{ color: "var(--green-bright)" }}>8006</b> · same /v1 contract</span>
      </motion.div>
    </SceneShell>
  );
}
