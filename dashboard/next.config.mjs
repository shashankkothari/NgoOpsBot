/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [
      // Telegram CDN — user profile photos fetched via bot API
      { protocol: "https", hostname: "t.me" },
      { protocol: "https", hostname: "*.t.me" },
      // Telegram file storage for bot-served images
      { protocol: "https", hostname: "api.telegram.org" },
    ],
  },
  experimental: {
    serverActions: {
      allowedOrigins: ["localhost:3000"],
    },
  },
};

export default nextConfig;
