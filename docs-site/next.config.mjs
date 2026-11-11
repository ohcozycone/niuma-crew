import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

/** @type {import('next').NextConfig} */
const config = {
  output: 'export',
  basePath: process.env.NEXT_PUBLIC_DOCS_BASE_PATH || '',
  reactStrictMode: true,
  trailingSlash: true,
  images: { unoptimized: true },
  turbopack: { root: process.cwd() },
  devIndicators: false,
  agentRules: false,
  experimental: { cpus: 1 },
};

export default withMDX(config);
