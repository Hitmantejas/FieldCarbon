# Deploying FieldCarbon to Cloud Run

One Cloud Run service, `fieldcarbon-app`, in `us-central1`. It runs the FastAPI backend and serves the built React app from
the same container (see `Dockerfile`). Gemini is called through the Vertex AI `global` endpoint (`gemini-3.5-flash` is not
offered in `us-central1`). By default data is read from the CSVs baked into the image (`FIELDCARBON_DATA=csv`), so the
service needs no BigQuery access. Section 5 switches it to BigQuery.

The project `ai-hackathon-india` is shared with other teams: every resource below starts with `fieldcarbon-`, and nothing
else is touched. Commands are written for Git Bash. Run them in order, from the repo root.

## 0. Check the account and project

```bash
gcloud auth list
gcloud config get-value project
```

## 1. One-off setup

An Artifact Registry repository for the image:

```bash
gcloud artifacts repositories create fieldcarbon-images \
  --repository-format=docker --location=us-central1 --project=ai-hackathon-india \
  --description="FieldCarbon container images"
```

A service account for the service. Its only role is calling Gemini on Vertex AI. It has no key file:

```bash
gcloud iam service-accounts create fieldcarbon-run \
  --display-name="FieldCarbon Cloud Run" --project=ai-hackathon-india

gcloud projects add-iam-policy-binding ai-hackathon-india \
  --member="serviceAccount:fieldcarbon-run@ai-hackathon-india.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user" --condition=None
```

The second command changes the shared project's IAM policy. That needs `resourcemanager.projects.setIamPolicy`. If the
command is refused, ask the project admin to grant this one role.

## 2. Build the image with Cloud Build

`.gcloudignore` keeps out of the upload: raw data, `.env` files, `CLAUDE.md`, `.claude/`, tests and evals. The build
compiles the frontend inside the container, so no local `npm run build` is needed.

```bash
TAG=$(git rev-parse --short HEAD)
gcloud builds submit . --region=us-central1 --project=ai-hackathon-india \
  --tag="us-central1-docker.pkg.dev/ai-hackathon-india/fieldcarbon-images/fieldcarbon-app:$TAG"
```

The tag is the last commit, so build after committing.

## 3. Deploy

```bash
gcloud run deploy fieldcarbon-app --project=ai-hackathon-india --region=us-central1 \
  --image="us-central1-docker.pkg.dev/ai-hackathon-india/fieldcarbon-images/fieldcarbon-app:$TAG" \
  --service-account="fieldcarbon-run@ai-hackathon-india.iam.gserviceaccount.com" \
  --min-instances=0 --max-instances=1 --cpu=1 --memory=1Gi --timeout=120 \
  --allow-unauthenticated \
  --set-env-vars="FIELDCARBON_DATA=csv,FIELDCARBON_PROJECT=ai-hackathon-india,FIELDCARBON_GEMINI_MODEL=gemini-3.5-flash,FIELDCARBON_GEMINI_LOCATION=global,FIELDCARBON_ASK_PER_MINUTE=5,FIELDCARBON_ASK_PER_DAY=200"
```

Why these settings:
- `--max-instances=1`: the question limits (`backend/api/limits.py`) are counted in memory, per instance. With one
  instance they hold for the whole service. It also caps the cost.
- `--min-instances=0`: the service scales to zero when nobody uses it.
- `--allow-unauthenticated`: the judges need a public URL. The question limits keep Gemini spending bounded. If an org
  policy blocks public services, the deploy says so. Then ask the project admin.

## 4. Smoke test

```bash
URL=$(gcloud run services describe fieldcarbon-app --region=us-central1 --project=ai-hackathon-india --format='value(status.url)')
curl -s -o /dev/null -w "%{http_code}\n" "$URL/"              # 200, the app
curl -s -o /dev/null -w "%{http_code}\n" "$URL/api/sources"   # 200, the API
curl -s -X POST "$URL/api/agent/ask" -H "Content-Type: application/json" \
  -d '{"question": "How much fuel did the fleet use, by site?"}'  # one Gemini call
```

## 5. Serve the fleet data from BigQuery (optional)

Load the tables first (`python infra/load_fleet.py --apply`, see the script header). Then let the service account read
them and run queries, and switch the data source:

```bash
for ROLE in roles/bigquery.dataViewer roles/bigquery.jobUser; do
  gcloud projects add-iam-policy-binding ai-hackathon-india \
    --member="serviceAccount:fieldcarbon-run@ai-hackathon-india.iam.gserviceaccount.com" --role="$ROLE" --condition=None
done
gcloud run services update fieldcarbon-app --project=ai-hackathon-india --region=us-central1 \
  --update-env-vars="FIELDCARBON_DATA=bigquery"
```

`dataViewer` on the whole project is read-only but wide in a shared project. If the admin prefers, grant it on the
`fieldcarbon` dataset only. Set `FIELDCARBON_DATA=csv` to go back. The service reads each table once per instance start.

## Removing it

```bash
gcloud run services delete fieldcarbon-app --region=us-central1 --project=ai-hackathon-india
gcloud artifacts repositories delete fieldcarbon-images --location=us-central1 --project=ai-hackathon-india
```
