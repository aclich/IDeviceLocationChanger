import { useRef, useState, useCallback, useEffect } from 'react';

export function Joystick({ onMove, onRelease, size = 150 }) {
  const containerRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });

  const maxRadius = (size / 2) - 20;
  const knobSize = 30;
  const center = size / 2;

  const calculateOffset = useCallback((clientX, clientY) => {
    if (!containerRef.current) return { dx: 0, dy: 0 };

    const rect = containerRef.current.getBoundingClientRect();
    let dx = clientX - rect.left - center;
    let dy = clientY - rect.top - center;

    // Constrain to circle
    const distance = Math.sqrt(dx * dx + dy * dy);
    if (distance > maxRadius) {
      const scale = maxRadius / distance;
      dx *= scale;
      dy *= scale;
    }

    return { dx, dy };
  }, [center, maxRadius]);

  const handleStart = useCallback((clientX, clientY) => {
    setIsDragging(true);
    const { dx, dy } = calculateOffset(clientX, clientY);
    setPosition({ x: dx, y: dy });
    onMove?.(dx, dy, maxRadius);
  }, [calculateOffset, maxRadius, onMove]);

  const handleMove = useCallback((clientX, clientY) => {
    if (!isDragging) return;
    const { dx, dy } = calculateOffset(clientX, clientY);
    setPosition({ x: dx, y: dy });
    onMove?.(dx, dy, maxRadius);
  }, [isDragging, calculateOffset, maxRadius, onMove]);

  const handleEnd = useCallback(() => {
    setIsDragging(false);
    setPosition({ x: 0, y: 0 });
    onRelease?.();
  }, [onRelease]);

  // Mouse events
  const onMouseDown = (e) => {
    e.preventDefault();
    handleStart(e.clientX, e.clientY);
  };

  useEffect(() => {
    if (!isDragging) return;

    const onMouseMove = (e) => handleMove(e.clientX, e.clientY);
    const onMouseUp = () => handleEnd();

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);

    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [isDragging, handleMove, handleEnd]);

  // Touch events
  const onTouchStart = (e) => {
    e.preventDefault();
    const touch = e.touches[0];
    handleStart(touch.clientX, touch.clientY);
  };

  const onTouchMove = (e) => {
    e.preventDefault();
    const touch = e.touches[0];
    handleMove(touch.clientX, touch.clientY);
  };

  const onTouchEnd = (e) => {
    e.preventDefault();
    handleEnd();
  };

  // Direction labels
  const labels = [
    { label: 'N', x: center, y: 10 },
    { label: 'E', x: size - 10, y: center },
    { label: 'S', x: center, y: size - 10 },
    { label: 'W', x: 10, y: center },
  ];

  return (
    <div
      ref={containerRef}
      className="joystick"
      style={{ width: size, height: size }}
      onMouseDown={onMouseDown}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
    >
      {/* Background circle */}
      <div
        className="joystick-base"
        style={{
          width: size - 20,
          height: size - 20,
          left: 10,
          top: 10,
        }}
      />

      {/* Direction labels */}
      {labels.map(({ label, x, y }) => (
        <span
          key={label}
          className="joystick-label"
          style={{
            left: x,
            top: y,
            transform: 'translate(-50%, -50%)',
          }}
        >
          {label}
        </span>
      ))}

      {/* Knob */}
      <div
        className="joystick-knob"
        style={{
          width: knobSize,
          height: knobSize,
          left: center + position.x - knobSize / 2,
          top: center + position.y - knobSize / 2,
        }}
      />
    </div>
  );
}
