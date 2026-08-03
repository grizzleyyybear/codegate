import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Codegate",
  description: "Governance layer for AI coding agents",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
