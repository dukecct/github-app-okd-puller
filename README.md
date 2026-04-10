# github-app-okd-puller
Container that clones/pulls a github repo in okd using GitHub App credentials

## Files

- `repo_sync.py`: Uses GitHub App credentials to clone or pull a repository.
- `requirements.txt`: Python dependencies for the sync script.
- `Dockerfile`: OKD-compatible image build.
- `.github/workflows/publish-ghcr.yml`: Builds and pushes image to GHCR when a release is published.

## Required environment variables

- `GITHUB_APP_ID`: GitHub App ID.
- `GITHUB_REPO`: Target repository in `owner/repo` format.
- `GITHUB_APP_PRIVATE_KEY` or `GITHUB_APP_PRIVATE_KEY_FILE`: App private key PEM content or path.

## Optional environment variables

- `GITHUB_APP_INSTALLATION_ID`: Installation ID override. If not set, the script resolves the installation for `GITHUB_REPO` automatically.
- `GIT_TARGET_DIR`: Destination path for the repo. Default is `/work/<repo-name>`.

## Local run

```bash
pip install -r requirements.txt
python repo_sync.py
```

## Build and run container

```bash
docker build -t ghcr.io/<owner>/<image>:dev .
docker run --rm \
	-e GITHUB_APP_ID="<app-id>" \
	-e GITHUB_REPO="<owner>/<repo>" \
	-e GITHUB_APP_PRIVATE_KEY="$(cat /path/to/private-key.pem)" \
	ghcr.io/<owner>/<image>:dev
```

## Example OKD Job YAML

This example stores the app ID in a `my-secrets` secret, mounts the PEM from a separate `github-app-pem` secret, and keeps `GITHUB_REPO` as a direct job parameter.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: github-app-puller-work
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
---
apiVersion: batch/v1
kind: Job
metadata:
  name: github-app-puller
spec:
  backoffLimit: 2
  ttlSecondsAfterFinished: 3600
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: puller
          image: ghcr.io/johnbradley/github-app-okd-puller:0.0.1
          imagePullPolicy: IfNotPresent
          env:
            - name: GITHUB_APP_ID
              valueFrom:
                secretKeyRef:
                  name: my-secrets
                  key: GITHUB_APP_ID
            - name: GITHUB_REPO
              value: "your-org/your-repo"
            - name: GITHUB_APP_PRIVATE_KEY_FILE
              value: /var/run/secrets/github-app/private-key.pem
          volumeMounts:
            - name: github-app-key
              mountPath: /var/run/secrets/github-app
              readOnly: true
            - name: work
              mountPath: /work
      volumes:
        - name: github-app-key
          secret:
            secretName: github-app-pem
            items:
              - key: github-app-key.pem
                path: private-key.pem
        - name: work
          persistentVolumeClaim:
            claimName: github-app-puller-work
```

Create the referenced secrets before applying the job:

```bash
oc create secret generic my-secrets \
	--from-literal=GITHUB_APP_ID="<app-id>"

oc create secret generic github-app-pem \
	--from-file=github-app-key.pem=/path/to/private-key.pem
```

## GHCR publish workflow

On release publish, GitHub Actions builds and pushes the image tagged with the release tag:

- `ghcr.io/<owner>/<repo>:<release-tag>`

The workflow uses `secrets.GITHUB_TOKEN` with `packages: write` permission.

