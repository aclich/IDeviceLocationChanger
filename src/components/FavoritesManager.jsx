import { useState } from 'react';

/**
 * Modal component for managing favorite locations (full CRUD).
 */
export function FavoritesManager({
  isOpen,
  onClose,
  favorites,
  isLoading,
  onUpdate,
  onDelete,
  onImport,
}) {
  const [editingIndex, setEditingIndex] = useState(null);
  const [editingName, setEditingName] = useState('');
  const [importPath, setImportPath] = useState('');
  const [showImport, setShowImport] = useState(false);

  if (!isOpen) return null;

  const handleStartEdit = (index, currentName) => {
    setEditingIndex(index);
    setEditingName(currentName);
  };

  const handleSaveEdit = async () => {
    if (editingIndex !== null && editingName.trim()) {
      await onUpdate?.(editingIndex, editingName.trim());
      setEditingIndex(null);
      setEditingName('');
    }
  };

  const handleCancelEdit = () => {
    setEditingIndex(null);
    setEditingName('');
  };

  const handleDelete = async (index) => {
    if (window.confirm('Are you sure you want to delete this favorite?')) {
      await onDelete?.(index);
    }
  };

  const handleImport = async () => {
    if (importPath.trim()) {
      const result = await onImport?.(importPath.trim());
      if (result?.success) {
        setImportPath('');
        setShowImport(false);
        alert(`Successfully imported ${result.imported} favorite(s)`);
      }
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleSaveEdit();
    } else if (e.key === 'Escape') {
      handleCancelEdit();
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content favorites-manager" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Manage Favorites</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          {/* Import section */}
          {showImport ? (
            <div className="import-section">
              <div className="import-row">
                <input
                  type="text"
                  className="import-input"
                  placeholder="Enter file path (e.g., ~/favorites.txt)"
                  value={importPath}
                  onChange={(e) => setImportPath(e.target.value)}
                />
                <button
                  className="btn btn-primary btn-sm"
                  onClick={handleImport}
                  disabled={!importPath.trim() || isLoading}
                >
                  Import
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setShowImport(false)}
                >
                  Cancel
                </button>
              </div>
              <p className="import-hint">
                Format: latitude,longitude,name (one per line)
              </p>
            </div>
          ) : (
            <button
              className="btn btn-secondary btn-sm import-toggle"
              onClick={() => setShowImport(true)}
            >
              Import from file...
            </button>
          )}

          {/* Favorites list */}
          <div className="favorites-manager-list">
            {favorites.length === 0 ? (
              <div className="favorites-empty">
                <p>No favorites saved yet.</p>
                <p className="hint">Click "Save Current" in the dropdown to add locations.</p>
              </div>
            ) : (
              favorites.map((fav, index) => (
                <div key={index} className="favorites-manager-item">
                  {editingIndex === index ? (
                    <div className="favorites-edit-row">
                      <input
                        type="text"
                        className="favorites-edit-input"
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        onKeyDown={handleKeyDown}
                        autoFocus
                      />
                      <button
                        className="btn-icon"
                        onClick={handleSaveEdit}
                        title="Save"
                      >
                        ✓
                      </button>
                      <button
                        className="btn-icon"
                        onClick={handleCancelEdit}
                        title="Cancel"
                      >
                        ✕
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="favorites-item-info">
                        <span className="favorites-item-name">{fav.name}</span>
                        <span className="favorites-item-coords">
                          {fav.latitude.toFixed(6)}, {fav.longitude.toFixed(6)}
                        </span>
                      </div>
                      <div className="favorites-item-actions">
                        <button
                          className="btn-icon"
                          onClick={() => handleStartEdit(index, fav.name)}
                          title="Rename"
                          disabled={isLoading}
                        >
                          ✏️
                        </button>
                        <button
                          className="btn-icon btn-danger"
                          onClick={() => handleDelete(index)}
                          title="Delete"
                          disabled={isLoading}
                        >
                          🗑️
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        <div className="modal-footer">
          <span className="favorites-count">
            {favorites.length} favorite{favorites.length !== 1 ? 's' : ''}
          </span>
          <button className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
