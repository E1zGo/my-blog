import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readFile, writeFile, mkdir, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { execFileSync } from 'node:child_process'
import ts from 'typescript'

test('compiled production API loads as ESM and fails closed without configuration', async () => {
  // The Vercel compiler reads the root config; it does not follow Vite project references.
  const root = new URL('../', import.meta.url)
  const config = JSON.parse(await readFile(new URL('tsconfig.json', root), 'utf8'))
  const parsed = ts.convertCompilerOptionsFromJson(config.compilerOptions || {}, '.')
  assert.equal(parsed.errors.length, 0)
  const temporary = await mkdtemp(join(tmpdir(), 'research-api-build-'))
  try {
    await writeFile(join(temporary, 'package.json'), '{"type":"module"}')
    for (const name of ['server', 'api']) {
      await mkdir(join(temporary, name))
      const source = await readFile(new URL(`${name}/research-model.ts`, root), 'utf8')
      const compiled = ts.transpileModule(source, { compilerOptions: parsed.options, fileName: `${name}/research-model.ts` }).outputText
      await writeFile(join(temporary, name, 'research-model.js'), compiled)
    }
    const entry = pathToFileURL(join(temporary, 'api/research-model.js')).href
    const script = `import api from ${JSON.stringify(entry)};
      const get = await api.fetch(new Request('https://www.e1zgo.top/api/research-model'));
      const post = await api.fetch(new Request('https://www.e1zgo.top/api/research-model', {method:'POST'}));
      console.log(JSON.stringify({status:get.status, body:await get.json(), post:post.status}));`
    const result = JSON.parse(execFileSync(process.execPath, ['--input-type=module', '-e', script], {
      encoding: 'utf8', env: { ...process.env, RESEARCH_AI_ENABLED: 'false' },
    }))
    assert.deepEqual(result, { status: 200, body: { enabled: false, model: 'gpt-6.1-sol', provider: 'OpenAI', access: 'code' }, post: 503 })
  } finally { await rm(temporary, { recursive: true, force: true }) }
})
