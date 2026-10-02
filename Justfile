create_postgressDB:
    #!/usr/bin/env bash
    docker pull postgres
    echo "pulled latest postgress docker image"
    docker run --name careerAI_postgres \
        -e POSTGRES_PASSWORD=mysecretpassword \
        -p 5432:5432 \
        -d postgres:17
    echo "Done! Running dockers:"
    docker ps

# Writes the FastAPI OpenAPI spec to fronts/careerai/openapi.json without starting the server.
# create_engine doesn't connect on import, so a placeholder DATABASE_URL is enough.
openapi:
    DATABASE_URL="${DATABASE_URL:-sqlite://}" .myenv/bin/python -c "import json; from apis.main import app; print(json.dumps(app.openapi(), indent=2))" > fronts/careerai/openapi.json

# Regenerates the typed frontend client (fronts/careerai/lib/client) from the backend schemas.
gen-api: openapi
    cd fronts/careerai && pnpm gen:api
