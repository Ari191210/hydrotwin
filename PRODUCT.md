# Product

## Register

product

## Users

Competition judges watching a ~3-minute live demo (10 AM deadline build). They
are technical-adjacent evaluators: they reward instant comprehension, physical
credibility, and confident data storytelling. Secondary framing: the interface
roleplays a flood-emergency operations console, so it must read as a tool a
real duty officer could trust, not a slide.

## Product Purpose

HydroTwin turns a physics simulation (Landlab 2D shallow-water flow over real
SRTM terrain) plus live rainfall into evacuation decisions and a 3D visual
story. The demo surface is `outputs/<case>/flood_3d.html` — a self-contained,
offline-capable three.js viewer. Success = a judge understands "rain fell,
water flowed, these zones evacuate, here's why" within 30 seconds, and nothing
on screen undermines the credibility of the physics.

## Brand Personality

Mission-control precision. Dark, exact, calm authority — a NASA/ops-room
register where the data is the hero and the interface recedes. Urgency is
carried by the alert and the red priority vocabulary, never by visual noise.

## Anti-references

- Generic AI-SaaS dashboard: gradient-text hero metrics, purple-blue glow,
  identical card grids, decorative glassmorphism.
- Video-game HUD: neon overload, sci-fi bevels, scanlines, gamer minimap
  chrome.

## Design Principles

1. **The terrain is the interface.** Panels annotate the 3D scene; they never
   compete with it. When in doubt, give pixels back to the world.
2. **Numbers earn trust.** Every stat shown is computed from the simulation
   and traceable to a source line in the panel. No decoration dressed as data.
3. **One urgency channel.** Red belongs to the alert and immediate-priority
   zones only. Everything else stays calm so the red can shout.
4. **Offline is a feature.** Every byte ships in the file. No CDN, no font
   service, no tiles. Degradation paths are visible, honest, and named.
5. **Three-minute legibility.** A first-time viewer must grasp cause (rain),
   effect (water), and consequence (evacuation) without instruction.

## Accessibility & Inclusion

- Contrast: panel text ≥4.5:1 against panel backgrounds (dim text on dark
  surfaces is the known risk — verify, don't eyeball).
- Full keyboard control of the timeline (space, arrows) — already present,
  keep it.
- `prefers-reduced-motion`: disable auto-rotate and the pulsing alert dot;
  timeline scrubbing stays manual.
- Water depth encodes in both color ramp and 3D height, so color-blind
  viewers still read the flood from geometry.
