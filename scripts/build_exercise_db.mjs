// Builds custom_components/opengym/exercises.json.gz from an openGym checkout.
//
//   node scripts/build_exercise_db.mjs /path/to/openGym
//
// Uses openGym's own catalogue modules, so names and muscle weights are exactly
// what the app shows: the English title (capitalised like the app's CSS does),
// the German name pack (catalogue/i18n/de.json) and muscleWeightsOf() per
// exercise. Format: {"v":1,"ex":{id:[en,de|null,bp,{slug:weight}]},"alias":{id:id}}
import { readFileSync, writeFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(process.argv[2] || '../openGym')
const lib = join(root, 'frontend/src/lib')
const { CATALOGUE } = await import(join(lib, 'exercises.js'))
const { EXALIAS } = await import(join(lib, 'exercises-data.js'))
const { muscleWeightsOf, MUSCLES } = await import(join(lib, 'muscles.js'))
const de = JSON.parse(readFileSync(join(root, 'catalogue/i18n/de.json'), 'utf8'))

const capWords = s => String(s || '').replace(/(^|[\s(\-\/])(\p{Ll})/gu, (m, pre, ch) => pre + ch.toUpperCase())
const ex = {}
for (const e of CATALOGUE) {
  const w = {}
  for (const [slug, v] of Object.entries(muscleWeightsOf(e))) if (v > 0 && MUSCLES.includes(slug)) w[slug] = Math.round(v * 1000) / 1000
  ex[e.id] = [capWords(e.n), de[e.id]?.name || null, e.bp || null, w]
}
const out = { v: 1, ex, alias: EXALIAS }
const here = dirname(fileURLToPath(import.meta.url))
const target = join(here, '../custom_components/opengym/exercises.json.gz')
const buf = gzipSync(Buffer.from(JSON.stringify(out)), { level: 9 })
writeFileSync(target, buf)
console.log(`${Object.keys(ex).length} exercises, ${Object.keys(EXALIAS).length} aliases -> ${target} (${buf.length} bytes)`)
