import type { Metadata, Viewport } from "next";
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
      <body>{children}</body>
    </html>
  );
}
