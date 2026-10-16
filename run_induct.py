"""Run skill induction over a recorded episode.

    S2S_INDUCT_BASE_URL=... S2S_INDUCT_API_KEY=... S2S_INDUCT_MODEL=... \
        .venv/Scripts/python.exe run_induct.py --episode expense-submit-default

The endpoint is never hardcoded and no credential is read from anywhere but
the environment, so a run is reproducible from the caller's shell alone.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from induction import EndpointNotConfigured, induce  # noqa: E402
from induction.human import ScriptedHuman, interactive  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", default="expense-submit-default")
    ap.add_argument("--episodes-dir", default=str(ROOT / "episodes"))
    ap.add_argument("--out", default=str(ROOT / "induced"))
    ap.add_argument("--prompt", default="concise", choices=["concise", "pipeline"])
    ap.add_argument("--max-iterations", type=int, default=100)
    ap.add_argument("--max-wall-s", type=float, default=1800.0)
    ap.add_argument("--answers", default=None,
                    help="JSON knowledge base standing in for the demonstrator; "
                         "without it the run has no person attached and must declare gaps")
    ap.add_argument("--drop-verifier-clause", action="store_true",
                    help="ablation: omit the prompt line requiring every skill to "
                         "ship a completion verifier. The tool contract still "
                         "requires the file; what changes is only what the prompt "
                         "says. Recorded in run-metadata.json.")
    ap.add_argument("--interactive", action="store_true",
                    help="put the induction's questions to stdin and read the answers back; "
                         "this is the plugin's real interaction")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    episode_dir = Path(args.episodes_dir) / args.episode
    if not episode_dir.is_dir():
        print(f"episode not found: {episode_dir}", file=sys.stderr)
        return 2

    out_dir = Path(args.out) / f"{args.episode}--{args.prompt}"

    ask = None
    if args.interactive:
        ask = interactive()
        print("[induct] interactive: the induction may ask you questions on stdin")
    elif args.answers:
        ask = ScriptedHuman.load(Path(args.answers), verbose=args.verbose)
        print(f"[induct] demonstrator attached: {args.answers} ({len(ask.rules)} rules)")
    else:
        print("[induct] no demonstrator attached; the run must declare its gaps")

    print(f"[induct] {args.episode} -> {out_dir}")
    try:
        run = induce(
            episode_dir=episode_dir,
            output_dir=out_dir,
            prompt_variant=args.prompt,
            drop_verifier_clause=args.drop_verifier_clause,
            max_iterations=args.max_iterations,
            max_wall_s=args.max_wall_s,
            ask=ask,
            verbose=args.verbose,
        )
    except EndpointNotConfigured as exc:
        print(f"[blocked] {exc}", file=sys.stderr)
        return 3

    summary = run.to_dict()
    asked = run.questions
    if asked:
        summary["questions_asked"] = len(asked)
        summary["questions_answered"] = sum(1 for q in asked if q.get("answer"))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if run.ok:
        print("\n[ok] finalized")
        for skill in sorted(out_dir.rglob("SKILL.md")):
            print(f"     {skill.relative_to(out_dir)}")
    else:
        print("\n[incomplete] run did not finalize", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
