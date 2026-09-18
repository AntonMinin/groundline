import fs from 'node:fs'
import path from 'node:path'
import sharp from 'sharp'

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#f3f2f2"/>
  <rect x="0" y="0" width="1200" height="8" fill="#0fbe6e"/>
  <g transform="translate(80, 96)">
    <path d="M0 0h48l24 24v84H0z" fill="none" stroke="#201e1d" stroke-width="6"/>
    <line x1="18" y1="46" x2="54" y2="46" stroke="#201e1d" stroke-width="6"/>
    <line x1="18" y1="66" x2="54" y2="66" stroke="#201e1d" stroke-width="6"/>
    <line x1="18" y1="86" x2="46" y2="86" stroke="#0fbe6e" stroke-width="6"/>
  </g>
  <text x="180" y="150" font-family="Archivo, Helvetica, Arial, sans-serif" font-size="52" font-weight="800" fill="#201e1d">Groundline</text>
  <text x="80" y="310" font-family="Archivo, Helvetica, Arial, sans-serif" font-size="62" font-weight="800" fill="#201e1d">Answers from your documents,</text>
  <text x="80" y="386" font-family="Archivo, Helvetica, Arial, sans-serif" font-size="62" font-weight="800" fill="#201e1d">never paid for twice</text>
  <text x="80" y="460" font-family="Archivo, Helvetica, Arial, sans-serif" font-size="30" fill="#5c5a58">Semantic answer cache · hybrid search · cited sources</text>
  <g font-family="Archivo, Helvetica, Arial, sans-serif">
    <text x="80" y="556" font-size="40" font-weight="800" fill="#0fbe6e">439 ms</text>
    <text x="80" y="590" font-size="22" fill="#5c5a58">answer from cache</text>
    <text x="360" y="556" font-size="40" font-weight="800" fill="#0fbe6e">0 tokens</text>
    <text x="360" y="590" font-size="22" fill="#5c5a58">spent on a cache hit</text>
    <text x="660" y="556" font-size="40" font-weight="800" fill="#0fbe6e">7 steps</text>
    <text x="660" y="590" font-size="22" fill="#5c5a58">each one visible</text>
  </g>
</svg>`

const out = path.join(process.cwd(), 'public', 'og.png')
await sharp(Buffer.from(svg)).png().toFile(out)
console.log(`wrote ${out} (${(fs.statSync(out).size / 1024).toFixed(0)} KB)`)
