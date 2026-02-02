import { useState, useRef, useEffect } from 'react';

/**
 * Dropdown component for quick access to favorite locations.
 */
export function FavoritesDropdown({
  favorites,
  isLoading,
  onSelect,
  onSaveCurrent,
  onManage,
  canSaveCurrent,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (favorite, index) => {
    onSelect?.(favorite, index);
    setIsOpen(false);
  };

  const handleSaveCurrent = () => {
    onSaveCurrent?.();
    setIsOpen(false);
  };

  return (
    <div className="favorites-dropdown" ref={dropdownRef}>
      <button
        className="favorites-dropdown-toggle"
        onClick={() => setIsOpen(!isOpen)}
        disabled={isLoading}
      >
        <span className="favorites-icon">⭐</span>
        <span>Favorites</span>
        <span className="dropdown-arrow">{isOpen ? '▲' : '▼'}</span>
      </button>

      {isOpen && (
        <div className="favorites-dropdown-menu">
          {/* Quick actions */}
          <div className="favorites-actions">
            <button
              className="favorites-action-btn"
              onClick={handleSaveCurrent}
              disabled={!canSaveCurrent || isLoading}
              title={!canSaveCurrent ? 'Set a location first' : 'Save current location'}
            >
              <span>⭐</span> Save Current
            </button>
            <button
              className="favorites-action-btn"
              onClick={() => {
                onManage?.();
                setIsOpen(false);
              }}
            >
              <span>⚙</span> Manage...
            </button>
          </div>

          {/* Favorites list */}
          <div className="favorites-list">
            {favorites.length === 0 ? (
              <div className="favorites-empty">
                No favorites yet
              </div>
            ) : (
              favorites.map((fav, index) => (
                <button
                  key={index}
                  className="favorites-item"
                  onClick={() => handleSelect(fav, index)}
                >
                  <span className="favorites-item-name">{fav.name}</span>
                  <span className="favorites-item-coords">
                    {fav.latitude.toFixed(4)}, {fav.longitude.toFixed(4)}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
