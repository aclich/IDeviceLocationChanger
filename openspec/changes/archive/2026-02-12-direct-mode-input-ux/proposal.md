## Why

The direct mode coordinate input UX has two small friction points: (1) the "Go" button's purpose isn't visually obvious as the action for the text input, and (2) users who copy coordinates in `(lat, lng)` parenthesized format (common from Google Maps and other tools) must manually strip parentheses before pasting.

## What Changes

- **Input group layout**: Visually attach the "Go" button to the coordinate input field as an input-group addon, removing the gap so they read as a single control. This makes it immediately clear that "Go" submits the coordinates typed in the input.
- **Parenthesized coordinate parsing**: Extend `parseCoordinates()` to accept `(lat, lng)` format in addition to the existing `lat, lng` format. Parentheses are simply stripped before parsing.

## Capabilities

### New Capabilities

_(none - these are minor enhancements to existing UI)_

### Modified Capabilities

_(no spec-level requirement changes - these are cosmetic/parsing tweaks within existing direct mode behavior)_

## Impact

- `src/components/ControlPanel.jsx` - Update `parseCoordinates()` regex to handle parentheses
- `src/styles/App.css` - Adjust `.coord-input-row` styling to create input-group appearance (remove gap, join border radii)
