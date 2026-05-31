#!/usr/bin/env bash
# One-time setup for the GitHub Actions CI/CD pipeline.
#
# Run this ONCE in Google Cloud Shell (it has gcloud + your project auth). It
# creates a "deployer" service account with the roles the pipeline needs, then
# prints the JSON key + the exact GitHub secrets to paste.
#
#   bash scripts/setup_cicd.sh
#
# After it finishes, add the printed values as GitHub repository secrets:
#   Settings → Secrets and variables → Actions → New repository secret
set -euo pipefail

PROJECT_ID="$(gcloud config get-value project 2>/dev/null)"
SA_NAME="goopher-deployer"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
KEY_FILE="goopher-deployer-key.json"

echo "Project: ${PROJECT_ID}"

# 1. Enable required APIs (idempotent).
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com aiplatform.googleapis.com \
  firestore.googleapis.com cloudtrace.googleapis.com iam.googleapis.com

# 2. Create the deployer service account (ignore error if it already exists).
gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="GOOPHER CI/CD deployer" 2>/dev/null || true

# 3. Grant the roles the pipeline needs: build, push, deploy, act-as runtime SA.
for ROLE in \
  roles/run.admin \
  roles/cloudbuild.builds.editor \
  roles/artifactregistry.admin \
  roles/storage.admin \
  roles/iam.serviceAccountUser \
  roles/datastore.user \
  roles/aiplatform.user \
  roles/cloudtrace.agent ; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" --role="${ROLE}" --condition=None >/dev/null
  echo "  granted ${ROLE}"
done

# 4. Create a JSON key for GitHub Actions.
gcloud iam service-accounts keys create "${KEY_FILE}" --iam-account="${SA_EMAIL}"

echo
echo "============================================================"
echo "Add these GitHub repository secrets:"
echo "  GCP_PROJECT_ID = ${PROJECT_ID}"
echo "  JWT_SECRET     = $(python3 -c 'import secrets;print(secrets.token_hex(32))')"
echo "  GCP_SA_KEY     = (paste the FULL contents of ${KEY_FILE} below)"
echo "============================================================"
echo
echo "----- ${KEY_FILE} (copy everything between the lines) -----"
cat "${KEY_FILE}"
echo "----- end of key -----"
echo
echo "SECURITY: after pasting into GitHub, delete the local key:"
echo "  rm ${KEY_FILE}"
