'use client';

import { useEffect, useRef } from 'react';

export default function AnimatedBackground() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    container.innerHTML = '';

    const lines = [
      { left: 5,  height: 25, delay: 0,   duration: 7  },
      { left: 9,  height: 40, delay: 1.5, duration: 9  },
      { left: 14, height: 55, delay: 0.8, duration: 11 },
      { left: 18, height: 35, delay: 3,   duration: 8  },
      { left: 23, height: 65, delay: 0.3, duration: 13 },
      { left: 27, height: 45, delay: 2.2, duration: 10 },
      { left: 32, height: 30, delay: 4,   duration: 7.5},
      { left: 36, height: 70, delay: 1,   duration: 14 },
      { left: 41, height: 50, delay: 2.8, duration: 9.5},
      { left: 45, height: 40, delay: 0.5, duration: 11 },
      { left: 50, height: 60, delay: 3.5, duration: 12 },
      { left: 54, height: 28, delay: 1.8, duration: 8  },
      { left: 58, height: 45, delay: 0.2, duration: 10 },
      { left: 63, height: 55, delay: 2.5, duration: 13 },
      { left: 67, height: 35, delay: 4.2, duration: 9  },
      { left: 72, height: 48, delay: 1.2, duration: 11 },
      { left: 76, height: 62, delay: 3.8, duration: 15 },
      { left: 81, height: 32, delay: 0.7, duration: 8.5},
      { left: 85, height: 50, delay: 2,   duration: 10 },
      { left: 90, height: 42, delay: 4.5, duration: 12 },
    ];

    lines.forEach((line) => {
      const el = document.createElement('div');
      el.className = 'rain-line';
      el.style.cssText = `
        left: ${line.left}%;
        height: ${line.height}vh;
        animation-delay: ${line.delay}s;
        animation-duration: ${line.duration}s;
      `;
      container.appendChild(el);
    });
  }, []);

  return (
    <div className="app-bg">
      <div className="rain-container" ref={containerRef} />
    </div>
  );
}