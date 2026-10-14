/**
 * dsh-show2skill — record a demonstration, induce a skill, install it.
 *
 * The design follows from what the measurements actually support, which is not
 * the obvious design.
 *
 * **What this plugin does not do.** It does not claim to learn a workflow from
 * a recording and then do it unattended. Measured against this project's own
 * benchmark, a recording replayed verbatim scores 100/100 on the page it was
 * recorded from, so on that page nothing learned from it can beat it; and an
 * induced skill with no other input scores the same as no skill at all on a
 * task whose judgement is not legible as a data field. A plugin that promised
 * unattended automation would be promising something the numbers do not
 * support.
 *
 * **What it does.** It records once, induces what can be induced, and — this is
 * the part with evidence behind it — *asks about the part it could not induce*.
 * On the reporting task in this project, one answered question took the score
 * from 35 to 100. The induction is required to reconcile the demonstration's
 * input against its output and to name the difference its own rules cannot
 * explain, so the question it asks is specific: not "how does this work" but
 * "these two rows were excluded and the only field distinguishing them is X —
 * is the rule about X, or something broader?"
 *
 * The skill it produces is a plain `SKILL.md` with YAML frontmatter, which the
 * harness already reads natively, so installation is a file copy. The
 * completion verifier travels beside it as `verify.json`.
 *
 * **Status: written against the documented plugin API, not yet run inside a
 * live harness.** The pipeline it wraps is tested end to end on its own
 * (`python reproduce.py`); this wrapper is not.
 */

import { spawn } from 'node:child_process'
import { cp, mkdir, readFile, readdir, rm } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join, resolve } from 'node:path'

export const name = 'dsh-show2skill'

// The tools service must exist before `apply` runs, or `ctx.tools` is undefined.
export const inject = ['tools']

export const Config = {
  /** Where the show2skill checkout lives. */
  projectRoot: '',
  /** Python interpreter with the project's dependencies installed. */
  python: 'python',
  /** Where episodes are written. Defaults to <projectRoot>/episodes. */
  episodesDir: '',
  /** Where induced skills are installed. Defaults to the project's skills root. */
  skillsDir: '',
  /** Ask the person who gave the demonstration when the induction cannot tell. */
  askHuman: true,
}

/**
 * Run the project's Python entry points and stream their output back.
 *
 * Shelling out is a real dependency and worth stating plainly: this plugin is a
 * front end for a Python pipeline, not a reimplementation of it. The pipeline
 * is the part with tests.
 */
function runPython({ python, cwd, args, onOutput, askHuman, question }) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(python, args, {
      cwd,
      env: {
        ...process.env,
        // The induction reads answers from stdin when a person is attached.
        // Piping is how a UI surfaces the question; with no UI the run is told
        // so and must declare the gap instead of inventing a rule.
        S2S_ASK_MODE: askHuman ? 'stdin' : 'none',
      },
    })

    let stdout = ''
    let stderr = ''
    child.stdout.on('data', (chunk) => {
      const text = chunk.toString()
      stdout += text
      onOutput?.(text)
    })
    child.stderr.on('data', (chunk) => {
      const text = chunk.toString()
      stderr += text
      onOutput?.(text)
    })

    // A question arrives on stdout framed by the interaction helper. Surfacing
    // it is the plugin's whole reason for existing, so it is parsed rather than
    // passed through as log noise.
    if (askHuman && question) {
      child.stdout.on('data', (chunk) => {
        const text = chunk.toString()
        const marker = 'The skill induction has a question:'
        if (text.includes(marker)) question(text)
      })
    }

    child.on('error', reject)
    child.on('close', (code) => {
      if (code === 0) resolvePromise({ stdout, stderr })
      else reject(new Error(`show2skill exited ${code}\n${stderr.slice(-2000)}`))
    })
  })
}

/**
 * Find the extraction manifest the induction wrote under an output root.
 *
 * The run directory is named for the episode and the prompt variant, and the
 * variant is a runtime setting, so it is discovered rather than assumed.
 */
async function findManifest(outDir) {
  const entries = await readdir(outDir, { withFileTypes: true }).catch(() => [])
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const candidate = join(outDir, entry.name, 'extraction-manifest.json')
    if (existsSync(candidate)) {
      try {
        return JSON.parse(await readFile(candidate, 'utf8'))
      } catch {
        return null
      }
    }
  }
  return null
}

export function apply(ctx, config) {
  const root = resolve(config.projectRoot || process.cwd())
  const episodesDir = resolve(config.episodesDir || join(root, 'episodes'))
  const skillsDir = resolve(
    config.skillsDir || join(homedir(), '.dsh', 'skills'),
  )

  const python = config.python || 'python'

  ctx.tools.register({
    name: 'show2skill_record',
    description:
      'Record a demonstration of a GUI workflow and package it as an episode. ' +
      'Run this while performing the task yourself, once. The episode captures ' +
      'screen video, action traces with resolved UI targets, and the files the ' +
      'task produced.',
    parameters: {
      type: 'object',
      properties: {
        task: { type: 'string', description: 'Task id to record, e.g. expense-submit.' },
        variant: { type: 'string', description: 'Page variant, defaults to the task default.' },
      },
      required: ['task'],
    },
    async execute({ task, variant }) {
      const args = ['run_sample.py', '--task', task]
      if (variant) args.push('--variant', variant)
      const { stdout } = await runPython({ python, cwd: root, args })
      const episode = /episode '([^']+)'/.exec(stdout)?.[1] ?? task
      return {
        episode,
        path: join(episodesDir, episode),
        note: 'Recorded. Now run show2skill_induce on this episode.',
      }
    },
  })

  ctx.tools.register({
    name: 'show2skill_induce',
    description:
      'Induce a reusable skill and a completion verifier from a recorded ' +
      'episode. The induction reconciles what the demonstration produced ' +
      'against what it consumed, and asks about any difference its own rules ' +
      'cannot explain. Answer those questions — they are the part a recording ' +
      'cannot carry, and they are usually the difference between a skill that ' +
      'works and one that scores the same as no skill at all.',
    parameters: {
      type: 'object',
      properties: {
        episode: { type: 'string', description: 'Episode id, as returned by show2skill_record.' },
        out: { type: 'string', description: 'Where to write the skill. Defaults to a temp dir.' },
        install: {
          type: 'boolean',
          description: 'Copy the induced skill into the harness skill directory. Default true.',
        },
      },
      required: ['episode'],
    },
    async execute({ episode, out, install }, toolCtx) {
      const outDir = out || join(root, 'induced', episode)
      const args = ['run_induct.py', '--episode', episode, '--out', outDir]
      if (config.askHuman) args.push('--interactive')

      const question = (text) => toolCtx?.ui?.notify?.(text)

      const { stdout } = await runPython({
        python, cwd: root, args, askHuman: config.askHuman, question,
      })

      if (!stdout.includes('[ok] finalized')) {
        return {
          installed: false,
          note:
            'The induction did not finalize. Its questions may be unanswered, or ' +
            'the run may have hit the provider. Nothing was installed.',
        }
      }

      // Read the manifest rather than parsing stdout. The manifest is the
      // pipeline's own record of what it produced, it names the skills, and it
      // flags anything it treated as an abandoned draft -- which must not be
      // installed.
      const manifest = await findManifest(outDir)
      if (!manifest) {
        return { installed: false, note: `no extraction manifest under ${outDir}` }
      }
      const skills = manifest.skills ?? []
      if (!skills.length) {
        return { installed: false, note: 'the manifest lists no skills' }
      }

      const runDir = dirname(join(outDir, skills[0].path))
      if (!install) {
        return { installed: false, out: runDir, skills: skills.map((s) => s.name) }
      }

      await mkdir(skillsDir, { recursive: true })
      const installed = []
      for (const skill of skills) {
        const source = join(runDir, skill.name)
        if (!existsSync(source)) continue
        const target = join(skillsDir, skill.name)
        await rm(target, { recursive: true, force: true })
        await cp(source, target, { recursive: true })
        installed.push(skill.name)
      }

      return {
        installed: true,
        skills: installed,
        at: skillsDir,
        assertions: (manifest.verifiers ?? []).reduce(
          (n, v) => n + (v.assertions ?? 0), 0,
        ),
        // Gaps are the honest part of the artifact: things the induction
        // declared it could not check. Worth surfacing rather than burying.
        gaps: manifest.warnings ?? [],
        orphaned: manifest.orphaned_skill_files ?? [],
      }
    },
  })

  ctx.tools.register({
    name: 'show2skill_replay',
    description:
      'Replay a recorded episode as a fixed macro against a page variant, and ' +
      'report what it scores. Useful as a baseline: on the page a demonstration ' +
      'was recorded from, this is expected to be perfect, and any induced skill ' +
      'has to beat it there rather than beat doing nothing.',
    parameters: {
      type: 'object',
      properties: {
        episode: { type: 'string' },
        variant: { type: 'string', description: 'Page variant to replay against.' },
        reparam: {
          type: 'boolean',
          description: 'Re-read field values from the live page instead of replaying literals.',
        },
      },
      required: ['episode', 'variant'],
    },
    async execute({ episode, variant, reparam }) {
      const args = ['run_macro.py', '--episode', episode, '--variant', variant]
      if (reparam) args.push('--reparam')
      const { stdout } = await runPython({ python, cwd: root, args })
      const score = /Score ([\d.]+)\/100/.exec(stdout)?.[1]
      return { variant, reparam: !!reparam, score: score ? Number(score) : null }
    },
  })

  ctx.logger?.info?.(
    `show2skill ready: episodes in ${episodesDir}, skills installed into ${skillsDir}`,
  )
}
