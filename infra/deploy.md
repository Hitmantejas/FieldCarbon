# Deploying FieldCarbon to Cloud Run

Two Cloud Run services in `us-central1`:

| Service | What it runs | Built from |
|---|---|---|
| `fieldcarbon-backend` | the FastAPI API (tools, analyst agent) | `Dockerfile` at the repo root |
| `fieldcarbon-frontend` | the built React app, and a proxy that forwards `/api` to the backend | `frontend/Dockerfile` |

The browser talks only to the frontend service, so the app needs no CORS settings and the analyst's step-by-step answer
stream works as before. Gemini is called through the Vertex AI `global` endpoint (`gemini-3.5-flash` is not offered in
`us-central1`). By default data is read from the CSVs baked into the backend image (`FIELDCARBON_DATA=csv`); section 5
switches it to BigQuery.

The project `ai-hackathon-india` is shared with other teams: every resource below starts with `fieldcarbon-`, and nothing
else is touched. That is why images are built into our own repository (`fieldcarbon-images`) and not with
`gcloud run deploy --source`, which would create a repository named `cloud-run-source-deploy`. Commands are written for
Git Bash. Run them in order, from the repo root.

## 0. Check the account and project

```bash
gcloud auth list
gcloud config get-value project
```

## 1. One-off setup

An Artifact Registry repository for the images:

```bash
gcloud artifacts repositories create fieldcarbon-images \
  --repository-format=docker --location=us-central1 --project=ai-hackathon-india \
  --description="FieldCarbon container images"
```

A service account for the backend. Its only role is calling Gemini on Vertex AI. It has no key file; Cloud Run attaches it, so
nothing is downloaded or stored. (The frontend service only serves files and forwards requests, so it uses the default
identity and needs no roles.) Pick one:

**A. A new account, used only by FieldCarbon (least privilege):**

```bash
SA=fieldcarbon-run@ai-hackathon-india.iam.gserviceaccount.com
gcloud iam service-accounts create fieldcarbon-run \
  --display-name="FieldCarbon Cloud Run" --project=ai-hackathon-india
gcloud projects add-iam-policy-binding ai-hackathon-india \
  --member="serviceAccount:$SA" --role="roles/aiplatform.user" --condition=None
```

**B. An account you already have.** Check it can call Vertex AI; add the role only if `roles/aiplatform.user` (or
`roles/aiplatform.admin`) is missing. A shared account gives this app every other role it has, so prefer A if it holds more.

```bash
SA=service-acc-1764678321@ai-hackathon-india.iam.gserviceaccount.com
gcloud projects get-iam-policy ai-hackathon-india --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:$SA" --format="value(bindings.role)"
gcloud projects add-iam-policy-binding ai-hackathon-india \
  --member="serviceAccount:$SA" --role="roles/aiplatform.user" --condition=None   # only if it was missing
```

The second command changes the shared project's IAM policy. That needs `resourcemanager.projects.setIamPolicy`. If the
command is refused, ask the project admin to grant this one role.

## 2. Backend

`.gcloudignore` keeps out of the upload: raw data, `.env` files, `CLAUDE.md`, `.claude/`, tests, evals and the frontend.

```bash
TAG=$(git rev-parse --short HEAD)   # the last commit, so build after committing
REPO=us-central1-docker.pkg.dev/ai-hackathon-india/fieldcarbon-images

gcloud builds submit . --region=us-central1 --project=ai-hackathon-india --tag="$REPO/fieldcarbon-backend:$TAG"

gcloud run deploy fieldcarbon-backend --project=ai-hackathon-india --region=us-central1 \
  --image="$REPO/fieldcarbon-backend:$TAG" \
  --service-account="$SA" \
  --min-instances=0 --max-instances=1 --cpu=1 --memory=1Gi --timeout=300 \
  --allow-unauthenticated \
  --set-env-vars="FIELDCARBON_DATA=csv,FIELDCARBON_PROJECT=ai-hackathon-india,FIELDCARBON_GEMINI_MODEL=gemini-3.5-flash,FIELDCARBON_GEMINI_LOCATION=global,FIELDCARBON_ASK_PER_MINUTE=5,FIELDCARBON_ASK_PER_DAY=200,FIELDCARBON_TRUSTED_PROXIES=1"
```

Why these settings:
- `--max-instances=1`: the question limits (`backend/api/limits.py`) are counted in memory, per instance. With one
  instance they hold for the whole service. It also caps the cost.
- `--min-instances=0`: scale to zero when nobody uses it.
- `--timeout=300`: an answer can take up to a minute; the stream stays open while the analyst works.
- `FIELDCARBON_TRUSTED_PROXIES=1`: the frontend service sits in front of the backend, so Cloud Run sees the frontend as the
  caller. With 1, each visitor is counted by their own address, taken from the entry before the frontend's.
- `--allow-unauthenticated`: the frontend service calls the backend over its public address. A person who reaches the
  backend directly can fake their address to dodge the per-minute limit; the daily cap (200 questions) still bounds what
  Gemini can cost. If an org policy blocks public services, the deploy says so. Then ask the project admin.

## 3. Frontend

Needs the backend's address, so deploy it second.

```bash
BACKEND_URL=$(gcloud run services describe fieldcarbon-backend --region=us-central1 --project=ai-hackathon-india --format='value(status.url)')

gcloud builds submit ./frontend --region=us-central1 --project=ai-hackathon-india --tag="$REPO/fieldcarbon-frontend:$TAG"

gcloud run deploy fieldcarbon-frontend --project=ai-hackathon-india --region=us-central1 \
  --image="$REPO/fieldcarbon-frontend:$TAG" \
  --min-instances=0 --max-instances=2 --cpu=1 --memory=256Mi --timeout=300 \
  --allow-unauthenticated \
  --set-env-vars="BACKEND_URL=$BACKEND_URL"
```

The frontend URL is the one to share. If the backend is ever redeployed under a new address, rerun the last command with the
new `BACKEND_URL`.

## 4. Smoke test

```bash
URL=$(gcloud run services describe fieldcarbon-frontend --region=us-central1 --project=ai-hackathon-india --format='value(status.url)')
curl -s -o /dev/null -w "%{http_code}\n" "$URL/"              # 200, the app
curl -s -o /dev/null -w "%{http_code}\n" "$URL/#/proof"       # 200, any screen is the same page
curl -s -o /dev/null -w "%{http_code}\n" "$URL/api/sources"   # 200, the API through the proxy
curl -s -N -X POST "$URL/api/agent/ask/stream" -H "Content-Type: application/json" \
  -d '{"question": "How much fuel did the fleet use, by site?"}'  # one Gemini call; steps arrive one by one
```

## 5. Serve the fleet data from BigQuery (optional)

Load the tables first (`python infra/load_fleet.py --apply`, see the script header). Then let the backend's service account
read them and run queries, and switch the data source:

```bash
for ROLE in roles/bigquery.dataViewer roles/bigquery.jobUser; do
  gcloud projects add-iam-policy-binding ai-hackathon-india \
    --member="serviceAccount:$SA" --role="$ROLE" --condition=None
done
gcloud run services update fieldcarbon-backend --project=ai-hackathon-india --region=us-central1 \
  --update-env-vars="FIELDCARBON_DATA=bigquery"
```

`dataViewer` on the whole project is read-only but wide in a shared project. If the admin prefers, grant it on the
`fieldcarbon` dataset only. Set `FIELDCARBON_DATA=csv` to go back. The service reads each table once per instance start.

## Removing it

```bash
gcloud run services delete fieldcarbon-frontend --region=us-central1 --project=ai-hackathon-india
gcloud run services delete fieldcarbon-backend --region=us-central1 --project=ai-hackathon-india
gcloud artifacts repositories delete fieldcarbon-images --location=us-central1 --project=ai-hackathon-india
```
