// Emoji pools by mode
const POOLS = {
  idle: ['☕', '🫖', '🍵', '🧋', '🍹', '🎧', '📖', '🎮', '🛋️', '🧩', '🎨', '🎵', '🍰', '🍩'],
  paused: ['😴', '💤', '🛌', '🧘', '🪴', '🌙', '😪', '🥱', '⏸️'],
  noDevice: ['🦐', '🦀', '🐟', '🐡', '🦑', '🐙', '🦞', '🦈', '🐋', '🐬', '🐠', '🦭', '🦪', '🐚'],
};

// Speed tiers: [maxSpeed, emojiPool]
// Checked in order — first match wins
const SPEED_TIERS = [
  [3, ['🐌', '🐢']],
  [6, ['🚶', '🧑‍🦯', '🐕‍🦺']],
  [12, ['🏃', '💨', '🐎']],
  [25, ['🚲', '🛴', '🛼', '🏇']],
  [60, ['🚗', '🚕', '🚙', '🏍️', '🛺']],
  [120, ['🏎️', '🚓', '🏁', '🚑']],
  [300, ['🚄', '🚅', '🚆', '🚝']],
  [900, ['✈️', '🛩️', '🦅', '🪂']],
  [2000, ['🚀', '🛰️', '💫', '⚡']],
  [Infinity, ['🛸', '👽', '🌌', '🪐']],
];

// Climate zones by |latitude|: [maxLat, emojiPool]
// Checked in order — first match wins
const CLIMATE_ZONES = [
  [30, ['🌴', '🌺', '🦜', '🐠', '🌊', '🥥', '🦎', '🌅', '🐒', '🦩']],
  [50, ['🌸', '🌻', '🦋', '🌳', '🍀', '🌾', '🐝', '🌈']],
  [66, ['🌲', '🦌', '🐺', '🍂', '🍁', '🫎', '🦫', '🌧️']],
  [Infinity, ['🐧', '❄️', '🧊', '🦭', '🐻‍❄️', '☃️', '🌨️', '🏔️']],
];

function getSpeedPool(speed) {
  for (const [max, pool] of SPEED_TIERS) {
    if (speed <= max) return pool;
  }
  return SPEED_TIERS[SPEED_TIERS.length - 1][1];
}

function getClimatePool(latitude) {
  const absLat = Math.abs(latitude);
  for (const [max, pool] of CLIMATE_ZONES) {
    if (absLat <= max) return pool;
  }
  return CLIMATE_ZONES[CLIMATE_ZONES.length - 1][1];
}

/**
 * Get the emoji pool for the current status bar mode.
 *
 * @param {'noDevice'|'idle'|'idleWithLocation'|'cruising'|'paused'|'routeCruising'|'routePaused'} mode
 * @param {number} speed - Current speed in km/h (used for cruising/routeCruising)
 * @param {number} latitude - Current latitude (used for idleWithLocation)
 * @returns {string[]} Array of emoji candidates
 */
export function getEmojiPool(mode, speed = 0, latitude = 0) {
  switch (mode) {
    case 'noDevice':
      return POOLS.noDevice;
    case 'idle':
      return POOLS.idle;
    case 'idleWithLocation':
      return getClimatePool(latitude);
    case 'cruising':
    case 'routeCruising':
      return getSpeedPool(speed);
    case 'paused':
    case 'routePaused':
      return POOLS.paused;
    default:
      return POOLS.idle;
  }
}

/**
 * Pick a random emoji from the given pool.
 */
export function pickEmoji(pool) {
  return pool[Math.floor(Math.random() * pool.length)];
}
