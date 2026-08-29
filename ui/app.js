/**
 * AlphaSwarm Office Visualization — app.js
 * =========================================
 * Corrected event schema matching the real backend:
 *   - Strategist NO_TRADE terminal path
 *   - Mentor APPROVE / REVISE / REJECT / WAIT (4 outcomes)
 *   - Owner-based correction routing from imperfections[]
 *   - Strategist re-synthesis hop after corrections
 *   - Risk Engine FAIL distinct from Mentor REJECT
 *   - Execution filled / rejected / error distinct visuals
 *   - One-revision-round hard cap enforcement
 */

'use strict';

// World coordinates and artifact destinations are owned by renderer.js.

const GLOW_IDS = {
  market_agent:     'glow-market',
  volatility_agent: 'glow-volatility',
  options_agent:    'glow-options',
  portfolio_agent:  'glow-portfolio',
  strategist:       'glow-strategist',
  mentor:           'glow-mentor',
  risk_engine:      'glow-risk',
  execution:        'glow-execution',
};

const LAYER1_AGENTS = ['market_agent', 'volatility_agent', 'options_agent', 'portfolio_agent'];

/* ──────────────────────────────────────────────────────────────
   STATE
────────────────────────────────────────────────────────────── */
let eventCount          = 0;
let activeCycleId       = null;
let bubbleTimers        = {};   // agent → timeout id
let glowTimers          = {};   // agent → timeout id

/* Correction-round state */
let inCorrectionRound   = false;
let correctionRound     = 0;     // 0 = initial; system hard-caps at 1
let lastCorrectedAgent  = null;  // tracks last corrected agent to finish

/* Polling state (Step 4) */
let pollIntervalId      = null;
let lastSeqSeen         = 0;
let currentLogFile      = null;

/* Mock playback state */
let mockPlaybackTimers  = [];

/* ──────────────────────────────────────────────────────────────
   DOM REFS
────────────────────────────────────────────────────────────── */
const $logList       = document.getElementById('event-log-list');

/* ──────────────────────────────────────────────────────────────
   UTILITY — STATE & VISUAL EFFECTS (Routed to Renderer)
────────────────────────────────────────────────────────────── */

function setLiveStatus(mode, cycleId = null) {
  if (mode === 'live' && cycleId) {
    activeCycleId = cycleId;
  }
  updateCycleStats();
}

function updateCycleStats() {
  const $statusPhase = document.getElementById('status-phase');
  if ($statusPhase) {
    $statusPhase.textContent = `Cycle: ${activeCycleId || 'None'} | Events: ${eventCount}`;
  }
}

function resetScene() {
  stopPolling();
  mockPlaybackTimers.forEach(clearTimeout);
  mockPlaybackTimers = [];

  Object.keys(GLOW_IDS).forEach(agent => setGlow(agent, null));
  hideAllBubbles();
  clearAllTerminalBadges();

  if (window.AlphaSwarmWorld && window.AlphaSwarmWorld.reset) {
    window.AlphaSwarmWorld.reset();
  }

  eventCount = 0;
  activeCycleId = null;
  lastSeqSeen = 0;
  inCorrectionRound = false;
  correctionRound = 0;
  lastCorrectedAgent = null;

  updateCycleStats();
  if ($logList) $logList.innerHTML = '';
  logEvent('Scene reset.', 'ev-started');
}

function setGlow(agent, state, autoOffMs = 0) {
  if (window.AlphaSwarmWorld && window.AlphaSwarmWorld.setAgentState) {
    window.AlphaSwarmWorld.setAgentState(agent, state);
    
    if (glowTimers[agent]) {
      clearTimeout(glowTimers[agent]);
      delete glowTimers[agent];
    }
    if (autoOffMs > 0) {
      glowTimers[agent] = setTimeout(() => {
        window.AlphaSwarmWorld.setAgentState(agent, null);
      }, autoOffMs);
    }
  }
}

/* ──────────────────────────────────────────────────────────────
   UTILITY — SPEECH BUBBLES
────────────────────────────────────────────────────────────── */

function showBubble(agent, text, durationMs = 3000, type = '') {
  if (window.AlphaSwarmWorld && window.AlphaSwarmWorld.showBubble) {
    window.AlphaSwarmWorld.showBubble(agent, text, type);
    
    if (bubbleTimers[agent]) {
      clearTimeout(bubbleTimers[agent]);
      delete bubbleTimers[agent];
    }
    
    if (durationMs > 0) {
      bubbleTimers[agent] = setTimeout(() => {
        window.AlphaSwarmWorld.hideBubble(agent);
      }, durationMs);
    }
  }
}

function hideAllBubbles() {
  if (window.AlphaSwarmWorld && window.AlphaSwarmWorld.hideAllBubbles) {
    window.AlphaSwarmWorld.hideAllBubbles();
  }
}

/* ──────────────────────────────────────────────────────────────
   UTILITY — TERMINAL BADGES
   Dynamically created overlays for cycle-ending events.
────────────────────────────────────────────────────────────── */

/**
 * Show a terminal badge over an agent's station.
 * @param {string} agent       — agent key
 * @param {string} label       — e.g. "NO_TRADE", "✗ REJECTED", "⏸ WAIT"
 * @param {string} badgeClass  — CSS class: 'badge-no-trade', 'badge-rejected',
 *                                'badge-waiting', 'badge-risk-fail', 'badge-exec-error'
 */
function showTerminal(agent, label, badgeClass) {
  if (window.AlphaSwarmWorld && window.AlphaSwarmWorld.showTerminalBadge) {
    window.AlphaSwarmWorld.showTerminalBadge(agent, label, badgeClass);
  }
}

function clearTerminalBadge(agent) {
  if (window.AlphaSwarmWorld && window.AlphaSwarmWorld.clearTerminalBadge) {
    window.AlphaSwarmWorld.clearTerminalBadge(agent);
  }
}

function clearAllTerminalBadges() {
  if (window.AlphaSwarmWorld && window.AlphaSwarmWorld.clearAllTerminalBadges) {
    window.AlphaSwarmWorld.clearAllTerminalBadges();
  }
}

/* ──────────────────────────────────────────────────────────────
   UTILITY — WORK ARTIFACT TRAVEL
────────────────────────────────────────────────────────────── */

/**
 * Spawn the artifact at `fromAgent` and slide it to `toAgent`.
 * Uses PixiJS WorldRenderer instead of DOM transitions.
 */
function travelArtifact(fromAgent, toAgent, label = '', onArrival = null) {
  if (window.AlphaSwarmWorld && window.AlphaSwarmWorld.travelArtifact) {
    window.AlphaSwarmWorld.travelArtifact(fromAgent, toAgent, label, onArrival);
  } else {
    console.warn("AlphaSwarmWorld not ready for travelArtifact");
    if (onArrival) setTimeout(onArrival, 900);
  }
}

/* ──────────────────────────────────────────────────────────────
   UTILITY — EVENT LOG
────────────────────────────────────────────────────────────── */
function logEvent(text, cssClass = '') {
  const now = new Date();
  const ts  = now.toLocaleTimeString('en-GB', { hour12: false });

  const li    = document.createElement('li');
  li.className = `log-entry${cssClass ? ' ' + cssClass : ''}`;
  li.innerHTML = `<div class="log-entry-time">${ts}</div>
                  <div class="log-entry-text">${escapeHtml(text)}</div>`;

  $logList.prepend(li);

  eventCount++;
  updateCycleStats();
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ──────────────────────────────────────────────────────────────
   STEP 2 — Debug Trigger
────────────────────────────────────────────────────────────── */
function debugTriggerEvent() {
  logEvent('[DEBUG] market_agent finished → Strategist', 'ev-started');
  setLiveStatus('live', 'debug_cycle');
  setGlow('market_agent', 'working');

  setTimeout(() => {
    setGlow('market_agent', 'received', 1200);
    travelArtifact('market_agent', 'strategist', 'Research', () => {
      setGlow('strategist', 'received', 2000);
      logEvent('[DEBUG] Artifact arrived at Strategist.', 'ev-finished');
    });
    logEvent('[DEBUG] market_agent finished → artifact → Strategist', 'ev-finished');
  }, 800);
}

/* ══════════════════════════════════════════════════════════════
   CORE — EVENT PROCESSING
   Central dispatch: every event from events.jsonl goes through
   here. All event→visual logic lives in this function.
   ══════════════════════════════════════════════════════════════ */

function processEvent(ev) {
  const {
    agent,
    event: evType,
    summary       = '',
    result,
    overall_decision,
    decision_id,
    decision,            // strategist: "PROPOSE" | "NO_TRADE"
    imperfections = [],
    severity,
  } = ev;

  // Update status bar
  if (decision_id) setLiveStatus('live', decision_id);

  switch (evType) {

    /* ─────────────────────────────────
       agent: started
    ───────────────────────────────── */
    case 'started': {
      setGlow(agent, 'working');
      logEvent(`${agent}: started`, 'ev-started');

      // During correction round, if the STRATEGIST starts, that's the
      // re-synthesis hop — artifact travels from the last corrected agent.
      if (inCorrectionRound && agent === 'strategist' && lastCorrectedAgent) {
        travelArtifact(lastCorrectedAgent, 'strategist', 'Re-synthesis');
        inCorrectionRound = false;
        logEvent('Corrections complete → Strategist re-synthesis', 'ev-finished');
      }
      break;
    }

    /* ─────────────────────────────────
       agent: finished
    ───────────────────────────────── */
    case 'finished': {
      setGlow(agent, null);

      // ── Strategist NO_TRADE: TERMINAL — cycle ends here ──
      if (agent === 'strategist' && decision === 'NO_TRADE') {
        setGlow('strategist', 'no-trade');
        showTerminal('strategist', 'NO_TRADE', 'badge-no-trade');
        if (summary) showBubble('strategist', summary, 7000);
        logEvent(`Strategist: NO_TRADE — "${summary}"`, 'ev-notrade');
        setLiveStatus('idle');
        break;
      }

      // ── During correction round: corrected agents don't route artifacts ──
      // They just show completion glow. The artifact-to-strategist travel
      // is triggered by the strategist's own "started" event (see above).
      if (inCorrectionRound && LAYER1_AGENTS.includes(agent)) {
        setGlow(agent, 'received', 2500);
        lastCorrectedAgent = agent;
        if (summary) showBubble(agent, summary, 4000);
        logEvent(`${agent}: finished (correction) — "${summary}"`, 'ev-finished');
        break;
      }

      // ── Normal finished → artifact to next station ──
      const dest = recipientOf(agent);
      if (dest) {
        travelArtifact(agent, dest, truncate(summary, 22), () => {
          setGlow(dest, 'received', 2500);
        });
        logEvent(`${agent}: finished — "${summary}" → ${dest}`, 'ev-finished');
      } else {
        logEvent(`${agent}: finished — "${summary}"`, 'ev-finished');
      }
      if (summary) showBubble(agent, summary, 4000);
      break;
    }

    /* ─────────────────────────────────
       mentor: audit_complete
    ───────────────────────────────── */
    case 'audit_complete': {
      setGlow('mentor', null);

      switch (overall_decision) {

        // ── REVISE: artifact back to flagged owners only ──
        case 'REVISE': {
          correctionRound++;

          // Hard cap: exactly ONE revision round. A second REVISE is a bug.
          if (correctionRound > 1) {
            logEvent('⚠ BUG: Second REVISE — system hard-caps at one revision round', 'ev-error');
            showBubble('mentor', '⚠ Unexpected second revision', 5000);
            setGlow('mentor', 'rejected');
            setLiveStatus('idle');
            break;
          }

          // Extract unique owners from imperfections (excluding "none")
          const owners = [...new Set(
            imperfections
              .map(imp => imp.owner)
              .filter(o => o && o !== 'none' && Object.hasOwn(GLOW_IDS, o))
          )];
          const label = owners.length ? owners.join(', ') : 'flagged agent(s)';

          setGlow('mentor', 'mentor-active', 3000);
          logEvent(`Mentor: REVISE → targeting ${label}`, 'ev-revise');

          // Enter correction round
          inCorrectionRound = true;
          lastCorrectedAgent = null;

          // Artifact travels from Mentor to EACH flagged owner (staggered)
          owners.forEach((tgt, i) => {
            setTimeout(() => {
              travelArtifact('mentor', tgt, 'Correction', () => {
                setGlow(tgt, 'correction');
              });
            }, i * 1200);
          });
          break;
        }

        // ── APPROVE: artifact → Risk Engine ──
        case 'APPROVE': {
          setGlow('mentor', 'received', 1500);
          inCorrectionRound = false;
          logEvent('Mentor: APPROVE → artifact to Risk Engine', 'ev-approve');
          travelArtifact('mentor', 'risk_engine', 'Proposal', () => {
            setGlow('risk_engine', 'working');
          });
          break;
        }

        // ── REJECT: TERMINAL — fundamental flaws ──
        case 'REJECT': {
          setGlow('mentor', 'rejected');
          showTerminal('mentor', '✗ REJECTED', 'badge-rejected');
          showBubble('mentor', '✗ REJECTED — fundamental flaws', 6000);
          logEvent('Mentor: REJECT — cycle terminated', 'ev-reject');
          setLiveStatus('idle');
          break;
        }

        // ── WAIT: TERMINAL — missing information (distinct from REJECT) ──
        case 'WAIT': {
          setGlow('mentor', 'waiting');
          showTerminal('mentor', '⏸ WAIT', 'badge-waiting');
          showBubble('mentor', '⏸ WAIT — deferred, missing info', 6000);
          logEvent('Mentor: WAIT — cycle deferred', 'ev-wait');
          setLiveStatus('idle');
          break;
        }

        default:
          logEvent(`Mentor: unknown decision "${overall_decision}"`, 'ev-error');
      }
      break;
    }

    /* ─────────────────────────────────
       agent: correction_target
       Speech bubble showing the action
       requested by the Mentor.
    ───────────────────────────────── */
    case 'correction_target': {
      setGlow(agent, 'correction');
      if (summary) showBubble(agent, summary, 6000);
      logEvent(`${agent}: correction target — "${summary}"`, 'ev-correction');
      break;
    }

    /* ─────────────────────────────────
       risk_engine: check_result
       Deterministic — distinct visual
       from Mentor REJECT.
    ───────────────────────────────── */
    case 'check_result': {
      if (result === 'PASS') {
        setGlow('risk_engine', 'risk-pass');
        showBubble('risk_engine', '✓ PASS', 3000);
        logEvent(`Risk Engine: PASS — ${summary || 'all checks clear'}`, 'ev-risk');
        setTimeout(() => {
          travelArtifact('risk_engine', 'execution', 'Order', () => {
            setGlow('execution', 'received');
          });
        }, 800);
      } else {
        // FAIL — deterministic rejection, visually distinct from Mentor REJECT
        // (crimson pulsing vs red pulsing, different badge style)
        setGlow('risk_engine', 'risk-fail');
        showTerminal('risk_engine', '✗ RISK FAIL', 'badge-risk-fail');
        showBubble('risk_engine', `✗ FAIL: ${summary || 'risk checks failed'}`, 7000);
        logEvent(`Risk Engine: FAIL — ${summary || 'deterministic rejection'}`, 'ev-risk-fail');
        setLiveStatus('idle');
      }
      break;
    }

    /* ─────────────────────────────────
       execution: filled
    ───────────────────────────────── */
    case 'filled': {
      setGlow('execution', 'received');
      const msg = summary || 'Order filled';
      showBubble('execution', `✓ ${msg}`, 8000);
      logEvent(`Execution: FILLED — "${msg}"`, 'ev-filled');
      setLiveStatus('idle');
      break;
    }

    /* ─────────────────────────────────
       execution: rejected
       (Alpaca / broker rejected order)
    ───────────────────────────────── */
    case 'rejected': {
      setGlow('execution', 'exec-error');
      showTerminal('execution', '✗ ORDER REJECTED', 'badge-exec-error');
      showBubble('execution', `✗ ${summary || 'Order rejected'}`, 7000);
      logEvent(`Execution: REJECTED — "${summary || 'order rejected'}"`, 'ev-error');
      setLiveStatus('idle');
      break;
    }

    /* ─────────────────────────────────
       execution: error
       (exception during submission)
    ───────────────────────────────── */
    case 'error': {
      setGlow('execution', 'exec-error');
      showTerminal('execution', '⚠ ERROR', 'badge-exec-error');
      showBubble('execution', `⚠ ${summary || 'Execution error'}`, 7000);
      logEvent(`Execution: ERROR — "${summary || 'execution error'}"`, 'ev-error');
      setLiveStatus('idle');
      break;
    }

    /* ─────────────────────────────────
       default: unknown event type
    ───────────────────────────────── */
    default:
      logEvent(`${agent}: ${evType}${summary ? ' — "' + summary + '"' : ''}`, '');
  }
}

/* ──────────────────────────────────────────────────────────────
   ROUTING TABLE
   Determines the default next station for a finished agent.
   REVISE/APPROVE/REJECT/WAIT routing is handled in audit_complete,
   not here.
────────────────────────────────────────────────────────────── */
function recipientOf(agent) {
  if (LAYER1_AGENTS.includes(agent)) return 'strategist';
  if (agent === 'strategist') return 'mentor';
  return null;
}

function truncate(s, maxLen) {
  if (!s) return '';
  return s.length > maxLen ? s.slice(0, maxLen) + '…' : s;
}

/* ──────────────────────────────────────────────────────────────
   POLLING (Step 4 — live events.jsonl)
────────────────────────────────────────────────────────────── */
async function pollFile(filePath) {
  try {
    const res = await fetch(filePath + '?t=' + Date.now());
    if (!res.ok) return;
    const text = await res.text();
    const lines = text.trim().split('\n').filter(Boolean);

    for (const line of lines) {
      try {
        const ev = JSON.parse(line);
        if (ev.seq > lastSeqSeen) {
          lastSeqSeen = ev.seq;
          processEvent(ev);
        }
      } catch (_) { /* skip malformed line */ }
    }
  } catch (_) { /* file not found — silently ignore */ }
}

function startPolling(filePath, intervalMs = 1500) {
  if (pollIntervalId) stopPolling();
  currentLogFile = filePath;
  lastSeqSeen = 0;
  logEvent(`Polling: ${filePath}`, '');
  setLiveStatus('live');
  pollIntervalId = setInterval(() => pollFile(filePath), intervalMs);
}

function stopPolling() {
  if (pollIntervalId) {
    clearInterval(pollIntervalId);
    pollIntervalId = null;
  }
}

/* ──────────────────────────────────────────────────────────────
   MOCK PLAYBACK (Step 3)
   Loads mock_events.jsonl and plays events one-by-one with
   configurable delays. Each cycle separated by a longer pause.
────────────────────────────────────────────────────────────── */
async function playMockFile(filePath) {
  try {
    const res = await fetch(filePath + '?t=' + Date.now());
    if (!res.ok) {
      logEvent(`Error: could not load ${filePath}`, 'ev-error');
      return;
    }
    const text = await res.text();
    const lines = text.trim().split('\n').filter(Boolean);
    const events = [];
    for (const line of lines) {
      try { events.push(JSON.parse(line)); } catch (_) {}
    }

    if (events.length === 0) {
      logEvent('No events in mock file.', 'ev-error');
      return;
    }

    const INTER_EVENT_MS = 2600;  // delay between events to allow physical walking & handoffs
    const INTER_CYCLE_MS = 5000;  // extra pause between cycles

    let delay = 300;
    let prevDecisionId = null;

    for (const ev of events) {
      // Extra pause between different cycles
      if (prevDecisionId && ev.decision_id !== prevDecisionId) {
        delay += INTER_CYCLE_MS;
      }

      const timer = setTimeout(() => processEvent(ev), delay);
      mockPlaybackTimers.push(timer);
      delay += INTER_EVENT_MS;
      prevDecisionId = ev.decision_id;
    }

    const totalSec = Math.round(delay / 1000);
    logEvent(`Mock playback: ${events.length} events over ~${totalSec}s`, '');
  } catch (e) {
    logEvent(`Error loading mock file: ${e.message}`, 'ev-error');
  }
}

/* ──────────────────────────────────────────────────────────────
   WIRING — UI CONTROLS
────────────────────────────────────────────────────────────── */

document.getElementById('btn-reset').addEventListener('click', () => {
  resetScene();
});

document.getElementById('btn-clear-log').addEventListener('click', () => {
  if ($logList) $logList.innerHTML = '';
  eventCount = 0;
  updateCycleStats();
});

document.getElementById('btn-debug-trigger').addEventListener('click', debugTriggerEvent);

document.getElementById('btn-playback').addEventListener('click', () => {
  resetScene();
  setTimeout(() => {
    playMockFile('mock_events.jsonl');
    logEvent('▶ Mock playback started…', 'ev-started');
  }, 400);
});

/* ──────────────────────────────────────────────────────────────
   MUNDER DIFFLIN SHELL INTEGRATION
────────────────────────────────────────────────────────────── */

// 1. Responsive Workspace Scaling
function resizeWorkspace() {
  const container = document.getElementById('workspace-content');
  const sceneWrapper = document.getElementById('scene-wrapper');
  if (!container || !sceneWrapper) return;
  
  // Logical dimensions of the scene
  const sceneW = 960;
  const sceneH = 640;
  
  const containerW = container.clientWidth;
  const containerH = container.clientHeight;
  
  // Calculate scale to fit with 20px padding
  const scale = Math.min(
    (containerW - 40) / sceneW,
    (containerH - 40) / sceneH
  );
  
  // Apply scale via transform
  sceneWrapper.style.transform = `scale(${Math.max(0.2, scale)})`;
}

window.addEventListener('resize', resizeWorkspace);

// 2. Panel Toggles
document.querySelectorAll('.toggle-btn, .rail-item[data-target]').forEach(btn => {
  btn.addEventListener('click', (e) => {
    const targetId = btn.dataset.target || btn.dataset.panel;
    if (!targetId) return;
    const panel = document.getElementById(targetId);
    if (panel) {
      panel.classList.toggle('collapsed');
      if (btn.classList.contains('rail-item')) {
        btn.classList.toggle('active');
      }
      // Trigger resize after animation completes (approx 300ms)
      setTimeout(resizeWorkspace, 300);
    }
  });
});

document.querySelectorAll('.close-sidebar-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const targetId = btn.dataset.panel;
    if (!targetId) return;
    document.getElementById(targetId).classList.add('collapsed');
    
    // Deactivate rail item if applicable
    const railItem = document.querySelector(`.rail-item[data-target="${targetId}"]`);
    if (railItem) railItem.classList.remove('active');
    
    setTimeout(resizeWorkspace, 300);
  });
});

// 3. Command Palette
const $palette = document.getElementById('command-palette');
const $paletteInput = document.getElementById('palette-input');

function togglePalette() {
  if (!$palette) return;
  if ($palette.open) {
    $palette.close();
  } else {
    $palette.showModal();
    if ($paletteInput) {
      $paletteInput.value = '';
      $paletteInput.focus();
    }
  }
}

document.getElementById('btn-open-palette')?.addEventListener('click', togglePalette);

document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    togglePalette();
  }
});

document.querySelectorAll('.palette-item').forEach(item => {
  item.addEventListener('click', () => {
    const action = item.dataset.action;
    if ($palette) $palette.close();
    
    if (action === 'play_mock') document.getElementById('btn-playback')?.click();
    if (action === 'reset') document.getElementById('btn-reset')?.click();
    if (action === 'trigger') document.getElementById('btn-debug-trigger')?.click();
    if (action === 'toggle_left') document.querySelector('.rail-item[data-target="left-sidebar"]')?.click();
    if (action === 'toggle_right') {
      const p = document.getElementById('right-sidebar');
      if (p) p.classList.toggle('collapsed');
      setTimeout(resizeWorkspace, 300);
    }
    if (action === 'toggle_terminal') document.querySelector('.toggle-btn[data-panel="bottom-terminal"]')?.click();
  });
});

/* ──────────────────────────────────────────────────────────────
   INIT
────────────────────────────────────────────────────────────── */
(function init() {
  setLiveStatus('waiting');
  logEvent('AlphaSwarm Office ready.', '');
  
  // Initial resize
  setTimeout(resizeWorkspace, 100);
})();
