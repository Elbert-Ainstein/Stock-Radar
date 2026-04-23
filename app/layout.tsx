import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Stock Radar — Multi-AI Agent Dashboard",
  description: "10x stock discovery powered by multi-AI scout system",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Inline script runs synchronously before paint — prevents flash */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{if(localStorage.getItem('sr-theme')==='light')document.documentElement.setAttribute('data-theme','light')}catch(e){}`,
          }}
        />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
      </head>
      <body className="antialiased">{children}</body>
    </html>
  );
}
