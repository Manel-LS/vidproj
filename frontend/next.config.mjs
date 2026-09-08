/** @type {import('next').NextConfig} */
const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  // The dev server blocks its own resources when reached from a host it does not
  // recognise, which silently prevents hydration. Both loopback spellings are the
  // ones people actually type.
  allowedDevOrigins: ["localhost", "127.0.0.1", "[::1]"],
  images: {
    // Media is served by the backend (dev) or object storage (production).
    remotePatterns: [
      { protocol: "http", hostname: "localhost" },
      { protocol: "http", hostname: "127.0.0.1" },
      { protocol: "https", hostname: "**" },
    ],
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
  env: { NEXT_PUBLIC_API_URL: apiUrl },
};

export default nextConfig;
