import type { Metadata } from "next";
import "./globals.css";
import NavBar from "./components/NavBar";

export const metadata: Metadata = {
  title: "Stock Radar — Multi-AI Agent Dashboard",
  description: "10x stock discovery powered by multi-AI scout system",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
        {/* Theme restoration — runs synchronously BEFORE React hydration so the
            theme persists across full-page navigations (e.g. <a href> links)
            and never flashes the wrong palette. Reads `sr-theme` from
            localStorage and sets data-theme on <html> immediately. */}
        <script dangerouslySetInnerHTML={{ __html: `(function(){try{var t=localStorage.getItem('sr-theme');if(t==='light')document.documentElement.setAttribute('data-theme','light');}catch(e){}})();` }} />
      </head>
      <body className="antialiased" suppressHydrationWarning style={{ display: "flex", flexDirection: "column", minHeight: "100vh", margin: 0 }}>
        <NavBar />
        {/* Page area takes the remaining viewport height. Pages that want a
            single-viewport layout (e.g. Ask AI with sticky input) can use
            min-h-0 + flex children instead of min-h-screen — which previously
            added 100vh on top of the navbar's ~60px and forced scroll. */}
        <div style={{ flex: "1 1 auto", display: "flex", flexDirection: "column", minHeight: 0 }}>
          {children}
        </div>
      </body>
    </html>
  );
}
