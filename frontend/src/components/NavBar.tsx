'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function Navbar() {
  const pathname = usePathname();

  const links = [
    { href: '/live', label: 'Live', isLive: true },
    { href: '/predict', label: 'Predict' },
    { href: '/batch', label: 'Batch' },
    { href: '/monitoring', label: 'Monitoring' },
  ];

  return (
    <nav className="navbar">
      <Link href="/" className="navbar-logo">
        <div className="navbar-logo-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="#2d5be3" xmlns="http://www.w3.org/2000/svg">
            <path d="M13 2L4.5 13.5H11L10 22L20.5 10H14L13 2Z"/>
          </svg>
        </div>
        <span className="navbar-logo-text">
          Fraud<span>Guard</span>
        </span>
      </Link>

      <div className="navbar-nav">
        {links.map(({ href, label, isLive }) => {
          const isActive = pathname === href || (href !== '/' && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={`nav-link ${isLive ? 'live-link' : ''} ${isActive ? 'active' : ''}`}
            >
              {isLive && <span className="nav-dot" />}
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}