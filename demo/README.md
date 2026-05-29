# End-to-end validation demo — AI Code Reviewer

This is a minimal Python sample that validates the Azure Context Cache → Azure OpenAI link created by the one-click ARM template at the repo root. It sends N PR-review requests to the deployment using the **Responses API**, with a ~2.4K-token stable system prompt and a varying diff per call, and prints `cached_tokens` + latency for each call.

If the deployment is properly linked to a cache container, you should see:

- **Call #1:** `cached_tokens` near 0, full latency (cold).
- **Calls #2..N:** `cached_tokens` ≈ system-prompt size, latency a few× lower (warm).

The workload mirrors **Step 5** of the original `contextCacheDemo` repository (remote prompt cache, concurrent + warm), trimmed down to the smallest useful end-to-end probe.

## Setup

```powershell
cd demo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

Grab the AOAI endpoint and deployment name from your deployment's **Outputs** tab (`azureOpenAIEndpoint`, `aoaiDeploymentName`).

```powershell
$env:AOAI_ENDPOINT   = "https://<prefix>-aoai.openai.azure.com"
$env:AOAI_DEPLOYMENT = "context-cache-deployment"
$env:AOAI_API_KEY    = "<your aoai key>"        # or pass --aad

python code_reviewer_demo.py --runs 6
```

### Run with Azure AD / Managed Identity (no key)

The same script works keyless via `DefaultAzureCredential` — just add `--aad` and skip `AOAI_API_KEY`. `DefaultAzureCredential` automatically tries, in order: env-var service principal → workload identity → **managed identity** → Azure CLI (`az login`) → VS Code → interactive browser. So the *same* command runs unchanged on your laptop (uses `az login`) and on an Azure VM / App Service / AKS pod / Container App (uses its assigned MI).

**One-time RBAC grant** (the identity needs data-plane access to the AOAI account):

```powershell
# Pick the identity you'll run as:
$principalId = (az ad signed-in-user show --query id -o tsv)            # local laptop / az login
# $principalId = "<system-assigned MI principalId>"                      # VM/App Service system MI
# $principalId = "<user-assigned MI principalId>"                        # UAMI

# Scope = the AOAI account that hosts the linked deployment
$aoai = az cognitiveservices account show -n <aoai-account-name> -g <aoai-rg> --query id -o tsv

az role assignment create `
  --assignee-object-id $principalId `
  --assignee-principal-type User `   # use ServicePrincipal for MI
  --role "Cognitive Services OpenAI User" `
  --scope $aoai
```

Then run:

```powershell
$env:AOAI_ENDPOINT   = "https://<prefix>-aoai.openai.azure.com"
$env:AOAI_DEPLOYMENT = "context-cache-deployment"
Remove-Item Env:AOAI_API_KEY -ErrorAction SilentlyContinue

# Local laptop (uses your az login):
az login
python code_reviewer_demo.py --aad --runs 6

# On an Azure VM with system-assigned MI: nothing else to do — same command works.
# On a VM with a user-assigned MI, point DefaultAzureCredential at it:
$env:AZURE_CLIENT_ID = "<UAMI clientId>"
python code_reviewer_demo.py --aad --runs 6
```

The script requests a token for the audience `https://cognitiveservices.azure.com/.default` and sends it as `Authorization: Bearer <token>`. No code change needed between key and AAD/MI modes.

### CLI flags

| Flag | Description |
|---|---|
| `--endpoint` / `AOAI_ENDPOINT` | AOAI endpoint URL |
| `--deployment` / `AOAI_DEPLOYMENT` | Deployment name (default `context-cache-deployment`) |
| `--api-key` / `AOAI_API_KEY` | AOAI key |
| `--aad` | Use `DefaultAzureCredential` instead of a key |
| `--api-version` | Defaults to `2026-03-15-preview` |
| `--runs` | Number of requests (default 6) |
| `--max-output` | `max_output_tokens` per call (default 200) |
| `--show-output` | Also print the reviewer's JSON for each call |

## Expected output

```
Azure Context Cache demo  ·  endpoint = https://mycache01-aoai.openai.azure.com
deployment = context-cache-deployment  ·  runs = 6  ·  api = 2026-03-15-preview

 #  diff                         lat(ms)      in   cached    out   hit%
------------------------------------------------------------------------
 1  01-sql-injection.diff           8730    2456        0    180     0%
 2  02-disabled-tls.diff            1840    2452     2432    176    99%
 3  03-n-plus-one.diff              1910    2470     2432    188    98%
 4  04-clean-refactor.diff          1875    2478     2432    192    98%
 5  05-logged-token.diff            1820    2454     2432    181    99%
 6  06-mutable-default.diff         1795    2448     2432    175    99%
------------------------------------------------------------------------
mean latency        :    2995 ms
call 1 (cold)       :    8730 ms
calls 2..N (warm)   :    1848 ms mean   →   4.72× speedup
mean cached prefix  :   82.2% of input tokens

✓  Prompt cache is active — the linked Azure Context Cache container is serving hits.
```

The exact numbers will vary, but the **shape** — cold first call, warm rest, `cached_tokens` ≈ system-prompt size, several-× latency drop — is the success signal.

## Files

```
demo/
├── code_reviewer_demo.py   # the runnable sample
├── requirements.txt
├── system_prompt.md        # ~2.4K-token stable prefix (Reviewer-GPT)
└── diffs/                  # 22 PR diffs used as the variable tail
```

The `system_prompt.md` and `diffs/*.diff` are copied verbatim from the [contextCacheDemo](https://github.com/kraman-msft-eng/contextCacheDemo) reference so the cache-hit shape matches that demo's Step 5.
