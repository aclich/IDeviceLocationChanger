## 1. Contextual Status Bar Content

- [x] 1.1 Refactor status bar JSX in `App.jsx` — replace multiple conditional `<span>` elements with a single contextual text string computed from current mode (idle/cruising/route cruising/paused states). Use middle dot `·` separator. Always include device name. Prefix with emoji.
- [x] 1.2 Remove the portrait-mode multi-line stacking CSS (`flex-direction: column` in the `@media` query at `App.css:1435`) and ensure single-line layout at all viewport sizes.

## 2. Contextual Emoji System

- [x] 2.1 Create `src/utils/statusEmoji.js` — define emoji pools: speed tiers (10 tiers from 🐌 to 🛸), climate zones (4 latitude bands), idle, paused, and no-device (seafood) pools. Export `getEmojiPool(mode, speed, latitude)` function.
- [x] 2.2 Add emoji state management in `App.jsx` — `useState` for current emoji, `useEffect` with 30-second `setInterval` for rotation within the same pool. On mode/tier change, pick new emoji immediately and restart timer. Clean up timer on unmount.

## 3. Bounce-Scroll Marquee Animation

- [x] 3.1 Add CSS `@keyframes bounce-scroll` animation with ping-pong timing (pause-at-left → scroll-left → pause-at-right → scroll-right → repeat) using `translateX(var(--scroll-distance))`.
- [x] 3.2 Add JS measurement logic — use `useEffect` + `ResizeObserver` to detect when inner text `scrollWidth` exceeds container `clientWidth`, set `--scroll-distance` CSS custom property, and toggle animation class. Reset animation when content changes.

## 4. Cleanup and Polish

- [x] 4.1 Update status bar CSS to use `overflow: hidden` on the container, `white-space: nowrap` and `display: inline-block` on the inner text element. Remove obsolete portrait-mode status bar span styles.
- [x] 4.2 Verify in both portrait and landscape viewports — animation only triggers on overflow, no animation when content fits. Emoji displays correctly and rotates every 30s.
