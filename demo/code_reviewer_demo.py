"""Azure Context Cache — end-to-end validation demo (AI Code Reviewer).

Sends N PR-review requests to an Azure OpenAI deployment using the **Responses
API**. The same ~2.4K-token system prompt (`system_prompt.md`) is sent on every
call — only the trailing diff varies. If the deployment is linked to an Azure
Context Cache container (as the one created by this repo's `azuredeploy.json`
is), call #2 onward should show large `cached_tokens` and meaningfully lower
latency than call #1.

Usage:
    # Recommended: use the deployment outputs from the ARM deploy
    python code_reviewer_demo.py \
        --endpoint   https://<prefix>-aoai.openai.azure.com \
        --deployment context-cache-deployment \
        --api-key    $env:AOAI_KEY \
        --runs 6

    # Or use Azure AD (DefaultAzureCredential)
    python code_reviewer_demo.py --endpoint ... --deployment ... --aad --runs 6

Environment variables (override CLI defaults):
    AOAI_ENDPOINT, AOAI_DEPLOYMENT, AOAI_API_KEY, AOAI_API_VERSION
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
DEFAULT_API_VERSION = "2026-03-15-preview"


def _aad_token() -> str:
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError:
        sys.exit("azure-identity not installed: pip install azure-identity")
    return (
        DefaultAzureCredential(exclude_interactive_browser_credential=False)
        .get_token("https://cognitiveservices.azure.com/.default")
        .token
    )


def load_diffs(n: int) -> list[tuple[str, str]]:
    files = sorted((HERE / "diffs").glob("*.diff"))
    if not files:
        sys.exit("No diffs found under ./diffs")
    out: list[tuple[str, str]] = []
    i = 0
    while len(out) < n:
        f = files[i % len(files)]
        out.append((f.name, f.read_text(encoding="utf-8")))
        i += 1
    return out


def build_payload(deployment: str, system_prompt: str, diff_name: str, diff_body: str,
                  max_output_tokens: int) -> dict:
    user_msg = (
        "Review this PR diff and return the JSON described in your instructions.\n\n"
        f"File: {diff_name}\n\n```diff\n{diff_body}\n```"
    )
    return {
        "model": deployment,
        "input": [
            {
                "type": "message",
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": user_msg}],
            },
        ],
        "max_output_tokens": max_output_tokens,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--endpoint", default=os.getenv("AOAI_ENDPOINT", ""),
                   help="Azure OpenAI endpoint (e.g. https://<prefix>-aoai.openai.azure.com).")
    p.add_argument("--deployment", default=os.getenv("AOAI_DEPLOYMENT", "context-cache-deployment"),
                   help="AOAI deployment name (default: context-cache-deployment).")
    p.add_argument("--api-key", default=os.getenv("AOAI_API_KEY", ""),
                   help="AOAI API key. Ignored when --aad is set.")
    p.add_argument("--aad", action="store_true",
                   help="Use DefaultAzureCredential instead of an API key.")
    p.add_argument("--api-version", default=os.getenv("AOAI_API_VERSION", DEFAULT_API_VERSION))
    p.add_argument("--runs", type=int, default=6,
                   help="How many requests to send (default: 6).")
    p.add_argument("--max-output", type=int, default=200,
                   help="max_output_tokens per call (default: 200).")
    p.add_argument("--show-output", action="store_true",
                   help="Print the JSON reviewer output for each call.")
    args = p.parse_args()

    if not args.endpoint:
        sys.exit("Set --endpoint or AOAI_ENDPOINT (see deployment Outputs tab).")
    if not args.aad and not args.api_key:
        sys.exit("Provide --api-key / AOAI_API_KEY, or pass --aad.")

    url = f"{args.endpoint.rstrip('/')}/openai/v1/responses?api-version={args.api_version}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if args.aad:
        headers["Authorization"] = f"Bearer {_aad_token()}"
    else:
        headers["api-key"] = args.api_key
        headers["Authorization"] = f"Bearer {args.api_key}"

    system_prompt = (HERE / "system_prompt.md").read_text(encoding="utf-8")
    diffs = load_diffs(args.runs)

    print(f"\nAzure Context Cache demo  ·  endpoint = {args.endpoint}")
    print(f"deployment = {args.deployment}  ·  runs = {args.runs}  ·  api = {args.api_version}\n")
    print(f"{'#':>2}  {'diff':<26} {'lat(ms)':>9}  {'in':>6}  {'cached':>7}  {'out':>5}  {'hit%':>5}")
    print("-" * 72)

    latencies: list[float] = []
    cached_pcts: list[float] = []
    first_latency = None
    warm_latencies: list[float] = []

    with httpx.Client(timeout=240.0) as client:
        for i, (name, body) in enumerate(diffs, 1):
            payload = build_payload(args.deployment, system_prompt, name, body, args.max_output)
            t0 = time.perf_counter()
            try:
                r = client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as e:
                print(f"{i:>2}  {name:<26}  transport error: {e}")
                continue
            lat = (time.perf_counter() - t0) * 1000.0
            if r.status_code >= 400:
                print(f"{i:>2}  {name:<26}  HTTP {r.status_code}: {r.text[:200]}")
                continue
            data = r.json()
            usage = data.get("usage", {}) or {}
            in_tok = int(usage.get("input_tokens") or 0)
            out_tok = int(usage.get("output_tokens") or 0)
            cached = int((usage.get("input_tokens_details") or {}).get("cached_tokens") or 0)
            pct = (100.0 * cached / in_tok) if in_tok else 0.0

            latencies.append(lat)
            cached_pcts.append(pct)
            if i == 1:
                first_latency = lat
            else:
                warm_latencies.append(lat)

            print(f"{i:>2}  {name:<26} {lat:>9.0f}  {in_tok:>6}  {cached:>7}  {out_tok:>5}  {pct:>4.0f}%")
            if args.show_output:
                text = data.get("output_text") or json.dumps(data.get("output"), indent=2)[:500]
                print(f"      output: {text[:300]}{'…' if len(text) > 300 else ''}")

    if not latencies:
        return 2

    print("-" * 72)
    print(f"mean latency        : {statistics.mean(latencies):>7.0f} ms")
    if warm_latencies:
        speedup = (first_latency / statistics.mean(warm_latencies)) if first_latency else 0.0
        print(f"call 1 (cold)       : {first_latency:>7.0f} ms")
        print(f"calls 2..N (warm)   : {statistics.mean(warm_latencies):>7.0f} ms mean   →   {speedup:.2f}× speedup")
    print(f"mean cached prefix  : {statistics.mean(cached_pcts):>6.1f}% of input tokens")
    if statistics.mean(cached_pcts) < 1:
        print("\n⚠  cached_tokens is ~0. Things to check:")
        print("    · The deployment has properties.contextCacheContainerId set (this is what the ARM template does).")
        print("    · You are sending the byte-identical system prompt every call.")
        print("    · The Microsoft.CognitiveServices/OpenAI.ContextCacheAllowed feature is Registered.")
    else:
        print("\n✓  Prompt cache is active — the linked Azure Context Cache container is serving hits.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
