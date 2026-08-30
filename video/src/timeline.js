// ═══════════════════════════════════════════════════════════════════════
// THE MODEL QUESTION — 10-minute master timeline (600 s).
//
// ONE continuous spatial canvas: each chapter is a fixed vantage in a shared
// dark world (cam: z zoom, x/y pan, r roll, pitch). The camera dollies
// between them — the world never cuts. `cues` are the spoken narration,
// written as short cinematic transcript lines (max ~2 lines, 20 words or
// fewer). Key terms wrapped in [[...]] render green. Within a chapter the
// first ~1.2 s is camera flight-in, so cue `at` times start near 1.2.
// ═══════════════════════════════════════════════════════════════════════

export const SCENES = [
  {
    id: "hook", name: "THE HOOK", from: 0, to: 30,
    cam: { z: 0.85, x: 0, y: 0, roll: 0, pitch: 0 },
    cues: [
      { at: 1.2, text: "People ask me all the time" },
      { at: 3.2, text: "what hardware to run AI locally." },
      { at: 5.6, text: "I think that's [[the wrong question]]." },
      { at: 9.6, text: "The first question should be:" },
      { at: 12.2, text: "what kind of AI are you [[actually trying to run]]?" },
      { at: 17.2, text: "Because [[that]] determines the hardware." },
      { at: 21.6, text: "And if you already own the hardware," },
      { at: 24.2, text: "the same question works [[in reverse]]." },
    ],
  },
  {
    id: "workloads", name: "ONE WORKLOAD?", from: 30, to: 95,
    cam: { z: 1.5, x: -60, y: 20, roll: -1.5, pitch: 6 },
    cues: [
      { at: 31.2, text: "Local AI isn't one workload." },
      { at: 34.5, text: "Some models are small, fast, and easy to run." },
      { at: 39.5, text: "Some are [[much larger]]." },
      { at: 42.5, text: "And suddenly [[memory]] becomes a hard constraint." },
      { at: 46.5, text: "Can it run?" },
      { at: 49, text: "How fast can it run?" },
      { at: 51.5, text: "Those are [[completely different]] questions." },
    ],
  },
  {
    id: "moe", name: "MIXTURE OF EXPERTS", from: 95, to: 140,
    cam: { z: 2.1, x: 30, y: -40, roll: 1.8, pitch: 8 },
    cues: [
      { at: 96.5, text: "Then there are [[Mixture-of-Experts]] models." },
      { at: 100.5, text: "Data comes in. The router branches." },
      { at: 104.5, text: "Selected experts activate. Others stay dark." },
      { at: 109.5, text: "They can be enormous in memory…" },
      { at: 114, text: "…while only activating [[part]] of the model at a time." },
      { at: 120, text: "And now compute and memory stop scaling [[together]]." },
    ],
  },
  {
    id: "context", name: "CONTEXT", from: 140, to: 175,
    cam: { z: 1.6, x: -40, y: 30, roll: -1.2, pitch: 5 },
    cues: [
      { at: 141.5, text: "And even model size isn't the whole problem." },
      { at: 145.5, text: "Give it an [[entire codebase]]…" },
      { at: 149, text: "Let an agent work for [[hours]]…" },
      { at: 153.5, text: "And context becomes part of your [[hardware requirement]]." },
      { at: 159, text: "Now we're ready for the hardware." },
    ],
  },
  {
    id: "h3090", name: "RTX 3090", from: 175, to: 225,
    cam: { z: 1.8, x: -160, y: -20, roll: -2, pitch: 6 },
    cues: [
      { at: 177, text: "So let's start here." },
      { at: 181, text: "Older hardware. Relatively inexpensive." },
      { at: 184.5, text: "And somehow still [[extremely relevant]]." },
      { at: 191, text: "The interesting question isn't whether something newer is faster." },
      { at: 196.5, text: "It's how far you can get [[before you need]] something newer." },
    ],
  },
  {
    id: "h5090", name: "RTX 5090", from: 225, to: 275,
    cam: { z: 1.8, x: 160, y: -20, roll: 2, pitch: 6 },
    cues: [
      { at: 227, text: "The 5090 attacks a [[very different]] problem." },
      { at: 231.5, text: "When the workload fits," },
      { at: 234, text: "raw compute becomes [[incredibly valuable]]." },
      { at: 241, text: "But there's still [[a wall]]." },
      { at: 246, text: "All that compute doesn't help" },
      { at: 248.5, text: "if the workload can't fit where you need it." },
    ],
  },
  {
    id: "spark", name: "DGX SPARK", from: 275, to: 325,
    cam: { z: 1.7, x: 0, y: 10, roll: 1.4, pitch: 10 },
    cues: [
      { at: 277, text: "And that's why something like the [[DGX Spark]] exists." },
      { at: 283, text: "It solves a [[different]] problem." },
      { at: 287.5, text: "It's not interesting because it makes small models faster." },
      { at: 294, text: "It changes [[which models]] are available to you at all." },
      { at: 301, text: "And that's a different trade." },
      { at: 305.5, text: "You've now met the [[three characters]]." },
    ],
  },
  {
    id: "pullback", name: "THE GREAT PULLBACK", from: 325, to: 370,
    cam: { z: 1.45, x: 0, y: -90, roll: 0, pitch: 12 },
    cues: [
      { at: 327, text: "This is the decision" },
      { at: 329, text: "I think people should actually make." },
      { at: 334, text: "Start with [[the workload]]." },
      { at: 340, text: "The hardware connects where there's a [[good match]]." },
    ],
  },
  {
    id: "framework", name: "THE FRAMEWORK", from: 370, to: 415,
    cam: { z: 1.7, x: 0, y: -60, roll: 0.8, pitch: 9 },
    cues: [
      { at: 371.5, text: "If you care about [[responsiveness]]…" },
      { at: 376, text: "compute becomes prominent." },
      { at: 381, text: "As model size grows, so does [[memory]]." },
      { at: 386.5, text: "Eventually capacity decides [[whether it runs at all]]." },
      { at: 392.5, text: "For coding and long agents, context changes the equation." },
      { at: 398.5, text: "When many things share the system," },
      { at: 401, text: "throughput becomes [[another dimension]]." },
    ],
  },
  {
    id: "reverse", name: "REVERSE IT", from: 415, to: 450,
    cam: { z: 1.55, x: 0, y: 40, roll: -1.6, pitch: 6 },
    cues: [
      { at: 416.5, text: "But maybe you're [[not buying]] anything." },
      { at: 421, text: "Then the useful question becomes" },
      { at: 424.5, text: "[[my practical model envelope]]:" },
      { at: 427.5, text: "what can I [[actually]] run?" },
    ],
  },
  {
    id: "realworld", name: "REAL WORLD", from: 450, to: 510,
    cam: { z: 1.5, x: 70, y: 30, roll: 1.2, pitch: 5 },
    cues: [
      { at: 451.5, text: "Because this is where benchmarks stop being enough." },
      { at: 457, text: "I don't buy this hardware for benchmark prompts." },
      { at: 461, text: "I buy it to [[do work]]." },
      { at: 467, text: "How long do I [[wait]]?" },
      { at: 473, text: "Can I keep the context I [[need]]?" },
      { at: 479, text: "Can I run the model I [[actually want]]?" },
      { at: 485, text: "And what happens when another agent shows up?" },
    ],
  },
  {
    id: "synthesis", name: "THE SYNTHESIS", from: 510, to: 550,
    cam: { z: 1.15, x: 0, y: 0, roll: 0, pitch: 4 },
    cues: [
      { at: 512, text: "Once you see the whole system," },
      { at: 515, text: "the answer becomes clearer." },
      { at: 519, text: "There is [[no]] best GPU." },
      { at: 524.5, text: "There is a best [[fit]]." },
      { at: 529, text: "If your models fit on consumer hardware," },
      { at: 531.5, text: "compute can dominate the decision." },
      { at: 536, text: "Older hardware can still make [[extraordinary]] sense." },
      { at: 541, text: "If workloads demand more memory, capacity decides." },
      { at: 546, text: "[[The model]] decides." },
    ],
  },
  {
    id: "owners", name: "EXISTING OWNERS", from: 550, to: 575,
    cam: { z: 1.45, x: 0, y: -30, roll: -1, pitch: 7 },
    cues: [
      { at: 551.5, text: "Already own the hardware?" },
      { at: 555.5, text: "Don't upgrade because of a [[faster benchmark]]." },
      { at: 560.5, text: "Find the [[practical limit]] of what you own." },
      { at: 566, text: "Upgrade when your workload [[crosses that line]]." },
      { at: 569.5, text: "Not before." },
    ],
  },
  {
    id: "series", name: "THE SERIES", from: 575, to: 590,
    cam: { z: 1.35, x: 0, y: 10, roll: 0, pitch: 4 },
    cues: [
      { at: 576.5, text: "Different [[models]]." },
      { at: 579, text: "Different [[engines]]." },
      { at: 581.5, text: "Different [[context]] sizes." },
      { at: 584, text: "Real [[agentic]] workloads." },
      { at: 587, text: "Run it. Measure it. [[Find the limit]]." },
    ],
  },
  {
    id: "openloop", name: "OPEN LOOP", from: 590, to: 600,
    cam: { z: 1.9, x: -160, y: -10, roll: -2, pitch: 6 },
    cues: [
      { at: 591, text: "And there's one machine" },
      { at: 593.5, text: "that keeps [[surprising]] me." },
      { at: 596, text: "How far can a [[3090]] go?" },
    ],
  },
];

export const TOTAL = 600; // 10:00

export function sceneAt(t) {
  for (let i = SCENES.length - 1; i >= 0; i--) {
    if (t >= SCENES[i].from) return SCENES[i];
  }
  return SCENES[0];
}

export function sceneIndexAt(t) {
  for (let i = SCENES.length - 1; i >= 0; i--) {
    if (t >= SCENES[i].from) return i;
  }
  return 0;
}

export function fmtClock(t) {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
