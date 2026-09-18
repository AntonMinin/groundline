import { defineConfig } from 'astro/config'

export default defineConfig({
  site: process.env.SITE_URL || 'https://groundline.antonmb.com',
  output: 'static',
  trailingSlash: 'never',
  build: { inlineStylesheets: 'auto' },
  compressHTML: true,
})
