# CareerAI

*By Ashkan Nikfarjam*

CareerAI is an open-source, AI-powered job search engine. Its agents query job-board portal APIs to find roles tailored to your skills, then pull the key qualifications out of each job description and match them against your background, so you only spend time on jobs you're actually qualified for.

CareerAI also tracks your applications, so you always know which jobs you've already applied to.

## Features

- **Multi-portal search**: agents search across job-board APIs in a single run.
- **Qualification matching**: key requirements are extracted from each posting and compared to your skills and experience.
- **Application tracking**: keep a record of which jobs you've applied to.
- **Runs locally**: the LLM runs on your own hardware, so your data stays on your machine.

## Requirements

- [Docker](https://docs.docker.com/get-docker/)
- [just](https://github.com/casey/just) command runner
- An NVIDIA GPU with CUDA support, plus the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

> [!NOTE]
> The agent runs on CUDA and needs a CUDA-compatible GPU.

## Getting Started

### 1. Download the model

CareerAI currently runs OpenAI's [gpt-oss-120b](https://huggingface.co/openai/gpt-oss-120b) locally. Download it from Hugging Face into the `./llmModel/` directory:

```bash
pip install -U "huggingface_hub[cli]"
huggingface-cli download openai/gpt-oss-120b
```

### 2. Pull and run the app

The app is containerized and can be pulled from Docker Hub and run locally:

```bash
# pull the image and run it with Docker
```

### 3. Set up the database and frontend

Create the Postgres database container and start the GUI:

```bash
just create_postgressDB
just run_gui
```

## Managing the Containers

Start and stop the agent (backend server) and database containers:

```bash
# start the agent
just start_app

# start the database
just start_db

# stop the agent
just stop_app

# stop the database
just stop_db
```

## Upcoming Features

- **Resume and interview coach**: an agent that helps you build your resume and practice with mock interviews.
