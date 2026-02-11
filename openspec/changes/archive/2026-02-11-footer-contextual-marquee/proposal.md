## Why

In portrait/narrow viewport, the status bar stacks up to 4 lines (device name, coordinates, cruise info, route cruise info), consuming ~80px+ of vertical space. This crowds the map and degrades UX, especially during route cruise mode when all 4 lines are active.

## What Changes

- **Contextual single-line status bar**: Merge all status info into a single line that changes content based on current mode (idle, cruising, route cruising). Device name always included.
- **Bounce-scroll marquee for overflow**: When the single line overflows its container, apply a CSS ping-pong animation that scrolls left-to-right, then right-to-left, pausing at each end. No animation when content fits.
- **Remove multi-line stacking in portrait**: The `flex-direction: column` layout for narrow viewports is replaced by the single-line contextual approach.
- **Contextual emoji**: Each mode displays a leading emoji picked randomly from a themed pool. Speed tiers map to progressively faster vehicle/creature emojis. Location mode uses latitude-band climate-zone emojis. Idle/paused/no-device each have themed pools (chill, sleep, seafood). Emoji rotates every 30 seconds within the same pool and changes immediately on mode/tier transitions.

## Capabilities

### New Capabilities
- `status-bar-contextual`: Contextual status bar that condenses device, location, cruise, and route cruise info into a single adaptive line with bounce-scroll overflow animation and contextual emoji indicators.

### Modified Capabilities

## Impact

- `src/App.jsx`: Status bar JSX restructured from multiple conditional `<span>` elements to single contextual line with emoji prefix
- `src/utils/statusEmoji.js`: New utility — emoji pool definitions, speed tier mapping, latitude-band climate lookup, random picker with 30s rotation timer
- `src/styles/App.css`: New bounce-scroll keyframe animation, status bar layout changes, removal of portrait multi-line stacking
- No backend changes
- No API changes
- No new dependencies
