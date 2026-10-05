import { cp, mkdir, copyFile, readdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
const root = fileURLToPath(new URL('../', import.meta.url))
const target = `${root}/public/ocr`
await mkdir(`${target}/core`, { recursive: true })
await mkdir(`${target}/lang`, { recursive: true })
await copyFile(`${root}/node_modules/tesseract.js/dist/worker.min.js`, `${target}/worker.min.js`)
await copyFile(`${root}/node_modules/tesseract.js/LICENSE.md`, `${target}/LICENSE-tesseract.txt`)
for (const name of await readdir(`${root}/node_modules/tesseract.js-core`)) {
  if (/^tesseract-core.*\.(js|wasm)$/.test(name) || name.startsWith('LICENSE')) await copyFile(`${root}/node_modules/tesseract.js-core/${name}`, `${target}/core/${name}`)
}
for (const lang of ['eng', 'chi_sim']) {
  await copyFile(`${root}/node_modules/@tesseract.js-data/${lang}/4.0.0_best_int/${lang}.traineddata.gz`, `${target}/lang/${lang}.traineddata.gz`)
  await cp(`${root}/node_modules/@tesseract.js-data/${lang}/README.md`, `${target}/lang/README-${lang}.md`)
  await cp(`${root}/node_modules/@tesseract.js-data/${lang}/package.json`, `${target}/lang/package-${lang}.json`)
}
console.log('OCR workers, engine and English/Chinese data copied to this site; no runtime CDN.')
