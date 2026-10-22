/** @type {import('next').NextConfig} */
export default {
  eslint: { ignoreDuringBuilds: true },
  poweredByHeader: false,
  experimental: { serverActions: { bodySizeLimit: "2mb" } },
};
