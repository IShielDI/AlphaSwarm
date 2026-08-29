/**
 * AlphaSwarm Office Visualization — renderer.js
 * =========================================
 * Visual Refinement Pass #8 — Controlled Furnishing, Proportion & Composition
 * - Balance: 60-70% breathing room, 30-40% purposeful furnishing per room.
 * - Solid Room Boundaries: Dark bevelled architectural walls with single clear 48px doorways.
 * - Wall Flush Furnishings: Every accessory is aligned against perimeter or partition walls.
 * - Character-to-Desk Proportion: 0.60 scale with upright posture and clean non-clipping nameplates.
 * - Strategist Command Hub: 5-Screen Command Workstation on elevated platform, distinct character silhouette.
 * - Mentor Executive Suite: Warm mahogany desk, double bookshelves, side credenza with carafe, compliance board.
 * - Technical Zone Flow: [Risk Checkpoint Gate] -> [Risk Monitor Console] -> [Execution Terminal].
 * - Unobstructed North Windows at (128, 0), (384, 0), and windowed glass entrance at (576, 0) & (704, 0).
 */

'use strict';

const ASSET_MANIFEST = {
  // Environment
  floor_base: 'assets/tile_floor_base.png',
  floor_alt:  'assets/tile_floor_alt.png',
  wall_ns:    'assets/tile_wall_straight_ns.png',
  wall_ew:    'assets/tile_wall_straight_ew.png',
  wall_nw:    'assets/tile_wall_corner_nw.png',
  wall_ne:    'assets/tile_wall_corner_ne.png',
  wall_sw:    'assets/tile_wall_corner_sw.png',
  wall_se:    'assets/tile_wall_corner_se.png',
  wall_door:  'assets/tile_wall_doorway.png',
  wall_win:   'assets/tile_wall_window.png',
  // Architectural Room Dividers & Doors
  glass_part_h: 'assets/prop_glass_partition_h.png',
  glass_part_v: 'assets/prop_glass_partition_v.png',
  door_frame_h: 'assets/prop_door_frame_h.png',
  door_frame_v: 'assets/prop_door_frame_v.png',
  // Workstations & Checkpoints
  desk_standard:        'assets/desk_standard.png',
  desk_senior:          'assets/desk_senior.png',
  desk_mentor:          'assets/desk_mentor.png',
  station_risk_engine:  'assets/station_risk_engine.png',
  station_risk_monitor: 'assets/station_risk_monitor.png',
  station_execution:    'assets/station_execution.png',
  // Role-Specific Wall Displays
  prop_board_market:    'assets/prop_board_market.png',
  prop_board_volatility:'assets/prop_board_volatility.png',
  prop_board_options:   'assets/prop_board_options.png',
  prop_board_portfolio: 'assets/prop_board_portfolio.png',
  prop_board_strategy:  'assets/prop_board_strategy.png',
  prop_board_compliance:'assets/prop_board_compliance.png',
  // Wall & Room Accessories
  prop_panel_telemetry: 'assets/prop_panel_telemetry.png',
  prop_board_docs:      'assets/prop_board_docs.png',
  prop_plant_small:     'assets/prop_plant_small.png',
  prop_cabinet_small:   'assets/prop_cabinet_small.png',
  prop_bookshelf:       'assets/prop_bookshelf.png',
  prop_mentor_credenza: 'assets/prop_mentor_credenza.png',
  prop_strat_console:   'assets/prop_strat_console.png',
  prop_plant_tall:      'assets/prop_plant_tall.png',
  prop_water_cooler:    'assets/prop_water_cooler.png',
  // Characters
  char_market:     'assets/char_market.png',
  char_volatility: 'assets/char_volatility.png',
  char_options:    'assets/char_options.png',
  char_portfolio:  'assets/char_portfolio.png',
  char_strategist: 'assets/char_strategist.png',
  char_mentor:     'assets/char_mentor.png',
  // Artifact
  work_artifact: 'assets/work_artifact.png'
};

const TEXTURES = {};

async function loadAssets() {
  const promises = Object.entries(ASSET_MANIFEST).map(async ([key, url]) => {
    try {
      const tex = await PIXI.Assets.load(url);
      TEXTURES[key] = tex;
    } catch (e) {
      console.warn(`[Asset Loader] Missing asset: ${url}`);
      TEXTURES[key] = null;
    }
  });
  await Promise.all(promises);
}

async function initRenderer() {
  await loadAssets();

  const app = new PIXI.Application({
    width: 960,
    height: 640,
    backgroundColor: 0x0c0f18,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true
  });
  
  const container = document.getElementById('pixi-container');
  if (container) {
    container.innerHTML = '';
    container.appendChild(app.view);
  } else {
    console.error("pixi-container not found!");
    return;
  }

  // World Container & Layer Stack
  const world = new PIXI.Container();
  app.stage.addChild(world);
  
  const floorLayer = new PIXI.Container();
  const entityLayer = new PIXI.Container();
  entityLayer.sortableChildren = true; // Strict Native Y-Sort
  world.addChild(floorLayer, entityLayer);

  // 1. ZONED FLOORING
  const texFloorBase = TEXTURES['floor_base'];
  const texFloorAlt = TEXTURES['floor_alt'];
  if (texFloorBase) {
    for (let x = 0; x <= 960; x += 64) {
      for (let y = 0; y <= 640; y += 64) {
        const useAlt = texFloorAlt && (((x * 17 + y * 31) % 100) < 20);
        const tile = new PIXI.Sprite(useAlt ? texFloorAlt : texFloorBase);
        tile.x = x;
        tile.y = y;

        const isCorridor = (288 <= y && y <= 352 && x <= 608) || (560 <= x && x <= 608 && 48 <= y && y <= 592);
        const isMentor = (x >= 608 && y <= 288);
        const isTech = (x >= 768 && y >= 352);
        const isStrategist = (608 <= x && x <= 768 && y >= 352);

        if (isCorridor) {
          tile.tint = 0xccd6e0;
        } else if (isMentor) {
          tile.tint = 0xd6ccc6;
        } else if (isTech) {
          tile.tint = 0x8a9aa8;
        } else if (isStrategist) {
          tile.tint = 0xa4b4c0;
        } else {
          tile.tint = 0xb0bec5;
        }

        floorLayer.addChild(tile);
      }
    }
  }

  // Elevated Executive & Command Platform Mats
  const drawPlatformMat = (x, y, w, h, tint = 0x141a26) => {
    const mat = new PIXI.Graphics();
    mat.beginFill(tint, 0.45);
    mat.lineStyle(1.5, 0x2e3b52, 0.75);
    mat.drawRoundedRect(x, y, w, h, 6);
    mat.endFill();
    floorLayer.addChild(mat);
  };
  drawPlatformMat(630, 80, 260, 185, 0x241d18);  // Mentor Platform Mat (Warm Walnut)
  drawPlatformMat(620, 375, 140, 195, 0x141c2c); // Strategist Command Platform

  // Static Outer Wall Placements (Windows at 128, 384, 576, 704, Door at 640)
  const addWallTile = (textureKey, x, y, flipH = false) => {
    const texture = TEXTURES[textureKey];
    if (!texture) return;
    const tile = new PIXI.Sprite(texture);
    if (flipH) {
      tile.scale.x = -1;
      tile.x = x + 64;
    } else {
      tile.x = x;
    }
    tile.y = y;
    floorLayer.addChild(tile);
  };

  addWallTile('wall_nw', 0, 0);
  for (let x = 64; x < 896; x += 64) {
    const key = (x === 128 || x === 384 || x === 576 || x === 704) ? 'wall_win' : (x === 640 ? 'wall_door' : 'wall_ew');
    addWallTile(key, x, 0);
  }
  addWallTile('wall_ne', 896, 0);

  for (let y = 64; y < 576; y += 64) {
    addWallTile('wall_ns', 0, y, false);
    addWallTile('wall_ns', 896, y, true);
  }
  addWallTile('wall_sw', 0, 576, false);
  for (let x = 64; x < 896; x += 64) {
    addWallTile('wall_ew', x, 576);
  }
  addWallTile('wall_se', 896, 576, false);

  // Distinct Role-Specific Wall Displays Mounted Directly on Upper Walls Inside Each Room
  const addWallBoard = (texKey, x, y) => {
    const tex = TEXTURES[texKey] || TEXTURES['prop_board_market'];
    if (!tex) return;
    const board = new PIXI.Sprite(tex);
    board.anchor.set(0.5, 0.5);
    board.x = x;
    board.y = y;
    floorLayer.addChild(board);
  };
  addWallBoard('prop_board_market', 74, 32);       // Market: Price Trend Line Chart (Left of Window)
  addWallBoard('prop_board_volatility', 480, 32);  // Volatility: Volatility Smile Curve (Right of Window)
  addWallBoard('prop_board_compliance', 780, 32);  // Mentor: Regulatory Audit Checklist
  addWallBoard('prop_board_strategy', 688, 352);   // Strategist: Master Decision Matrix on North Divider
  addWallBoard('prop_board_options', 110, 352);    // Options: Kinked Call Payoff on Upper North Divider
  addWallBoard('prop_board_portfolio', 380, 352);  // Portfolio: Asset Allocation on Upper North Divider

  // Small Analytical Wall Panels Flush with Divider Walls
  addWallBoard('prop_panel_telemetry', 72, 140);   // Market West Wall Telemetry
  addWallBoard('prop_board_docs', 342, 140);        // Volatility West Divider Docs
  addWallBoard('prop_panel_telemetry', 72, 410);   // Options West Wall Matrix
  addWallBoard('prop_board_docs', 342, 410);        // Portfolio West Divider Index

  // 2. SPATIAL STATIONS
  const STATIONS = {
    market_agent: {
      type: 'analyst',
      deskPos: { x: 168, y: 175 },
      seatPos: { x: 168, y: 138 },
      standPos: { x: 168, y: 215 },
      doorPos:  { x: 168, y: 305 }
    },
    volatility_agent: {
      type: 'analyst',
      deskPos: { x: 440, y: 175 },
      seatPos: { x: 440, y: 138 },
      standPos: { x: 440, y: 215 },
      doorPos:  { x: 440, y: 305 }
    },
    options_agent: {
      type: 'analyst',
      deskPos: { x: 168, y: 465 },
      seatPos: { x: 168, y: 428 },
      standPos: { x: 168, y: 505 },
      doorPos:  { x: 168, y: 335 }
    },
    portfolio_agent: {
      type: 'analyst',
      deskPos: { x: 440, y: 465 },
      seatPos: { x: 440, y: 428 },
      standPos: { x: 440, y: 505 },
      doorPos:  { x: 440, y: 335 }
    },
    mentor: {
      type: 'mentor',
      deskPos: { x: 780, y: 175 },
      seatPos: { x: 780, y: 138 },
      standPos: { x: 700, y: 210 },
      doorPos:  { x: 608, y: 175 }
    },
    strategist: {
      type: 'strategist',
      deskPos: { x: 688, y: 465 },
      seatPos: { x: 688, y: 420 },
      standPos: { x: 688, y: 520 },
      doorPos:  { x: 608, y: 465 }
    },
    risk_engine: {
      type: 'risk_checkpoint',
      deskPos: { x: 840, y: 390 }, // Illuminated Architectural Checkpoint Gate
      seatPos: null,
      standPos: { x: 840, y: 390 },
      doorPos:  { x: 768, y: 465 }
    },
    execution: {
      type: 'exec_checkpoint',
      deskPos: { x: 840, y: 530 }, // Terminal Workstation
      seatPos: null,
      standPos: { x: 840, y: 530 },
      doorPos:  { x: 768, y: 465 }
    }
  };

  // 3. SEMANTIC CORRIDOR WAYPOINTS & PATHFINDER
  const WAYPOINTS = {
    'CORRIDOR_CROSS':   { x: 584, y: 320 },
    'CORRIDOR_NORTH':   { x: 584, y: 175 },
    'CORRIDOR_SOUTH':   { x: 584, y: 465 }
  };

  function calculatePath(fromId, toId) {
    const fromSt = STATIONS[fromId];
    const toSt = STATIONS[toId];
    if (!fromSt || !toSt) return [toSt ? toSt.standPos : { x: 584, y: 320 }];

    if ((fromId === 'risk_engine' && toId === 'execution') || (fromId === 'execution' && toId === 'risk_engine')) {
      return [fromSt.standPos, toSt.standPos];
    }

    const path = [];
    path.push(fromSt.standPos, fromSt.doorPos);

    if (fromId === 'mentor') {
      path.push(WAYPOINTS['CORRIDOR_NORTH']);
    } else if (fromId === 'strategist' || fromId === 'risk_engine' || fromId === 'execution') {
      path.push(WAYPOINTS['CORRIDOR_SOUTH']);
    } else {
      path.push(WAYPOINTS['CORRIDOR_CROSS']);
    }

    if (toId === 'mentor') {
      path.push(WAYPOINTS['CORRIDOR_NORTH']);
    } else if (toId === 'strategist' || toId === 'risk_engine' || toId === 'execution') {
      path.push(WAYPOINTS['CORRIDOR_SOUTH']);
    } else {
      path.push(WAYPOINTS['CORRIDOR_CROSS']);
    }

    path.push(toSt.doorPos, toSt.standPos);

    const clean = [];
    for (const p of path) {
      if (!clean.length || (clean[clean.length - 1].x !== p.x || clean[clean.length - 1].y !== p.y)) {
        clean.push(p);
      }
    }
    return clean;
  }

  // 4. SOLID ARCHITECTURAL ROOM DIVIDERS & CONTROLLED FURNISHING
  const addProp = (texKey, x, y, anchorY = 1.0, zIndex = null) => {
    const tex = TEXTURES[texKey];
    if (!tex) return null;
    const sprite = new PIXI.Sprite(tex);
    sprite.anchor.set(0.5, anchorY);
    sprite.x = x;
    sprite.y = y;
    sprite.zIndex = (zIndex !== null) ? zIndex : y;
    entityLayer.addChild(sprite);
    return sprite;
  };

  // --- ROOM 1: Market Room (NW: x=48..288, y=48..288) ---
  for (let gy = 96; gy <= 289; gy += 64) addProp('glass_part_v', 288, gy); // East wall
  addProp('glass_part_h', 80, 288);
  addProp('door_frame_h', 168, 288); // South Doorway
  addProp('glass_part_h', 248, 288);
  addProp('prop_cabinet_small', 72, 210); // Filing Credenza Against West Wall
  addProp('prop_plant_small', 72, 80);    // Organic Fanning Palm Plant in Corner

  // --- ROOM 2: Volatility Room (N-Mid: x=320..560, y=48..288) ---
  for (let gy = 96; gy <= 289; gy += 64) addProp('glass_part_v', 320, gy); // West wall
  for (let gy = 96; gy <= 289; gy += 64) addProp('glass_part_v', 560, gy); // East wall
  addProp('glass_part_h', 352, 288);
  addProp('door_frame_h', 440, 288); // South Doorway
  addProp('glass_part_h', 528, 288);
  addProp('prop_cabinet_small', 342, 210); // Filing Credenza Against West Divider
  addProp('prop_plant_small', 342, 80);    // Organic Fanning Palm Plant in Corner

  // --- ROOM 3: Options Room (SW: x=48..288, y=352..592) ---
  for (let gy = 384; gy <= 577; gy += 64) addProp('glass_part_v', 288, gy); // East wall
  addProp('glass_part_h', 80, 352);
  addProp('door_frame_h', 168, 352); // North Doorway
  addProp('glass_part_h', 248, 352);
  addProp('prop_cabinet_small', 72, 475); // Filing Credenza Against West Wall
  addProp('prop_plant_small', 72, 540);   // Organic Fanning Palm Plant in Corner

  // --- ROOM 4: Portfolio Room (S-Mid: x=320..560, y=352..592) ---
  for (let gy = 384; gy <= 577; gy += 64) addProp('glass_part_v', 320, gy); // West wall
  for (let gy = 384; gy <= 577; gy += 64) addProp('glass_part_v', 560, gy); // East wall
  addProp('glass_part_h', 352, 352);
  addProp('door_frame_h', 440, 352); // North Doorway
  addProp('glass_part_h', 528, 352);
  addProp('prop_cabinet_small', 342, 475); // Filing Credenza Against West Divider
  addProp('prop_plant_small', 342, 540);   // Organic Fanning Palm Plant in Corner

  // --- ROOM 5: Compliance Mentor Executive Suite (NE: x=608..912, y=48..288) ---
  addProp('glass_part_v', 608, 96);
  addProp('door_frame_v', 608, 175); // West Doorway
  addProp('glass_part_v', 608, 256);
  for (let gx = 608 + 32; gx < 912; gx += 64) addProp('glass_part_h', gx, 288); // South divider
  addProp('prop_bookshelf', 720, 74, 1.0, 70); // Bookshelf 1
  addProp('prop_bookshelf', 840, 74, 1.0, 70); // Bookshelf 2
  addProp('prop_mentor_credenza', 650, 210);    // Executive Walnut Credenza & Carafe
  addProp('prop_plant_tall', 885, 80);         // Executive Corner Tree

  // --- ROOM 6: Lead Strategist Executive Command Suite (Mid-East: x=608..768, y=352..592) ---
  addProp('glass_part_h', 608 + 32, 352);
  addProp('glass_part_h', 672 + 32, 352);
  addProp('glass_part_v', 608, 384);
  addProp('door_frame_v', 608, 465); // West Doorway
  addProp('glass_part_v', 608, 544);
  for (let gy = 384; gy <= 577; gy += 64) addProp('glass_part_v', 768, gy); // East divider
  addProp('prop_strat_console', 635, 475); // Command Equipment Console
  addProp('prop_plant_tall', 635, 390);    // Suite Palm Tree

  // --- ROOM 7: Technical Operations Room (SE: x=768..912, y=352..592) ---
  addProp('glass_part_h', 768 + 32, 352);
  addProp('glass_part_h', 832 + 32, 352);
  addProp('door_frame_v', 768, 465); // West Doorway
  addProp('station_risk_monitor', 840, 455); // Intermediate Risk Monitor Terminal Console

  // Arrival Foyer Water Cooler (Flush Against North Wall at 580, 52)
  addProp('prop_water_cooler', 580, 52, 1.0, 48);

  // 5. WORKSTATION & CHECKPOINT ENTITIES
  class WorkstationEntity extends PIXI.Container {
    constructor(id, station) {
      super();
      this.id = id;
      this.station = station;
      this.x = station.deskPos.x;
      this.y = station.deskPos.y;
      this.zIndex = station.deskPos.y;
      this.type = station.type;
      this.phase = Math.random() * Math.PI * 2;
      this.screenActive = false;
      this.screenColor = (station.type === 'mentor') ? 0xffb74d : (station.type === 'risk_checkpoint' ? 0x00e5ff : 0x00e5ff);

      let texKey = 'desk_standard';
      if (this.type === 'strategist') texKey = 'desk_senior';
      if (this.type === 'mentor') texKey = 'desk_mentor';
      if (this.type === 'risk_checkpoint') texKey = 'station_risk_engine';
      if (this.type === 'exec_checkpoint') texKey = 'station_execution';

      const tex = TEXTURES[texKey];
      if (tex) {
        this.sprite = new PIXI.Sprite(tex);
        this.sprite.anchor.set(0.5, 1.0);
        this.addChild(this.sprite);
      }

      this.screenGlow = new PIXI.Graphics();
      this.addChild(this.screenGlow);

      if (this.type === 'mentor') {
        this.lampGlow = new PIXI.Graphics();
        this.lampGlow.beginFill(0xffb74d, 0.20);
        this.lampGlow.drawCircle(54, -48, 16);
        this.lampGlow.endFill();
        this.addChild(this.lampGlow);
      }
    }

    setActive(active, color = null) {
      this.screenActive = active;
      if (color) this.screenColor = color;
    }

    update(dt, time) {
      this.screenGlow.clear();
      const baseAlpha = this.screenActive ? 0.45 : 0.10;
      const flicker = Math.sin(time * (this.screenActive ? 0.025 : 0.003) + this.phase) * (this.screenActive ? 0.12 : 0.03);
      const alpha = Math.max(0.04, baseAlpha + flicker);
      const color = this.screenColor;

      this.screenGlow.beginFill(color, alpha);
      if (this.type === 'strategist') {
        this.screenGlow.drawRoundedRect(-48, -76, 96, 28, 3);
      } else if (this.type === 'mentor') {
        this.screenGlow.drawRoundedRect(-36, -64, 72, 22, 3);
      } else if (this.type === 'risk_checkpoint') {
        this.screenGlow.drawRoundedRect(-16, -72, 32, 60, 4);
      } else if (this.type === 'exec_checkpoint') {
        this.screenGlow.drawRoundedRect(-38, -60, 76, 22, 3);
      } else {
        this.screenGlow.drawRoundedRect(-24, -56, 48, 18, 2);
      }
      this.screenGlow.endFill();

      if (this.lampGlow) {
        this.lampGlow.alpha = 0.80 + Math.sin(time * 0.002 + this.phase) * 0.10;
      }
    }
  }

  const workstations = {};
  Object.entries(STATIONS).forEach(([id, st]) => {
    const ws = new WorkstationEntity(id, st);
    entityLayer.addChild(ws);
    workstations[id] = ws;
  });

  // 6. LIVING PHYSICAL AGENTS (0.60 Scale - Exact 29.4% Height Reduction)
  class AgentEntity extends PIXI.Container {
    constructor(id, station) {
      super();
      this.id = id;
      this.station = station;
      this.homePos = station.seatPos || station.standPos;
      this.x = this.homePos.x;
      this.y = this.homePos.y;
      this.zIndex = this.y;

      this.state = 'idle';
      this.idlePhase = Math.random() * Math.PI * 2;
      this.isWalking = false;
      this.walkPath = [];
      this.pathIndex = 0;
      this.walkSpeed = 3.0;
      this.walkTimer = 0;
      this.isCarryingArtifact = false;
      this.onArrivalAction = null;
      this.returnAfterAction = false;

      this.bodyContainer = new PIXI.Container();
      this.addChild(this.bodyContainer);

      const texChar = TEXTURES['char_' + id.replace('_agent', '')];
      if (texChar) {
        this.body = new PIXI.Sprite(texChar);
        this.body.anchor.set(0.5, 160 / 192); // (64, 160)
        this.body.scale.set(0.60);
        this.bodyContainer.addChild(this.body);
      } else {
        this.body = new PIXI.Container();
        this.bodyContainer.addChild(this.body);
      }

      // Compact Monospace Name Tag Positioned Cleanly Above Head
      this.labelContainer = new PIXI.Container();
      this.labelContainer.y = (id === 'strategist') ? -68 : -64;
      this.labelBg = new PIXI.Graphics();
      this.labelText = new PIXI.Text(id.replace('_', ' ').toUpperCase(), {
        fontFamily: 'monospace',
        fontSize: 9,
        fontWeight: 'bold',
        fill: 0xd8e2ed,
        align: 'center'
      });
      this.labelText.anchor.set(0.5, 0.5);
      this.statusDot = new PIXI.Graphics();
      this.updateStatusDot(0x78909c);
      this.labelContainer.addChild(this.labelBg, this.statusDot, this.labelText);
      this.addChild(this.labelContainer);
      this.renderLabelBg();

      // Speech Bubble
      this.bubble = new PIXI.Container();
      this.bubble.x = 14;
      this.bubble.y = -62;
      this.bubble.visible = false;
      this.bubbleBg = new PIXI.Graphics();
      this.bubbleText = new PIXI.Text('', {
        fontFamily: 'sans-serif',
        fontSize: 10,
        fill: 0xffffff,
        wordWrap: true,
        wordWrapWidth: 120
      });
      this.bubbleText.x = 6;
      this.bubbleText.y = 5;
      this.bubble.addChild(this.bubbleBg, this.bubbleText);
      this.addChild(this.bubble);

      // Terminal Badge
      this.terminalBadge = new PIXI.Container();
      this.terminalBadge.y = -84;
      this.terminalBadge.visible = false;
      this.terminalBadgeBg = new PIXI.Graphics();
      this.terminalBadgeText = new PIXI.Text('', {
        fontFamily: 'monospace',
        fontSize: 9,
        fontWeight: 'bold',
        fill: 0xffffff,
        align: 'center'
      });
      this.terminalBadgeText.anchor.set(0.5, 0.5);
      this.terminalBadge.addChild(this.terminalBadgeBg, this.terminalBadgeText);
      this.addChild(this.terminalBadge);

      // Carried Artifact
      this.carriedArtifact = null;
      if (TEXTURES['work_artifact']) {
        this.carriedArtifact = new PIXI.Sprite(TEXTURES['work_artifact']);
        this.carriedArtifact.anchor.set(0.5, 0.5);
        this.carriedArtifact.scale.set(0.50);
        this.carriedArtifact.x = 7;
        this.carriedArtifact.y = -24;
        this.carriedArtifact.visible = false;
        this.bodyContainer.addChild(this.carriedArtifact);
      }

      this.oneShotPerk = 0.0;
    }

    updateStatusDot(color) {
      this.statusDot.clear();
      this.statusDot.beginFill(color);
      this.statusDot.drawCircle(-this.labelText.width / 2 - 5, 0, 2.5);
      this.statusDot.endFill();
    }

    renderLabelBg() {
      const w = this.labelText.width + 16;
      const h = 14;
      this.labelBg.clear();
      this.labelBg.beginFill(0x0d1322, 0.85);
      this.labelBg.lineStyle(1, 0x334460, 0.8);
      this.labelBg.drawRoundedRect(-w / 2, -h / 2, w, h, 3);
      this.labelBg.endFill();
    }

    walkToStation(destStationId, carryArtifact = true, onArrival = null, returnHome = true) {
      const path = calculatePath(this.id, destStationId);
      if (!path || path.length === 0) {
        if (onArrival) onArrival();
        return;
      }

      this.isWalking = true;
      this.walkPath = path;
      this.pathIndex = 0;
      this.isCarryingArtifact = carryArtifact;
      if (this.carriedArtifact) this.carriedArtifact.visible = carryArtifact;
      this.onArrivalAction = onArrival;
      this.returnAfterAction = returnHome;
      this.destStationId = destStationId;
    }

    walkHome() {
      const returnPath = calculatePath(this.destStationId || 'strategist', this.id);
      returnPath.reverse();
      returnPath.push(this.homePos);

      this.isWalking = true;
      this.walkPath = returnPath;
      this.pathIndex = 0;
      this.isCarryingArtifact = false;
      if (this.carriedArtifact) this.carriedArtifact.visible = false;
      this.onArrivalAction = () => {
        if (this.body) this.body.scale.x = 0.60;
      };
      this.returnAfterAction = false;
    }

    setState(stateStr) {
      this.state = stateStr || 'idle';
      const ws = workstations[this.id];

      switch (this.state) {
        case 'working':
        case 'mentor-active':
          this.updateStatusDot(this.id === 'mentor' ? 0xffb74d : 0x00e5ff);
          if (ws) ws.setActive(true, this.id === 'mentor' ? 0xffb74d : 0x00e5ff);
          break;

        case 'alert':
        case 'received':
          this.oneShotPerk = -1.0;
          this.updateStatusDot(0x00e676);
          if (ws) ws.setActive(true, 0x00e676);
          break;

        case 'correction':
          this.oneShotPerk = -0.8;
          this.updateStatusDot(0xffab00);
          if (ws) ws.setActive(true, 0xffab00);
          break;

        case 'waiting':
          this.updateStatusDot(0xffab00);
          if (ws) ws.setActive(false);
          break;

        case 'risk-pass':
          this.oneShotPerk = -0.8;
          this.updateStatusDot(0x00e676);
          if (ws) ws.setActive(true, 0x00e676);
          break;

        case 'risk-fail':
        case 'rejected':
        case 'exec-error':
          this.oneShotPerk = -0.6;
          this.updateStatusDot(0xff1744);
          if (ws) ws.setActive(true, 0xff1744);
          break;

        case 'no-trade':
        case 'idle':
        default:
          this.updateStatusDot(0x78909c);
          if (ws) ws.setActive(false);
          break;
      }
    }

    showBubble(text, type) {
      this.bubbleText.text = text;
      const bounds = this.bubbleText.getLocalBounds();
      let bgColor = 0x111728;
      let borderColor = 0x3d5475;
      if (type === 'st-correction') { bgColor = 0x3d2805; borderColor = 0xffab00; }
      if (type === 'st-error') { bgColor = 0x3d0b0b; borderColor = 0xff1744; }
      
      this.bubbleBg.clear();
      this.bubbleBg.beginFill(bgColor, 0.95);
      this.bubbleBg.lineStyle(1.5, borderColor, 0.9);
      this.bubbleBg.drawRoundedRect(0, 0, bounds.width + 12, bounds.height + 10, 4);
      this.bubbleBg.endFill();

      this.bubble.scale.set(0.85);
      this.bubble.alpha = 0.0;
      this.bubble.visible = true;
    }

    hideBubble() {
      this.bubble.visible = false;
    }

    showTerminalBadge(label, type) {
      const colors = {
        'badge-no-trade':  { bg: 0x37474f, border: 0x78909c },
        'badge-rejected':  { bg: 0xb71c1c, border: 0xff1744 },
        'badge-waiting':   { bg: 0xe65100, border: 0xffab00 },
        'badge-risk-fail': { bg: 0x880e4f, border: 0xff1744 },
        'badge-exec-error':{ bg: 0x4a148c, border: 0xff1744 }
      };
      const scheme = colors[type] || { bg: 0x263238, border: 0x546e7a };

      this.terminalBadgeText.text = label;
      const bounds = this.terminalBadgeText.getLocalBounds();
      this.terminalBadgeBg.clear();
      this.terminalBadgeBg.beginFill(scheme.bg, 0.95);
      this.terminalBadgeBg.lineStyle(1.5, scheme.border, 1.0);
      this.terminalBadgeBg.drawRoundedRect(
        -bounds.width / 2 - 6,
        -bounds.height / 2 - 4,
        bounds.width + 12,
        bounds.height + 8,
        3
      );
      this.terminalBadgeBg.endFill();
      this.terminalBadge.scale.set(0.8);
      this.terminalBadge.alpha = 0.0;
      this.terminalBadge.visible = true;
    }

    clearTerminalBadge() {
      this.terminalBadge.visible = false;
    }

    update(dt, deltaMS, time) {
      this.oneShotPerk += (0.0 - this.oneShotPerk) * 0.22;

      if (this.isWalking && this.walkPath.length > 0) {
        this.walkTimer += deltaMS;
        const targetPoint = this.walkPath[this.pathIndex];
        const dx = targetPoint.x - this.x;
        const dy = targetPoint.y - this.y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (Math.abs(dx) > 1.0 && this.body) {
          this.body.scale.x = (dx > 0) ? 0.60 : -0.60;
          if (this.carriedArtifact) {
            this.carriedArtifact.x = (dx > 0) ? 7 : -7;
          }
        }

        if (dist <= this.walkSpeed) {
          this.x = targetPoint.x;
          this.y = targetPoint.y;
          this.pathIndex++;

          if (this.pathIndex >= this.walkPath.length) {
            this.isWalking = false;
            this.walkPath = [];
            
            if (this.onArrivalAction) {
              const cb = this.onArrivalAction;
              this.onArrivalAction = null;
              cb();
            }

            if (this.returnAfterAction) {
              setTimeout(() => {
                this.walkHome();
              }, 700);
            }
          }
        } else {
          this.x += (dx / dist) * this.walkSpeed;
          this.y += (dy / dist) * this.walkSpeed;
        }

        const stepBob = Math.sin(this.walkTimer * 0.016) * 0.5;
        this.bodyContainer.y = stepBob;
        this.zIndex = this.y;
      } else {
        const breath = Math.sin(time * 0.0012 + this.idlePhase) * 0.12;
        this.bodyContainer.y = breath + this.oneShotPerk;
        this.zIndex = this.y;
      }

      if (this.bubble.visible && this.bubble.scale.x < 1.0) {
        this.bubble.scale.x += (1.0 - this.bubble.scale.x) * 0.25;
        this.bubble.scale.y = this.bubble.scale.x;
        this.bubble.alpha = Math.min(1.0, this.bubble.alpha + 0.25);
      }
      if (this.terminalBadge.visible && this.terminalBadge.scale.x < 1.0) {
        this.terminalBadge.scale.x += (1.0 - this.terminalBadge.scale.x) * 0.25;
        this.terminalBadge.scale.y = this.terminalBadge.scale.x;
        this.terminalBadge.alpha = Math.min(1.0, this.terminalBadge.alpha + 0.25);
      }
    }
  }

  const agents = {};
  Object.entries(STATIONS).forEach(([id, st]) => {
    if (['market_agent', 'volatility_agent', 'options_agent', 'portfolio_agent', 'strategist', 'mentor'].includes(id)) {
      const agent = new AgentEntity(id, st);
      entityLayer.addChild(agent);
      agents[id] = agent;
    }
  });

  // Dedicated Operations Courier
  class OperationsCourier extends AgentEntity {
    constructor() {
      super('courier', {
        deskPos: { x: 584, y: 320 },
        seatPos: { x: 584, y: 320 },
        standPos: { x: 584, y: 320 },
        doorPos:  { x: 584, y: 320 }
      });
      this.visible = false;
    }
  }
  const opsCourier = new OperationsCourier();
  entityLayer.addChild(opsCourier);

  // 7. MASTER TICKER LOOP (60 FPS)
  let totalTime = 0;
  app.ticker.add((dt) => {
    totalTime += app.ticker.deltaMS;
    
    Object.values(workstations).forEach(ws => ws.update(dt, totalTime));
    Object.values(agents).forEach(agent => agent.update(dt, app.ticker.deltaMS, totalTime));
    opsCourier.update(dt, app.ticker.deltaMS, totalTime);

    entityLayer.sortChildren();
  });

  // 8. PUBLIC WORLD API FOR APP.JS
  window.AlphaSwarmWorld = {
    travelArtifact: (fromId, toId, label, onArrival) => {
      if (agents[fromId]) {
        agents[fromId].walkToStation(toId, true, () => {
          if (agents[toId]) {
            agents[toId].setState('alert');
          }
          if (workstations[toId]) {
            workstations[toId].setActive(true, 0x00e5ff);
          }
          if (onArrival) onArrival();
        }, true);
      } else if (fromId === 'risk_engine' || fromId === 'mentor') {
        opsCourier.x = STATIONS[fromId].standPos.x;
        opsCourier.y = STATIONS[fromId].standPos.y;
        opsCourier.visible = true;
        opsCourier.walkToStation(toId, true, () => {
          opsCourier.visible = false;
          if (workstations[toId]) {
            workstations[toId].setActive(true, 0x00e5ff);
          }
          if (onArrival) onArrival();
        }, false);
      } else {
        if (onArrival) onArrival();
      }
    },

    setAgentState: (agentId, state) => {
      if (agents[agentId]) agents[agentId].setState(state);
      if (workstations[agentId]) {
        const active = (state === 'working' || state === 'mentor-active' || state === 'received' || state === 'alert' || state === 'risk-pass');
        const color = (state === 'risk-pass' || state === 'received') ? 0x00e676 : (state === 'correction' ? 0xffab00 : (state === 'risk-fail' || state === 'rejected' ? 0xff1744 : (agentId === 'mentor' ? 0xffb74d : 0x00e5ff)));
        workstations[agentId].setActive(active, color);
      }
    },

    showBubble: (agentId, text, type) => {
      if (agents[agentId]) agents[agentId].showBubble(text, type);
    },

    hideBubble: (agentId) => {
      if (agents[agentId]) agents[agentId].hideBubble();
    },

    hideAllBubbles: () => {
      Object.values(agents).forEach(a => a.hideBubble());
    },

    showTerminalBadge: (agentId, label, type) => {
      if (agents[agentId]) agents[agentId].showTerminalBadge(label, type);
    },

    clearTerminalBadge: (agentId) => {
      if (agents[agentId]) agents[agentId].clearTerminalBadge();
    },

    clearAllTerminalBadges: () => {
      Object.values(agents).forEach(a => a.clearTerminalBadge());
    },

    reset: () => {
      Object.values(agents).forEach(a => {
        a.setState(null);
        a.hideBubble();
        a.clearTerminalBadge();
        a.isWalking = false;
        a.walkPath = [];
        a.x = a.homePos.x;
        a.y = a.homePos.y;
        if (a.body) a.body.scale.x = 0.60;
        if (a.carriedArtifact) a.carriedArtifact.visible = false;
      });
      opsCourier.visible = false;
      Object.values(workstations).forEach(ws => ws.setActive(false));
    }
  };

  console.log("AlphaSwarm Visual Refinement Pass #8 initialized.");
}

window.addEventListener('DOMContentLoaded', () => {
  initRenderer();
});
