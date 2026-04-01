FROM registry.access.redhat.com/ubi9/python-311:latest

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

WORKDIR /opt/app

COPY requirements.txt ./
USER 0
RUN pip install --no-cache-dir -r requirements.txt && \
    if command -v microdnf >/dev/null 2>&1; then \
        microdnf install -y git && microdnf clean all; \
    elif command -v dnf >/dev/null 2>&1; then \
        dnf install -y git && dnf clean all; \
    elif command -v yum >/dev/null 2>&1; then \
        yum install -y git && yum clean all; \
    else \
        echo "No supported package manager found (microdnf/dnf/yum)" >&2; exit 1; \
    fi

COPY repo_sync.py ./repo_sync.py

# OKD/OpenShift compatibility: allow arbitrary UID in root group to read/write.
RUN mkdir -p /work && \
    chgrp -R 0 /opt/app /work /tmp && \
    chmod -R g=u /opt/app /work /tmp

WORKDIR /work
USER 1001

ENTRYPOINT ["python", "/opt/app/repo_sync.py"]
