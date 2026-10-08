# Puts the .myenv virtualenv first on PATH so recipes find uvicorn, python, hf, ...
# without the shell having to activate it first.
export PATH := justfile_directory() + "/.myenv/bin:" + env_var("PATH")

# Installs the Python dependencies into .myenv and the frontend packages.
install_libraries:
    #!/usr/bin/env bash
    pip install -r requirements.txt
    cd fronts/careerpilot && pnpm install

# Installs Ollama into ./.ollama (no sudo needed); it serves the local LLM.
install_ollama:
    #!/usr/bin/env bash
    mkdir -p .ollama
    curl -fsSL https://ollama.com/download/ollama-linux-amd64.tar.zst | tar --zstd -x -C .ollama
    .ollama/bin/ollama --version

# Starts the Ollama server in the background, keeping its models in ./llmModel.
start_llm:
    #!/usr/bin/env bash
    if [ -f .ollama.pid ] && kill -0 "$(cat .ollama.pid)" 2>/dev/null; then
        echo "Ollama already running (pid $(cat .ollama.pid))"; exit 0
    fi
    OLLAMA_MODELS="$PWD/llmModel" nohup .ollama/bin/ollama serve > .ollama.log 2>&1 &
    echo $! > .ollama.pid
    until curl -s localhost:11434/api/version > /dev/null; do sleep 1; done
    echo "Ollama running (pid $(cat .ollama.pid)), log in .ollama.log"

stop_llm:
    #!/usr/bin/env bash
    if [ -f .ollama.pid ] && kill "$(cat .ollama.pid)" 2>/dev/null; then
        echo "Ollama stopped"
    else
        echo "Ollama is not running"
    fi
    rm -f .ollama.pid

# Pulls gpt-oss-20b (~13 GB) into ./llmModel through the Ollama server.
download_model: start_llm
    .ollama/bin/ollama pull gpt-oss:20b

# Builds the agents' code-execution sandbox image (GPU). Use build_sandbox_cpu without the NVIDIA toolkit.
build_sandbox:
    docker compose build sandbox

build_sandbox_cpu:
    docker compose build sandbox-cpu

# The toolkit install (Ubuntu/Debian) asks for sudo and is skipped if already installed.
# Builds sandbox-cpu, installs the NVIDIA Container Toolkit, builds the GPU sandbox and checks it sees the GPU.
setup_sandbox: build_sandbox_cpu
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v nvidia-ctk > /dev/null; then
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
            | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
            | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
            | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
        sudo apt-get update
        sudo apt-get install -y nvidia-container-toolkit
    fi
    if ! docker info 2>/dev/null | grep -q "Runtimes:.*nvidia"; then
        sudo nvidia-ctk runtime configure --runtime=docker
        sudo systemctl restart docker
    fi
    docker compose build sandbox
    docker compose run --rm sandbox nvidia-smi

create_postgressDB:
    #!/usr/bin/env bash
    docker pull postgres:17
    echo "pulled postgres:17 docker image"
    docker run --name careerpilot_postgres \
        -e POSTGRES_PASSWORD=mysecretpassword \
        -p 5432:5432 \
        -d postgres:17
    echo "Done! Running dockers:"
    docker ps

# Starts / stops the Postgres container created by create_postgressDB.
start_db:
    docker start careerpilot_postgres

stop_db:
    docker stop careerpilot_postgres

# Runs the FastAPI backend (agents) in the foreground so its logs show in the terminal.
# Stop it with Ctrl+C, or `just stop_app` from another terminal.
start_app:
    #!/usr/bin/env bash
    if [ -f .api.pid ] && kill -0 "$(cat .api.pid)" 2>/dev/null; then
        echo "API already running (pid $(cat .api.pid))"; exit 0
    fi
    uvicorn apis.main:app --host 0.0.0.0 --port 8000 &
    echo $! > .api.pid
    trap 'kill $(cat .api.pid) 2>/dev/null; rm -f .api.pid' INT TERM EXIT
    wait

stop_app:
    #!/usr/bin/env bash
    if [ -f .api.pid ] && kill "$(cat .api.pid)" 2>/dev/null; then
        echo "API stopped"
    else
        echo "API is not running"
    fi
    rm -f .api.pid

# Runs the Next.js frontend at http://localhost:3000 in the foreground.
# setsid gives pnpm and its next child their own process group so stop_gui can kill both.
# Stop it with Ctrl+C, or `just stop_gui` from another terminal.
run_gui:
    #!/usr/bin/env bash
    if [ -f .gui.pid ] && kill -0 "$(cat .gui.pid)" 2>/dev/null; then
        echo "Frontend already running (pid $(cat .gui.pid))"; exit 0
    fi
    (cd fronts/careerpilot && exec setsid pnpm dev) &
    echo $! > .gui.pid
    trap 'kill -- -$(cat .gui.pid) 2>/dev/null; rm -f .gui.pid' INT TERM EXIT
    wait

stop_gui:
    #!/usr/bin/env bash
    if [ -f .gui.pid ] && kill -- -"$(cat .gui.pid)" 2>/dev/null; then
        echo "Frontend stopped"
    else
        echo "Frontend is not running"
    fi
    rm -f .gui.pid

# Gracefully stops everything: the API first (so nothing is mid-request against the model
# or DB), then Ollama, Postgres and the frontend. Steps that aren't running are skipped.
shutdown:
    #!/usr/bin/env bash
    just stop_app
    just stop_llm
    just stop_db || true
    just stop_gui
    echo "CareerPilot stopped"

# Writes the FastAPI OpenAPI spec to fronts/careerpilot/openapi.json without starting the server.
# create_engine doesn't connect on import, so a placeholder DATABASE_URL is enough.
openapi:
    DATABASE_URL="${DATABASE_URL:-sqlite://}" python -c "import json; from apis.main import app; print(json.dumps(app.openapi(), indent=2))" > fronts/careerpilot/openapi.json

# Regenerates the typed frontend client (fronts/careerpilot/lib/client) from the backend schemas.
gen-api: openapi
    cd fronts/careerpilot && pnpm gen:api

# Moves job descriptions out of the database into Docs/job_descriptions/*.md (safe to re-run).
migrate:
    python -m db.migrations
