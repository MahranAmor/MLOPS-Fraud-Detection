import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import '../styles/globals.css';
import Navbar from '../components/NavBar';
import AnimatedBackground from '../components/AnimatedBackground';

export const metadata: Metadata = {
  title: 'FraudGuard ',
  description: 'Real-time credit card fraud detection powered by machine learning.',
  icons: {
    icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%232d5be3"><path d="M13 2L4.5 13.5H11L10 22L20.5 10H14L13 2Z"/></svg>',
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AnimatedBackground />
        <div className="page-wrapper">
          <Navbar />
          <main className="main-content">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}