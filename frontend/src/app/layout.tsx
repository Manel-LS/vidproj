import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

// Self-hosted at build time: no third-party request at runtime, no flash of
// unstyled text. The CSS variable is what `tailwind.config.ts` points `font-sans` at.
const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: {
    default: "Reelcraft — short-form video from your photos",
    template: "%s · Reelcraft",
  },
  description:
    "Turn product photos into TikTok, Reels and Shorts videos: animated scenes, transitions, captions, music and voice-over, rendered to MP4.",
  applicationName: "Reelcraft",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: "#090a0e",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body className="min-h-screen bg-canvas antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-accent focus:px-4 focus:py-2 focus:text-white"
        >
          Skip to content
        </a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
