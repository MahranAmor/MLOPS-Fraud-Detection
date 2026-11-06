FROM jenkins/jenkins:lts

USER root

RUN apt-get update && apt-get install -y \
        wget build-essential libssl-dev zlib1g-dev \
        libncurses5-dev libncursesw5-dev libreadline-dev \
        libsqlite3-dev libgdbm-dev libdb5.3-dev libbz2-dev \
        libexpat1-dev liblzma-dev libffi-dev uuid-dev \
        lsb-release curl gnupg && \
    wget https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tgz && \
    tar -xf Python-3.11.9.tgz && \
    cd Python-3.11.9 && \
    ./configure --enable-optimizations && \
    make -j$(nproc) && \
    make altinstall && \
    cd .. && rm -rf Python-3.11.9 Python-3.11.9.tgz && \
    update-alternatives --install /usr/bin/python3 python3 /usr/local/bin/python3.11 1 && \
    python3.11 -m pip install --upgrade pip && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | \
        tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y docker-ce-cli docker-compose-plugin && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# TARGETARCH est fourni par BuildKit (amd64 sur PC, arm64 sur Mac Apple Silicon)
ARG TARGETARCH
RUN curl -LO "https://dl.k8s.io/release/v1.32.2/bin/linux/${TARGETARCH:-amd64}/kubectl" && \
    chmod +x kubectl && mv kubectl /usr/local/bin/kubectl

# Dépendances ML pré-installées : requirements.txt (racine) contient déjà dvc,
# mlflow et prometheus-client ; Evidently est épinglé sur la série 0.7, dont
# drift_detection.py utilise l'API (evidently.Report, evidently.presets).
COPY requirements.txt /tmp/requirements.txt

RUN python3.11 -m venv /opt/venv-fraud && \
    /opt/venv-fraud/bin/pip install --upgrade pip && \
    /opt/venv-fraud/bin/pip install -r /tmp/requirements.txt && \
    /opt/venv-fraud/bin/pip install "evidently>=0.7,<0.8"

USER jenkins