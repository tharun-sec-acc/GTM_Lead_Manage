/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const backendUrl = process.env.INTERNAL_API_URL || "http://api:8000";
    return [
      {
        source: "/auth/:path*",
        destination: `${backendUrl}/auth/:path*`,
      },
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: "/public/:path*",
        destination: `${backendUrl}/public/:path*`,
      },
      {
        source: "/leads/:path*",
        destination: `${backendUrl}/leads/:path*`,
      },
      {
        source: "/campaigns/:path*",
        destination: `${backendUrl}/campaigns/:path*`,
      },
      {
        source: "/products/:path*",
        destination: `${backendUrl}/products/:path*`,
      },
      {
        source: "/zoho/:path*",
        destination: `${backendUrl}/zoho/:path*`,
      },
      {
        source: "/google/:path*",
        destination: `${backendUrl}/google/:path*`,
      },
      {
        source: "/microsoft/:path*",
        destination: `${backendUrl}/microsoft/:path*`,
      },
    ];
  },
};

export default nextConfig;
