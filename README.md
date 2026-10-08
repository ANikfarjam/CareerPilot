# CareerPilot

*By Ashkan Nikfarjam*

CareerPilot is an open-source, AI-powered job search engine. Its agents query job-board portal APIs to find roles tailored to your skills, then pull the key qualifications out of each job description and match them against your background, so you only spend time on jobs you're actually qualified for.

CareerPilot also tracks your applications, so you always know which jobs you've already applied to.

[Screencast from 2026-10-06 15-18-12.webm](https://github.com/user-attachments/assets/07f2f70b-2b71-4538-bc32-dc7529ceebb5)


## Features

- **Multi-portal search**: agents search across job-board APIs in a single run.
- **Qualification matching**: key requirements are extracted from each posting and compared to your skills and experience.
- **Application tracking**: keep a record of which jobs you've applied to.
- **Resume builder**: builds a resume tailored to a saved job from your background, and suggests side projects that close its skill gaps. A chat assistant edits it for you.
- **Google Drive export** (optional): saves your resumes as Google Docs in `career_pilot_resume/<job title>/` in your Drive.
- **Runs locally**: the LLM runs on your own hardware, so your data stays on your machine.

## Requirements

- [Docker](https://docs.docker.com/get-docker/)
- [just](https://github.com/casey/just) command runner
- Python 3.12+
- [Node.js](https://nodejs.org/) 20+ and [pnpm](https://pnpm.io/installation)
- An NVIDIA GPU with CUDA support, plus the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

> [!NOTE]
> The agent runs on CUDA and needs a CUDA-compatible GPU.

## Getting Started

### 1. Clone the repository and install dependencies

CareerPilot is open source: clone the repository into your desired directory and install the Python and frontend dependencies:

```bash
git clone https://github.com/ANikfarjam/careerAI
cd careerAI
pip install rust-just   # or install just with your package manager
just install_libraries
```

`install_libraries` installs `requirements.txt` into the `.myenv` virtual environment and runs `pnpm install` for the frontend.

### 2. Download the model

CareerPilot runs OpenAI's [gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b) locally through [Ollama](https://ollama.com). Its MoE experts that don't fit in VRAM run on the CPU, so it works on an 8 GB GPU with 16 GB of RAM. Install Ollama into `./.ollama` and pull the model (~13 GB) into `./llmModel/`:

```bash
just install_ollama
just download_model
```

`just start_llm` / `just stop_llm` start and stop the Ollama server; it has to be running before `just start_app`.

### 3. Build the agent sandbox

The agents run generated code inside a hardened Docker container. Build its image once:

```bash
just build_sandbox        # with the NVIDIA Container Toolkit
just build_sandbox_cpu    # without a GPU
```

### 4. Set up the database

Create the Postgres container:

```bash
just create_postgressDB
```

Then create a `.env` file in the project root pointing the backend at it:

```bash
DATABASE_URL=postgresql://postgres:mysecretpassword@localhost:5432/postgres
```

### 5. Start the backend and the GUI

```bash
just start_app   # API at http://localhost:8000 (docs at /docs)
just run_gui     # frontend at http://localhost:3000
```

### 6. Optional: Google Drive export

The Resume Builder can save resumes to your Google Drive as Google Docs, from its **Save to Drive** button or when you ask the resume chat to. Users don't set anything up: the first **Save to Drive** opens a Google sign-in popup, and after **Allow** the resume is saved to `career_pilot_resume/<job title>/<company> – Draft N – Resume` (and `– Side projects`). Saving a draft again updates its doc instead of making a copy. The sign-in is kept in `Docs/google/token.json` (gitignored), and the **Disconnect** link in the editor revokes it.

CareerPilot asks only for the `drive.file` scope, so it can see and change only the files and folders it creates.

#### Maintainers: the OAuth client

The popup needs one OAuth client for the whole project, shipped at `agents/resume_builder/google_client.json`. Without that file, the **Save to Drive** button is hidden. Google doesn't treat a Desktop app client's secret as confidential, so the file can be committed. To create it:

1. In the [Google Cloud Console](https://console.cloud.google.com/), create a project and enable the **Google Drive API**.
2. Set up the **OAuth consent screen** (Google Auth Platform): user type **External**, the app name, a support email, and the `.../auth/drive.file` scope under **Data access**.
3. Under **Audience**, click **Publish app** (**In production**). While the app is in **Testing**, only listed test users can sign in, and their sign-in expires after 7 days.
4. Under **Clients**, create a client of type **Desktop app**, download its JSON and save it as `agents/resume_builder/google_client.json`.

To use your own client without committing it, set `GOOGLE_OAUTH_CLIENT_FILE` in `.env`. `GOOGLE_OAUTH_TOKEN_FILE` moves the saved sign-in. Until Google verifies the app, users may see a "Google hasn't verified this app" screen they can click through (**Advanced → Go to CareerPilot**).

## Managing the Services

Start and stop the agent (backend server) and the database container:

```bash
# start the llm
just start_llm

# start the agent
just start_app

# start the database
just start_db

# stop the llm
just stop_llm

# stop the agent
just stop_app

# stop the database
just stop_db
```

`just start_app` runs the backend in the foreground so its logs print to the terminal; stop it with Ctrl+C or `just stop_app` from another terminal. Run `just --list` to see every available command.

## Upcoming Features

- **Interview coach**: an agent that helps you practice with mock interviews.
