/** @type {import('next').NextConfig} */
export default {
  eslint: { ignoreDuringBuilds: true },
  poweredByHeader: false,
  // next ≥ 15.5 有 middleware 时默认只保留请求体前 10MB；150MB 文件 base64 后约 200MB
  experimental: { serverActions: { bodySizeLimit: "2mb" }, middlewareClientMaxBodySize: "210mb" },
};
