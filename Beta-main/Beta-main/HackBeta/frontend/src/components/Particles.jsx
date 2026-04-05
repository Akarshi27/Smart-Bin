import React from 'react';

const Particles = () => {
  // Generate random particles for the background
  const particles = Array.from({ length: 15 }).map((_, i) => ({
    id: i,
    size: Math.random() * 6 + 2,
    left: Math.random() * 100,
    top: Math.random() * 100,
    animationDuration: Math.random() * 10 + 10,
    animationDelay: Math.random() * 5
  }));

  return (
    <div className="particles-container" style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 0, overflow: 'hidden' }}>
      {particles.map(p => (
        <div 
          key={p.id} 
          className="particle"
          style={{
            position: 'absolute',
            backgroundColor: 'rgba(16, 185, 129, 0.3)',
            borderRadius: '50%',
            width: `${p.size}px`,
            height: `${p.size}px`,
            left: `${p.left}%`,
            top: `${p.top}%`,
            animationDuration: `${p.animationDuration}s`,
            animationDelay: `${p.animationDelay}s`
          }}
        />
      ))}
    </div>
  );
};

export default Particles;
