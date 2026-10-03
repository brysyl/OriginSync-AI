import type { Metadata, Viewport } from "next";
import Script from "next/script";
import "./globals.css";

export const metadata: Metadata = {
  title: "OriginSync | Trade Control Room",
  description: "Cross-border trade compliance and settlement telemetry.",
  manifest: "/manifest.json",
};

export const viewport: Viewport = {
  themeColor: "#080d13",
  colorScheme: "dark",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      {process.env.NEXT_PUBLIC_RUNTIME_CONFIG === "true" && (
        <head>
          <Script src="/config.js" strategy="beforeInteractive" />
        </head>
      )}
      <body>{children}</body>
    </html>
  );
}
