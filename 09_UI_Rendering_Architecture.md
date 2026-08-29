# Office UI Rendering Architecture — Migration Decision

*Scope: UI visualization rendering architecture only. Does not modify `orchestrator.py`, the event contract, the Mentor schema, or any trading/backend logic. Builds on `08_Office_UI_Build_Plan.md` (the "agents are workers, work is what moves" concept) and the corrected event schema established after reviewing the real TRD/Architecture/Phase Progress docs — this migration changes how that concept is rendered, not what it depicts.*

> **Revision note (second pass):** this document has now been revised twice. Pass 1 added §3 (reference material analysis) after reference screenshots were supplied. Pass 2 (current) corrects six issues identified in review of pass 1: (1) claims about the references' underlying rendering technology are now explicitly framed as visual inference, not verified fact; (2) tilemap rendering is now a conditional recommendation subject to asset inspection, not an unconditional requirement — the actual requirement is a coherent, grid-aligned world-space with consistent scale/layering/depth; (3) asset reuse (inventory/integrate) is now explicitly separated from asset generation (which the implementation agent must not do unilaterally); (4) Y-sort remains a firm requirement for dynamic entities; (5) the camera is fixed to a static full-office framing for this milestone, with no pan/zoom/follow/cinematic behavior in scope; (6) the traveling Work Artifact is explicitly preserved as an intentional AlphaSwarm-specific mechanic regardless of how the references handle handoffs. §1–2 are unchanged in substance across both passes.

---

## 1. Critique of the current rendering approach

The current implementation is a composited scene: one background image, several absolutely-positioned character/icon `<div>`s, CSS `transform`/`transition` for movement, and status/speech bubbles as fade-in `<div>`s. This was the correct MVP choice for the original build order (Step 1 static scene → Step 2 single hardcoded trigger → Step 3 mock playback) — a handful of fixed nodes and a linear sequence of point-to-point moves doesn't need more than that.

It's the wrong foundation for what's being asked now:

- **No shared coordinate/camera system.** Every element's position is independently set in CSS px. There's no notion of "world space" vs. "screen space," so camera pan/zoom/follow, parallax, or reframing the view isn't something the current structure supports — it would have to be bolted on as more per-element math, not enabled by the architecture.
- **Movement is point-to-point, not path- or state-driven.** CSS transitions interpolate a start and end position over a duration; they don't support per-frame control, path-following around obstacles, or coordinating multiple simultaneous motions (idle sway + walk + arrival flourish) as one state machine. Every new motion nuance becomes another hand-tuned transition.
- **No true entity abstraction.** "Where is this agent, what is it doing, what does it look like right now" is split across CSS classes and JS event-handler side effects, referenced by DOM id — not centralized in a model object. Adding new agent-level behavior (idle look-around, hover reaction, walk-and-sit) means touching handler logic and CSS in parallel rather than extending one entity class.
- **Compositing cost scales badly.** Each glow/status effect is a box-shadow or filter on a DOM node; each simultaneous artifact or ambient effect is another absolutely-positioned node with its own transition. This works for one artifact and ~8 static nodes. It does not scale cleanly to "ambient life," multiple artifacts in flight, or ongoing idle animation across all agents at once.
- **Weak interaction/depth model.** Hover/click hit-testing on irregular sprites, z-ordering (agent in front of vs. behind a desk), and layered visual depth are all manual z-index and CSS-shape workarounds rather than native properties of the render model.

None of this was a mistake at the milestone it was built for. It's the wrong tool for "a persistent office environment in which agents are entities that inhabit the environment" — that phrase describes a small simulation with a render loop and an entity system, which CSS transitions don't provide.

---

## 2. Comparison of architectural options

### A. HTML/CSS layered rendering (current, extended)
- **Pros:** Zero new dependency, fully leverages existing work, real DOM elements give free accessibility and easy click/hover handlers, easy to inspect in devtools, declarative and often visually smooth for a small number of elements.
- **Cons:** No camera/viewport model, path-following and curved motion are awkward, no unified per-frame update loop (can't easily pause/scrub/rewind precisely), sprite-sheet walk-cycle animation is not a good fit, z-ordering/depth sorting gets fiddly as entity count grows, ambient/particle-style polish is expensive to fake with more DOM nodes.
- **Best when:** the scene stays simple and mostly static, event/entity count stays low, and DOM-native accessibility matters more than game-like polish. This describes the milestone already shipped, not the one being asked for now.

### B. Canvas 2D (raw, own render loop)
- **Pros:** Full per-frame control, a real coordinate system with a camera transform, natural fit for sprite-sheet animation and depth sorting, renders many entities without DOM overhead, cleanly separates "world state" from "how it's drawn" (`update()` / `draw()`).
- **Cons:** You own everything — hit-testing, hover/click, tweening, asset/sprite management, and depth sorting are all hand-rolled; no devtools element inspector for canvas contents; accessibility requires a parallel ARIA/DOM layer if needed at all.
- **Best when:** you want real per-frame control and are willing to build (or hand-roll small helpers for) the entity system, hit-testing, and tweening yourself, without pulling in a framework.

### C. Lightweight 2D/game rendering framework (e.g. PixiJS, or a comparably scoped 2D library)
- **Pros:** Delivers Canvas's benefits (camera, per-frame control, depth sorting) plus a built-in scene graph, texture/sprite-sheet loading, tweening helpers, and pointer-interaction support on sprites — removing most of Canvas's "own everything" burden. WebGL-backed options give GPU-accelerated compositing and filters (glow, blur) largely for free, and scale well if the scene grows (more agents, more simultaneous artifacts, ambient effects) without hand-tuned workarounds.
- **Cons:** A new dependency and a new API/mental model for whoever maintains this code; a moderate bundle-size increase; still requires building your own domain-specific entity/event logic on top (a framework gives you the renderer, not "agent walks from A to B on a correction event" — that logic is still yours to write).
- **Best when:** you actually want the persistent-world behavior described in this request — ambient/idle life, camera movement, multiple simultaneous world events, depth-sorted entities — and accept the added dependency and learning curve in exchange for not hand-building a renderer.

### D. Hybrid — world canvas (Canvas or lightweight framework) + HTML/CSS UI chrome
- **Pros:** This is the standard, proven pattern for exactly this product shape: a small persistent-world visualization embedded inside an otherwise normal web dashboard. The "world" (agents, desks, artifacts, movement, ambient state) gets a real coordinate system and render loop; the surrounding UI (header, event log, controls, cycle/status readouts) stays plain HTML/CSS — easy to build, natively accessible, easy for a teammate to extend without learning a new rendering API. You get the right tool for each job instead of forcing one paradigm to do both.
- **Cons:** Slightly more architectural surface area (two rendering systems, need a clean boundary between them); if any DOM element needs to track a canvas-world position (e.g. a tooltip following an agent), you need a small world-to-screen coordinate projection utility; the event stream must drive both layers consistently from one source, not two independently-drifting consumers.
- **Best when:** — the general case here. You want a real interactive world for the visualization core, but the parts that are already working well and are naturally suited to HTML (header, log, controls, anything with selectable text) don't need to be rebuilt just because the world did.

---

## 3. Reference material analysis

> **Epistemic note (correction applied):** the two supplied screenshots are visual evidence only — static images of running products. Nothing about them confirms the underlying rendering technology (a genuine tile/game engine, a hand-built tilemap on Canvas/WebGL, or even an extremely disciplined DOM/CSS composite could all produce these results). What follows describes what the *visual output* is **consistent with** and the *techniques that would produce that visual result*, not a verified claim about how either product is actually implemented. Everywhere below, read "tile-based," "tile atlas," etc. as "visually consistent with a tile/grid-based approach" — this is an inference to guide our own implementation choices, not a fact established about the reference products.

Two reference screenshots were supplied: a top-down pixel-art "agent office" with room-labeled zones (Meeting Room, Workspace, Command Center) and a live terminal/status sidebar; and a second top-down pixel-art office simulation with cubicle rows, a meeting table, a kitchen area, floating status labels over characters, and an agent-roster/command panel.

### 3.1 Visual construction
The floor, walls, furniture, doors, windows, and lamps in both references are visually consistent with construction from **one shared tile atlas at one consistent pixel-per-unit scale**, with one consistent light source and palette applied throughout. Floor tiles appear to repeat seamlessly; walls appear to join floor tiles at matching pixel boundaries; furniture appears grid-aligned rather than floating over the scene as an independently-scaled image. This is a visual read, not a confirmed implementation detail.

### 3.2 What makes it read as one coherent world
The actual mechanism, as far as can be inferred, is **stylistic and dimensional consistency**, not any single visual trick: character sprites are drawn at the same apparent pixel scale and palette family as the environment (same line weight, same lighting logic, same proportions) — nothing looks like a separately-styled asset dropped on top of a background. A mismatched art style between characters and environment would visibly break this, and neither reference shows that mismatch. **This is the most actionable, technology-agnostic finding here: coherence comes from one consistent scale/style/lighting applied uniformly, regardless of whether the underlying renderer is a literal tilemap, a Canvas composite, or something else.** Our own implementation should target this outcome directly rather than assuming a specific technique is what produces it.

### 3.3 Character/entity behavior
Characters are stationary-by-default, seated at desks, occasionally shown with a floating status label ("awaiting," "washing the mug," "reviewing," "documenting"). Where movement is implied, it appears grid-aligned — discrete tile-like positions, not arbitrary floating-point coordinates. This matches AlphaSwarm's existing design (agents mostly stay at desks; the artifact is what moves) closely — no correction needed to the underlying concept here.

### 3.4 Artifact/work movement and handoff
Neither reference shows a physical object visibly traveling between desks in the supplied stills. Handoff/state is instead communicated via **status-tag changes** (an agent's tag flips `idle`/`working`/etc.) mirrored in a side-panel roster. **This is confirmation of a different design choice these products made, not evidence AlphaSwarm's approach is wrong.** Per the explicit instruction accompanying this revision: the traveling Work Artifact is intentional and AlphaSwarm-specific — it visually proves *targeted* correction routing to a specific agent, which neither reference needs to demonstrate. It is preserved as-is regardless of what the references do.

### 3.5 Camera/viewport
Both stills show the entire office in one fixed frame — no visible pan, zoom, or follow behavior in the supplied images. This is consistent with a static "diorama" camera. Per the explicit scope decision for this milestone: AlphaSwarm's camera will be a **fixed full-office framing only** — no pan, zoom, follow, or cinematic behavior — independent of whether either reference product supports such behavior elsewhere (which cannot be confirmed from a still image regardless).

### 3.6 Layering/depth/z-order
The visual results in both references — an entity standing in front of a desk correctly occluding it — are **consistent with** Y-sort depth ordering (render order determined by each entity's vertical screen position). This is inferred from the visual effect, not confirmed as the reference's actual implementation. Regardless of how the references achieve it, correct front/behind occlusion driven by vertical position is a clear, well-understood, and easily verifiable technique in its own right, and is adopted here on its own merits — it doesn't require the reference attribution to be justified.

### 3.7 Does the recommended approach still hold?
Yes, with the requirement now framed correctly: the goal is a **coherent, grid-aligned world-space environment with consistent scale, layering, and depth** — not a mandate to build a literal tilemap. A Canvas/WebGL-backed lightweight rendering library (PixiJS or similar) remains well suited to achieving that goal, and can support either a genuine tilemap (if existing/new assets reasonably support one) or a well-structured, grid-aligned composited scene (if they don't) without changing the underlying framework decision. Tilemap rendering is downgraded from "the recommended implementation" to **"a recommended implementation technique, conditional on asset inspection"** — see §5 and §6.

### 3.8 Principles to adopt vs. assets/elements to NOT copy

**Adopt (principles, technology-agnostic where noted):**
- One consistent scale, palette, and lighting logic applied uniformly across floor/walls/furniture/characters — the actual coherence mechanism (§3.2), achievable via a tilemap or a disciplined grid-aligned composite, whichever the asset inventory supports
- Y-sort depth ordering for dynamic entities against static props — adopted on its own technical merits, not solely because the references appear to use it
- Floating status-label overlays anchored to entity screen position (AlphaSwarm's existing speech-bubble concept already does this — keep it)
- A status panel/roster that mirrors world state 1:1 — validates the hybrid HTML+canvas split already recommended in §4
- Distinct visually-zoned "rooms" as an optional narrative device — worth considering, not required

**Do NOT copy:**
- The specific tileset/asset packs from either reference — style inspiration only, not source material
- **Character names and likenesses.** One reference's roster (Michael, Jim, Pam, Kevin, Ryan, Stanley, Meredith) are recognizable *The Office* (NBC) characters; the other's names read as derived from an existing anime property. Neither should be replicated in any form — AlphaSwarm's agent identities should stay functionally named
- The exact room labels or specific UI chrome/button layout from either product — inspiration only, not a template to fill in
- **The assumption that a literal tilemap is required** — that would be copying an inferred implementation detail we cannot actually verify, rather than the visual principle it produces (see §3.7)

---

## 4. Recommended architecture and justification

**Recommendation unchanged: a hybrid architecture. A lightweight 2D rendering library (PixiJS, or a comparably scoped alternative) drives the world canvas; all surrounding UI chrome (header, event log, controls, technical/status readouts) stays exactly what it already is: HTML/CSS.**

The reference analysis in §3 refines the *requirement*, not the framework choice: the actual target is **a coherent world-space, grid-aligned environment with consistent scale, layering, and depth** — achieved via tilemap rendering where the asset inventory supports it, and via a disciplined grid-aligned composited alternative where it doesn't (see §5, §6). This is a meaningful softening from the prior version of this document, which treated tilemap rendering as an unconditional requirement inferred from the references; that inference was not something the screenshots actually established.

Why the hybrid call still holds:

- The request's own language — "agents are entities that inhabit the environment," "dynamic world events" — describes a small simulation with persistent entities and a render loop, not a sequence of CSS transitions between fixed points. Canvas-class rendering is the right primitive for that; pure DOM/CSS will fight this requirement at every step past what's already shipped.
- Raw Canvas (B) is workable but means hand-building sprite animation, depth sorting, hit-testing, and tweening from nothing. For a small team on a compressed build timeline, that's avoidable engineering cost with no corresponding benefit over using an existing lightweight library for exactly that plumbing.
- A lightweight 2D library is **not** a reversal of the original "no game engine" guidance from `08_Office_UI_Build_Plan.md`. That guidance was warning against Phaser-class full game engines (physics, collision systems, input managers) for a scene that, at the time, was a handful of fixed nodes and one traveling icon. PixiJS specifically is a rendering library, not a game engine — no physics, no collision, no built-in game-loop concepts beyond a ticker.
- Keeping UI chrome in HTML/CSS is the safe and correct call independent of the world-rendering decision, and §3.4's finding (both references pair a world view with a mirrored status-panel/roster) directly validates this split rather than suggesting the roster/log should be absorbed into the canvas.
- This satisfies "preserve the existing event contract and mock playback behavior" directly: the event stream (the corrected `events.jsonl` schema, including `owner`-based routing, the Strategist re-synthesis hop, and the REVISE/REJECT/WAIT/APPROVE distinctions) becomes the single input to a small in-memory **world-state store**. Both the canvas renderer and the HTML event-log panel read from that same store/stream — one source of truth, two presentation layers, no duplicated "what happened" logic and no risk of the two drifting apart.

---

## 5. Proposed scene/entity model

- **World mount:** a single rendering-library application instance mounted into a container sized to the "world" region of the existing page layout — a sibling of the header/log/controls, not a replacement for the page. Header, event log, and controls remain outside this container.
- **World-space foundation (revised — conditional, not unconditional):** the floor/walls/desks/checkpoint props must form a **coherent, grid-aligned world-space** with consistent scale, palette, and lighting. **Tilemap rendering is the recommended way to achieve this, subject to asset inspection** (see §6) — if the existing background/assets can reasonably be converted into or rebuilt as a tile atlas, do that. If they cannot be reasonably converted (e.g. the existing background is a single bespoke illustration not designed as tileable units), the correct response is a well-structured, grid-aligned composited scene that still delivers consistent scale/layering/depth — not a forced, artificial tilemap conversion that degrades visual quality to satisfy a technique for its own sake. Report which path was taken and why (see §6, §10 Step 0).
- **Layer stack (z-order, bottom to top):** `FloorLayer` → `WallLayer` (may combine with floor depending on approach) → `PropLayer` (static desks/checkpoint icons) → `EntityLayer` (agents and artifacts, **Y-sorted** — see below) → `EffectLayer` (glows, terminal-state flourishes, any future particles).
- **Depth ordering (firm requirement, unchanged):** entities in `EntityLayer` — agents and artifacts, i.e. anything that moves or changes position during a cycle — are sorted by screen Y-position every frame (Y-sort), not assigned a fixed z-index. This applies regardless of whether the floor/wall layer ends up as a true tilemap or a grid-aligned composite; it's a requirement on dynamic entities specifically, not on the whole scene.
- **Camera (firm scope limit for this milestone):** a single transform (position + scale) applied to a `WorldContainer` wrapping the layer stack, kept as an abstraction/seam for future use — but for this milestone the transform is **fixed to a static full-office framing**. No pan, zoom, follow, or cinematic camera behavior is in scope. This is a hard limit, not a default that can be quietly extended during implementation.
- **Entity base concept:** every persistent "thing in the world" (agent, artifact, checkpoint icon) is a small object with `id`, `kind` (`agent | artifact | checkpoint`), `position`, `targetPosition`/`path`, `state`, a reference to its display object, and an `update(dt)` method. Agents are created once and persist for the life of the session; artifacts are ephemeral — spawned on an agent's `finished` event, destroyed on arrival/absorption at the recipient.
- **Two decoupled state machines per interaction**, not one conflated state:
  - **Agent state:** `idle → working (started) → idle (finished)` and, separately, `correction_target → working (re-invoked) → idle`. An agent's own glow/pulse state reflects only whether *it* is actively processing — it does not track whether an artifact exists.
  - **Artifact state:** `spawned (at sender) → traveling → arrived (at recipient) → destroyed`. This keeps "is the agent busy" and "is a work item currently in transit" as separate, composable facts, matching the real event stream. **The traveling Work Artifact is preserved as a deliberate, intentional AlphaSwarm-specific visualization of targeted handoffs (per explicit instruction) — this holds regardless of what either reference does**, since neither reference needs to prove targeted routing the way AlphaSwarm's Mentor correction mechanism does.
- **Terminal-state visuals** (Strategist `NO_TRADE`, Mentor `REJECT`, Mentor `WAIT`, Risk Engine `FAIL`, execution `rejected`/`error`) render as short-lived, auto-fading world events (an icon + label floating above the relevant desk, in the same visual language as the existing speech-bubble concept) rather than a persistent change to the entity's base sprite.
- **Static desks/checkpoints** reuse the existing fixed-coordinate layout as-is, expressed as world-space grid positions. Optional: grouping desks into visually-zoned "rooms" — worth considering, not required for functional parity.

---

## 6. Asset strategy

> **Correction applied:** this section now draws a hard line between (a) inventorying and integrating *existing* assets, which the coding agent may do, and (b) *generating or regenerating* artwork, which the coding agent must **not** do unilaterally. Asset generation is a separate, controlled task with its own review step — not a fallback the implementation agent reaches for on its own when it hits a mismatch.

- **Step one is always inventory, not creation.** Before any rendering code changes, catalog every existing visual asset (background, agent avatars, checkpoint icons, artifact icon): resolution, apparent pixel scale, palette, and whether it's structured in a way that could reasonably be sliced/reused as tile units.
- **Compatibility assessment, reported explicitly:** for each asset, determine whether it's visually compatible with a coherent, consistently-scaled world-space (§5) — same apparent pixel-per-unit scale and lighting logic as the rest of the scene. Assets that are compatible get integrated as-is. Assets that are **not** compatible must be listed explicitly, by name, with the specific reason (e.g. "background is a single bespoke illustration at a different implied scale than the avatar sprites and isn't structured as tileable units").
- **If incompatible assets block a coherent-world result, stop and report — do not generate replacements.** The correct next step is a scoped decision by the person reviewing this work (e.g. "regenerate the background as a tile atlas matching the avatar scale" or "keep the current composite background and adjust the avatars to match instead"), made as its own controlled task, not an improvisation made mid-implementation.
- **Do not design or generate any character sprite, name, or likeness resembling existing copyrighted media characters** (e.g. sitcom characters, anime characters) — this applies to any future asset-generation task, not just this implementation session, and is called out here so it isn't lost if generation work is picked up later by someone else.
- If walk-cycle animation is ever pursued later (optional stretch, not part of this migration), that too is asset-generation work subject to the same rule: proposed and reviewed separately, not built spontaneously mid-implementation.
- Preload whatever assets are actually used (existing or later-approved replacements) before the first render, mirroring the "Step 1: static scene first, confirm layout before any logic" discipline already used in this project.
- Keep texture/tilemap resolution modest — this is a dashboard-embedded panel, not a full-screen application.

---

## 7. Animation/state strategy

- A single renderer-driven update loop (a ticker/frame callback) replaces CSS transitions as the source of motion. Every entity's `update(dt)` advances its own position/animation state each frame. Each frame's update also re-runs Y-sort (§5, firm requirement) on `EntityLayer` so depth ordering stays correct as entities and artifacts move — this applies whether the static world beneath them ends up as a tilemap or a grid-aligned composite.
- Movement: interpolate position per frame, resting at grid-aligned positions (per §3.3) with straight-line or simple-waypoint interpolation in transit. Easing can be layered in without a full animation library if desired.
- The event stream remains the single source of truth. A thin **event-to-world-action translation layer** — a straightforward port of the mapping logic that already exists in the current JS event handlers — consumes the same `events.jsonl`/mock playback stream and calls world-state methods (spawn an artifact between two desks, set an agent's state, show a terminal-state flourish at a desk).
- **Ambient lighting/mood, if used, is a scene-level choice** (a single global tint/overlay on the world container, or baked into whatever static assets are used) rather than stacked per-element glow filters — this is a visual-quality principle worth keeping regardless of the tilemap-vs-composite decision in §5/§6.
- **Camera:** the update loop does not drive any camera motion this milestone — the transform stays fixed at the static full-office framing decided in §5. No code should animate, pan, zoom, or follow the camera in this pass.
- **Do not change mock-playback pacing/timing behavior.** The existing poll-and-replay-at-a-readable-pace approach for `events.jsonl` stays as-is; only the thing being fed by that stream changes.
- The HTML event log panel keeps consuming the exact same event stream **independently** of the canvas world — it has no dependency on the renderer being correct, and this dual-surface pattern is the reason the hybrid architecture is safer than a canvas-only one.

---

## 8. Migration plan from the current UI

Phased and non-destructive — mirrors the discipline already used for the original build order (verify each step before moving on).

1. **Inventory existing assets and report tilemap feasibility before writing any rendering code.** Per §6: catalog every current visual asset, assess compatibility with a coherent, consistently-scaled world-space, and explicitly report whether a genuine tilemap conversion is reasonable or whether a grid-aligned composited alternative is the right call instead. Do not proceed past this step on an assumption.
2. **Add the new world canvas as a new layer; don't remove anything yet.** Mount the new renderer inside the existing world-region container, alongside (not replacing) the current CSS-composited scene. Render the static world (using whichever approach step 1 determined — tilemap or grid-aligned composite), desks, and at-rest agents with correct Y-sort placement and a fixed full-office camera. Confirm desk positions match the existing fixed-coordinate layout. Stop and show me before continuing.
3. **Port the event-to-visual mapping logic to the new world-state layer**, matching the existing JS event handlers behavior-for-behavior (started/finished, artifact spawn/travel/arrival, owner-based correction routing, the Strategist re-synthesis hop after any correction, terminal-state distinctions, and the traveling Work Artifact mechanic preserved as-is). This is a port of already-working logic — do not redesign the mapping while porting it.
4. **Re-run the existing mock cycle fixture(s) against the new world renderer.** Confirm: identical artifact routing (goes only to the owner(s) named in a REVISE), identical terminal-state visuals distinguishable from each other, correct Y-sort occlusion as entities/artifacts move, and no timing/pacing regression in mock playback. Do not proceed to step 5 without this comparison actually being done.
5. **Swap the mount point.** Once behavior parity is confirmed, hide/remove the old CSS-composited scene, make the new world canvas the live renderer. Do not touch the header, event log, or controls in this step.
6. **Stop here.** Any renderer-only polish (glow/particle effects, hover tooltips, ambient idle motion, room-zone labels, or any camera behavior beyond the fixed framing) is explicitly optional and out of scope for this session unless asked for.

---

## 9. Risks and scope control

- **New dependency / learning curve for a teammate.** Mitigate by isolating all renderer-specific code (including tilemap/composite and Y-sort logic) to one module, documenting the entity/event mapping clearly.
- **Scope creep into "actual game" territory** (physics, pathfinding, real walk-cycle animation, real-time multiplayer-style sync). Mitigate by explicitly scoping this migration to the rendering architecture only.
- **Forcing an artificial tilemap conversion when assets don't support it (new).** Mitigate directly via §5/§6/§8 step 1: tilemap is conditional on asset inspection, not mandatory, and a grid-aligned composited alternative is an accepted, correct outcome if that's what the assets support.
- **Unilateral asset generation during implementation (new).** Mitigate by the hard rule in §6: the implementation agent inventories and integrates, it does not generate or regenerate art. Any asset gap is reported and handled as a separate task.
- **Camera scope creep (new).** Mitigate by treating the fixed full-office camera as a hard limit for this milestone (§5, §7) — the abstraction exists for future use, but no pan/zoom/follow/cinematic behavior should appear in this pass's deliverable.
- **Event-contract fidelity regression during the port** (e.g. a REVISE routing to the wrong owner, `WAIT` rendering identically to `REJECT`). Mitigate via migration step 4: no sign-off without an explicit side-by-side re-run of the same mock cycles used to validate the current UI.
- **IP/likeness risk from reference material.** Do not let any future asset generation drift toward recognizable characters/likenesses from either reference.
- **Overclaiming reference-derived requirements (new, from this revision).** Keep the distinction from §3 in mind for any future revision of this document too: visual inference from screenshots should inform technique choices, not be presented as confirmed implementation fact about the references themselves.
- **Bundle size / load time increase.** Acceptable for a dashboard-embedded demo panel; not a reason to avoid the migration up front.
- **Accessibility/debuggability regression.** Mitigate by keeping the HTML event log as the accessible, inspectable source of truth for "what happened."
- **Scope reminder:** this is a UI rendering architecture decision only. No changes to `orchestrator.py`, the event schema, the Mentor contract, or any backend/trading logic are in scope for this migration.

---

## 10. Implementation prompt for a repository-aware coding agent

*Not to be run until this document is reviewed and approved — this is the prepared prompt for when implementation begins.*

```
You are migrating the AlphaSwarm office visualization from a composited HTML/CSS scene
to a hybrid architecture: a lightweight 2D rendering library (PixiJS, or a comparably
scoped alternative if you have a strong reason to prefer one — state your reasoning
before switching) drives a coherent, grid-aligned world canvas with Y-sorted entity
depth and a fixed camera, while all existing HTML/CSS UI chrome (header, event log,
controls, status readouts) is preserved unchanged.

Read this entire prompt before writing any code. This is a rendering-architecture
migration only. Do not modify orchestrator.py, the event schema/contract, the Mentor
schema, decision_store.py, or any backend/trading logic. If you think a backend change
would help, stop and flag it — do not make it.

============================================================
STEP 0 — INVENTORY ASSETS AND CODE BEFORE ASSUMING ANYTHING
============================================================
Do this before writing or changing any rendering code:

A) Read the current UI implementation: background/desk/avatar rendering, the
   event-to-visual mapping logic, the mock playback poller, the event log panel.
   Confirm the exact current event schema in use (should match: agent started/finished,
   strategist finished with decision PROPOSE|NO_TRADE, mentor audit_complete with
   overall_decision APPROVE|REVISE|REJECT|WAIT and an imperfections[] list keyed by
   "owner", risk_engine check_result PASS|FAIL, execution filled|rejected|error), the
   current desk/checkpoint fixed-coordinate layout, and the mock events.jsonl fixture
   file(s) and playback pacing.

B) INVENTORY every existing visual asset (background, agent avatars, checkpoint icons,
   artifact icon): note resolution, apparent pixel scale, palette, and whether each one
   is structured in a way that could reasonably be sliced/reused as tile units.

C) ASSESS AND REPORT tilemap feasibility. Determine whether the existing assets can
   reasonably be converted into or rebuilt as a coherent tile atlas at one consistent
   scale. If yes, that's the path to take. If NOT — e.g. the background is a single
   bespoke illustration not designed as tileable units, or converting it would degrade
   visual quality — do NOT force an artificial tilemap conversion. Instead, report this
   explicitly and propose a well-structured, grid-aligned COMPOSITED alternative that
   still delivers consistent scale, layering, and depth. Either path is acceptable; the
   requirement is a coherent grid-aligned world with consistent scale/layering/depth,
   not literally "must be a tilemap."

D) List any assets that are visually INCOMPATIBLE with a coherent world (mismatched
   scale, palette, or lighting relative to the rest of the scene), by name, with the
   specific reason. DO NOT regenerate or redesign these assets yourself. Stop and report
   them — asset generation is a separate, controlled task with its own review, not
   something to improvise mid-implementation.

Report all of A-D back before proceeding to Step 1. If anything conflicts with this
prompt's assumptions, the real code/real assets are ground truth — flag the conflict.

============================================================
TARGET ARCHITECTURE (do not deviate without flagging why)
============================================================
- One rendering-library application mounted into the existing "world" region container
  (a sibling of the header/event-log/controls elements — do not restructure the overall
  page layout).
- The floor/walls/desk-and-checkpoint props must form a coherent, grid-aligned world-
  space with consistent scale, palette, and lighting. Use a genuine tilemap if Step 0
  determined the assets reasonably support one; otherwise use the grid-aligned
  composited alternative you proposed and reported in Step 0. Do not force a tilemap
  conversion that Step 0 flagged as unreasonable.
- Layer stack, bottom to top: FloorLayer → WallLayer (may combine with floor depending
  on the approach taken) → PropLayer (static desks/checkpoint icons) → EntityLayer
  (agents + artifacts) → EffectLayer (glows, terminal-state flourishes).
- EntityLayer uses Y-SORT depth ordering (sort by each entity's screen Y-position every
  frame) for all dynamic entities — agents and artifacts. This is a FIRM requirement,
  independent of whether the static world beneath is a tilemap or a composite.
- A single camera transform (position + scale) wrapping the layer stack, kept as an
  abstraction for future use, but FIXED to a static full-office framing for this
  milestone. Do NOT implement pan, zoom, follow, or any cinematic camera behavior —
  that is explicitly out of scope for this pass, not a stretch goal to attempt if time
  allows.
- Ambient lighting/mood, if used, is a single global tint/overlay on the world
  container (or baked into whatever static assets are actually used), not stacked
  per-element glow filters.
- Entities: persistent Agent entities (created once, reused every cycle) with state
  idle | working | correction_target, each with position, sprite reference, and an
  update(dt) method. Ephemeral Artifact entities spawned on an agent's "finished" event,
  destroyed on arrival at the recipient. Keep agent-state and artifact-state as two
  separate state machines.
- PRESERVE the traveling Work Artifact mechanic exactly as it currently works
  conceptually — this is an intentional, AlphaSwarm-specific visualization of targeted
  correction routing and stays regardless of how the reference material handles
  handoffs. Do not remove, simplify away, or replace it with a status-tag-only approach.
- Terminal states (Strategist NO_TRADE, Mentor REJECT, Mentor WAIT, Risk Engine FAIL,
  execution rejected/error) render as short-lived, auto-fading world events (icon +
  label above the relevant desk) — not a persistent change to the base agent sprite.
  REJECT, WAIT, and Risk Engine FAIL must be visually distinguishable from each other.
- The HTML event log keeps consuming the exact same event stream independently of the
  canvas world — it must have zero dependency on the renderer being correct.

============================================================
ASSET RULES (do not skip)
============================================================
- You may INVENTORY and INTEGRATE existing assets. You may NOT generate, regenerate, or
  redesign artwork on your own initiative, for any reason, including to "fix" a
  compatibility problem you find. If existing assets are incompatible with a coherent
  world-space (mismatched scale/palette/lighting), STOP and report exactly which assets
  and why (per Step 0D) — do not substitute placeholder or generated art without
  explicit approval first.
- Do NOT design or generate any character sprite, name, or likeness resembling existing
  copyrighted media characters (e.g. sitcom characters, anime characters), even loosely,
  if asset generation is ever separately approved later — AlphaSwarm's agents should
  read as generic, functionally-named office workers with their own visual identity.

============================================================
MIGRATION STEPS — DO NOT SKIP OR REORDER
============================================================
1. Complete Step 0 (inventory + feasibility report) and share the results before writing
   any rendering code.
2. Add the new world canvas as a NEW layer inside the existing world-region container.
   Do not remove or hide the current CSS-composited scene yet. Render the static world
   (tilemap or composite, per Step 0's finding), desks, and at-rest agents with correct
   Y-sort placement and the fixed full-office camera. Confirm desk positions match the
   existing fixed-coordinate layout (translated to the new coordinate system). Stop and
   show me before continuing.
3. Port the event-to-visual mapping logic into the new world-state layer, matching the
   existing JS event handlers behavior-for-behavior (started/finished, artifact spawn/
   travel/arrival, owner-based correction routing, the Strategist re-synthesis hop after
   any correction, terminal-state distinctions, traveling Work Artifact preserved).
4. Re-run the existing mock cycle fixture(s) against the new world renderer. Confirm:
   identical artifact routing (goes only to the owner(s) named in a REVISE), identical
   terminal-state visuals distinguishable from each other, correct Y-sort occlusion as
   entities move, no timing/pacing regression in mock playback. Do not proceed to step 5
   without this comparison actually being done.
5. Once parity is confirmed, swap the mount point: hide/remove the old CSS-composited
   scene, make the new world canvas the live renderer. Do not touch the header, event
   log, or controls in this step.
6. Stop here. Any renderer-only polish (glow/particle effects, hover tooltips, ambient
   idle motion, room-zone labels, or ANY camera behavior beyond the fixed framing) is
   explicitly optional and out of scope for this session unless I ask for it.

============================================================
GUARDRAILS
============================================================
- No physics, no collision detection, no pathfinding around obstacles — straight-line
  or simple-waypoint artifact movement only.
- No pan/zoom/follow/cinematic camera behavior in this pass, even as a demo of
  capability — the abstraction exists, the behavior does not, this milestone.
- No asset generation or regeneration under any circumstances in this session — report
  and stop instead.
- No changes to events.jsonl schema, mock fixture files, orchestrator.py, or any backend
  code. If the migration seems to require one, stop and flag it to me rather than making
  the change.
- If you hit a case where the current UI's actual behavior differs from what this prompt
  describes, the current UI's real behavior wins — flag the discrepancy, don't silently
  pick one.

============================================================
YOUR DELIVERABLE FOR THIS SESSION
============================================================
1. Complete the inventory/feasibility analysis first.
2. Report the Step 0 findings before modifying any rendering code.
3. After approval, implement only the static world-rendering stage:
   - renderer setup
   - world-space coordinate system
   - fixed camera
   - static environment
   - desks/props
   - persistent agent entities
   - Y-sort
   - existing assets only
4. Do NOT integrate event playback yet.
5. Do NOT remove, hide, or modify the existing CSS scene yet.
6. Stop after the static renderer is working and report:
   - files changed
   - architecture implemented
   - assets used
   - tilemap vs composited decision and reasoning
   - coordinate mapping
   - how Y-sort works
   - how the old renderer remains untouched
   - any visual/asset problems discovered
7. Wait for explicit approval before proceeding to event integration.

Do not proceed to event mapping, mock playback integration, old-renderer removal,
or optional polish without explicit approval.
