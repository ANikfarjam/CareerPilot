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

