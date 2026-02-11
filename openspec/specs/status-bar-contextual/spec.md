### Requirement: Status bar displays contextual single-line content
The status bar SHALL render a single line of text whose content varies based on the current application mode. The device name SHALL always be included when a device is selected.

#### Scenario: No device selected
- **WHEN** no device is selected
- **THEN** the status bar SHALL display "{emoji} No device selected" where emoji is randomly picked from the seafood pool (🦐🦀🐟🐡🦑🐙🦞🦈🐋🐬🐠🦭🦪🐚)

#### Scenario: Device selected, no location set
- **WHEN** a device is selected AND no location is set AND no cruise is active
- **THEN** the status bar SHALL display "{emoji} {deviceName}" where emoji is from the idle pool (☕🫖🍵🧋🍹🎧📖🎮🛋️🧩🎨🎵🍰🍩)

#### Scenario: Idle with location
- **WHEN** a device is selected AND a location is set AND no cruise is active
- **THEN** the status bar SHALL display "{emoji} {deviceName} · {latitude}, {longitude}" where coordinates are formatted to 6 decimal places and emoji is from the climate-zone pool determined by |latitude| (polar >66: 🐧❄️🧊🦭🐻‍❄️☃️🌨️🏔️, cold 50-66: 🌲🦌🐺🍂🍁🫎🦫🌧️, temperate 30-50: 🌸🌻🦋🌳🍀🌾🐝🌈, tropical 0-30: 🌴🌺🦜🐠🌊🥥🦎🌅🐒🦩)

#### Scenario: Cruising active
- **WHEN** cruise mode is active AND not paused
- **THEN** the status bar SHALL display "{emoji} {deviceName} · {distance} rem · ETA {eta} · {speed} km/h" where emoji is from the speed tier pool matching current speed

#### Scenario: Cruising paused
- **WHEN** cruise mode is active AND paused
- **THEN** the status bar SHALL display "{emoji} {deviceName} · Paused · {distance} rem · ETA {eta} · {speed} km/h" where emoji is from the paused pool (😴💤🛌🧘🪴🌙😪🥱⏸️)

#### Scenario: Route cruising active
- **WHEN** route cruise mode is active AND not paused
- **THEN** the status bar SHALL display "{emoji} {deviceName} · Seg {current}/{total} · {remainingDistance} rem · {speed} km/h" where emoji is from the speed tier pool matching current speed

#### Scenario: Route cruising paused
- **WHEN** route cruise mode is active AND paused
- **THEN** the status bar SHALL display "{emoji} {deviceName} · Route Paused · Seg {current}/{total} · {remainingDistance} rem · {speed} km/h" where emoji is from the paused pool (😴💤🛌🧘🪴🌙😪🥱⏸️)

### Requirement: Status bar displays contextual emoji prefix
The status bar SHALL display a leading emoji before the text content. The emoji SHALL be randomly selected from a themed pool determined by the current mode, speed tier, or latitude-based climate zone.

#### Scenario: Speed tier emoji selection during cruising
- **WHEN** cruise or route cruise is active and not paused
- **THEN** the emoji SHALL be selected from the speed tier pool matching the current speed (0-3 km/h: 🐌🐢, 3-6: 🚶🧑‍🦯🐕‍🦺, 6-12: 🏃💨🐎, 12-25: 🚲🛴🛼🏇, 25-60: 🚗🚕🚙🏍️🛺, 60-120: 🏎️🚓🏁🚑, 120-300: 🚄🚅🚆🚝, 300-900: ✈️🛩️🦅🪂, 900-2000: 🚀🛰️💫⚡, 2000+: 🛸👽🌌🪐)

#### Scenario: Climate zone emoji for idle with location
- **WHEN** idle with location set
- **THEN** the emoji SHALL be selected from the climate zone pool determined by |latitude| (polar >66, cold 50-66, temperate 30-50, tropical 0-30)

#### Scenario: Emoji rotates every 30 seconds
- **WHEN** the current mode and pool have not changed for 30 seconds
- **THEN** a new random emoji SHALL be picked from the same pool

#### Scenario: Emoji changes immediately on mode or tier transition
- **WHEN** the mode changes (e.g., idle to cruising) OR the speed crosses a tier boundary
- **THEN** a new emoji SHALL be picked immediately from the new pool and the 30-second rotation timer SHALL reset

### Requirement: Status bar applies bounce-scroll animation on overflow
The status bar SHALL apply a ping-pong (bounce-scroll) CSS animation when the text content overflows the visible container width. The animation SHALL NOT be applied when content fits within the container.

#### Scenario: Content fits within container
- **WHEN** the status bar text width is less than or equal to the container width
- **THEN** no scroll animation SHALL be applied and text SHALL be left-aligned

#### Scenario: Content overflows container
- **WHEN** the status bar text width exceeds the container width
- **THEN** a bounce-scroll animation SHALL activate that:
  1. Starts left-aligned with a pause
  2. Scrolls leftward until the right end of text is visible, then pauses
  3. Scrolls rightward back to the left-aligned position, then pauses
  4. Repeats continuously

#### Scenario: Content changes reset animation
- **WHEN** the status bar text content changes (e.g., mode transition from idle to cruising)
- **THEN** the animation SHALL reset and re-evaluate whether overflow scrolling is needed

### Requirement: Status bar maintains single-line layout in all viewport sizes
The status bar SHALL always render as a single horizontal line regardless of viewport width. The previous multi-line stacking behavior in portrait/narrow viewports SHALL be removed.

#### Scenario: Portrait viewport
- **WHEN** the viewport is narrow (portrait mode)
- **THEN** the status bar SHALL remain a single line with overflow handled by bounce-scroll animation

#### Scenario: Landscape viewport
- **WHEN** the viewport is wide (landscape mode)
- **THEN** the status bar SHALL display as a single line, same as portrait
