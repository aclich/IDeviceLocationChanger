## Context

The status bar (`div.status-bar` in `App.jsx`) currently renders up to 4 conditional `<span>` elements stacked vertically in portrait mode. During route cruise, all 4 lines are active (device, location, cruise info, route info), consuming significant vertical space and reducing the map viewport.

Current structure in `App.jsx:422-443`:
- Span 1: Device name (always)
- Span 2: Coordinates (when location set)
- Span 3: Cruise status — distance, ETA, speed (when cruising)
- Span 4: Route status — segment, remaining km (when route cruising)

Portrait CSS (`App.css:1435`) sets `flex-direction: column` to stack these spans.

## Goals / Non-Goals

**Goals:**
- Reduce status bar to a single line in all viewport sizes
- Show contextually relevant info based on current mode
- Always include device name
- Apply bounce-scroll (ping-pong) CSS animation when content overflows
- No animation when content fits within the container
- Display a contextual emoji prefix that reflects the current mode, speed tier, or climate zone
- Rotate emoji every 30 seconds for variety within the same pool

**Non-Goals:**
- Changing the status bar in landscape/wide layout (though the contextual approach benefits all sizes)
- Adding interactive elements (tooltips, expand/collapse) to the status bar
- External API calls for weather/geo data (climate zone derived from latitude math only)
- Backend changes

## Decisions

### 1. Contextual content selection

Merge all status info into a single string, varying by mode:

| Mode | Content |
|------|---------|
| Idle, no location | `{deviceName}` |
| Idle, with location | `{deviceName} · {lat}, {lng}` |
| Cruising | `{deviceName} · {distance} rem · ETA {eta} · {speed} km/h` |
| Cruising, paused | `{deviceName} · Paused · {distance} rem · ETA {eta} · {speed} km/h` |
| Route cruising | `{deviceName} · Seg {n}/{total} · {routeRemaining} rem · {speed} km/h` |
| Route cruising, paused | `{deviceName} · Route Paused · Seg {n}/{total} · {routeRemaining} rem · {speed} km/h` |
| No device | `No device selected` |

**Rationale:** During cruise/route cruise, coordinates update rapidly and aren't useful to display. Speed, ETA, and segment progress are what matters. Device name is always shown for context since multiple devices may be in use.

Separator: middle dot (`·`) for visual clarity and compactness.

Each line is prefixed with a contextual emoji: `🚲 iPhone 12 Pro · 1.2km rem · ETA 3m · 15.0 km/h`

### 4. Contextual emoji system

A leading emoji is picked from a themed pool based on current mode. Emoji is placed before the text content.

**Speed tier pools (cruising & route cruising):**

| Speed (km/h) | Pool |
|---|---|
| 0–3 | 🐌 🐢 |
| 3–6 | 🚶 🧑‍🦯 🐕‍🦺 |
| 6–12 | 🏃 💨 🐎 |
| 12–25 | 🚲 🛴 🛼 🏇 |
| 25–60 | 🚗 🚕 🚙 🏍️ 🛺 |
| 60–120 | 🏎️ 🚓 🏁 🚑 |
| 120–300 | 🚄 🚅 🚆 🚝 |
| 300–900 | ✈️ 🛩️ 🦅 🪂 |
| 900–2000 | 🚀 🛰️ 💫 ⚡ |
| 2000+ | 🛸 👽 🌌 🪐 |

**Climate zone pools (idle with location, by |latitude|):**

| Zone | |lat| range | Pool |
|---|---|---|
| Polar | > 66 | 🐧 ❄️ 🧊 🦭 🐻‍❄️ ☃️ 🌨️ 🏔️ |
| Cold | 50–66 | 🌲 🦌 🐺 🍂 🍁 🫎 🦫 🌧️ |
| Temperate | 30–50 | 🌸 🌻 🦋 🌳 🍀 🌾 🐝 🌈 |
| Tropical | 0–30 | 🌴 🌺 🦜 🐠 🌊 🥥 🦎 🌅 🐒 🦩 |

**Other mode pools:**

| Mode | Pool |
|---|---|
| Idle (no location) | ☕ 🫖 🍵 🧋 🍹 🎧 📖 🎮 🛋️ 🧩 🎨 🎵 🍰 🍩 |
| Cruise/route paused | 😴 💤 🛌 🧘 🪴 🌙 😪 🥱 ⏸️ |
| No device | 🦐 🦀 🐟 🐡 🦑 🐙 🦞 🦈 🐋 🐬 🐠 🦭 🦪 🐚 |

### 5. Emoji rotation timing

- A 30-second `setInterval` rotates the emoji within the current pool
- On mode change or speed tier boundary crossing, emoji changes immediately (new random pick from new pool)
- Timer resets on mode/tier change to avoid a double-change
- Timer cleared on component unmount

**Implementation:** Utility module `src/utils/statusEmoji.js` exports:
- `getEmojiPool(mode, speed, latitude)` → returns the appropriate emoji array
- Emoji state managed in `App.jsx` via `useState` + `useEffect` with 30s interval
- When pool reference changes (mode/tier change), pick new emoji immediately and restart timer

### 2. Bounce-scroll animation via CSS

Use a CSS `@keyframes` animation with `translateX()` on the inner text element. The animation:
1. Starts at `translateX(0)` — left-aligned
2. Pauses briefly (via keyframe percentage hold)
3. Scrolls to `translateX(containerWidth - textWidth)` — right end visible
4. Pauses briefly
5. Returns to `translateX(0)`

**Structure:**
```
div.status-bar (overflow: hidden, fixed width)
  └─ span.status-bar-text (inline-block, white-space: nowrap)
       └─ animated via translateX when scrollWidth > clientWidth
```

**Rationale for JS-assisted approach:** The scroll distance (`containerWidth - textWidth`) is dynamic and depends on actual rendered text width. Pure CSS can't calculate this. Use a small `useEffect` + `ResizeObserver` to:
1. Measure `scrollWidth` vs `clientWidth` on the inner span
2. If overflowing, set a CSS custom property `--scroll-distance` on the element
3. CSS animation references `var(--scroll-distance)` for the translateX target

This keeps animation in CSS (smooth, GPU-accelerated) while JS only handles measurement.

### 3. Animation timing

- Total cycle: ~8s (adjustable via CSS variable)
- Pause at each end: ~2s (25% of cycle at start, 25% at end)
- Scroll duration: ~2s each direction (25% scrolling left, 25% scrolling right)

Keyframe breakdown:
```
0%    → translateX(0)         /* left-aligned, hold */
25%   → translateX(0)         /* still holding at left */
50%   → translateX(var(--d))  /* scrolled to right end, hold */
75%   → translateX(var(--d))  /* still holding at right */
100%  → translateX(0)         /* back to left */
```

## Risks / Trade-offs

- **[Text flicker on mode change]** → Content string changes when mode changes (idle → cruise). The scroll animation may restart abruptly. Mitigation: Reset animation when content changes by toggling the animation class.
- **[ResizeObserver performance]** → Minimal risk — only observing a single element. Disconnect on unmount.
- **[Very long device names]** → If device name alone overflows, the marquee still works. No truncation needed.
- **[Emoji rendering variance]** → Some emojis render differently across OS versions. All chosen emojis are well-supported on macOS/iOS. Electron's Chromium renderer handles them consistently.
- **[30s timer overhead]** → Negligible. One `setInterval` firing 0.033 Hz. Cleared on unmount.

  