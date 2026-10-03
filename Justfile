# Creates the .myenv virtualenv and installs the Python dependencies (torch from the CUDA 12.6 index).
install_libraries:
    #!/usr/bin/env bash
    pip install -r requirements.txt
    cd fronts/careerai && pnpm install

# Downloads gpt-oss-120b from Hugging Face into ./llmModel.
download_model:
    pip install -U "huggingface_hub[cli]"
    hf download openai/gpt-oss-120b --local-dir llmModel

# Builds the agents' code-execution sandbox image (GPU). Use build_sandbox_cpu without the NVIDIA toolkit.
build_sandbox:
    docker compose build sandbox

build_sandbox_cpu:
    docker compose build sandbox-cpu

create_postgressDB:
    #!/usr/bin/env bash
    docker pull postgres:17
    echo "pulled postgres:17 docker image"
    docker run --name careerAI_postgres \
        -e POSTGRES_PASSWORD=mysecretpassword \
        -p 5432:5432 \
        -d postgres:17
    echo "Done! Running dockers:"
    docker ps

# Starts / stops the Postgres container created by create_postgressDB.
start_db:
    docker start careerAI_postgres

stop_db:
    docker stop careerAI_postgres

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

# Runs the Next.js frontend at http://localhost:3000.
run_gui:
    cd fronts/careerai && pnpm dev

# Writes the FastAPI OpenAPI spec to fronts/careerai/openapi.json without starting the server.
# create_engine doesn't connect on import, so a placeholder DATABASE_URL is enough.
openapi:
    DATABASE_URL="${DATABASE_URL:-sqlite://}" python -c "import json; from apis.main import app; print(json.dumps(app.openapi(), indent=2))" > fronts/careerai/openapi.json

# Regenerates the typed frontend client (fronts/careerai/lib/client) from the backend schemas.
gen-api: openapi
    cd fronts/careerai && pnpm gen:api

# Moves job descriptions out of the database into Docs/job_descriptions/*.md (safe to re-run).
migrate:
    python -m db.migrations
