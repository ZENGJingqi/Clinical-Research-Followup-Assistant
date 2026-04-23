# Clinical Research Followup Assistant

Clinical Research Followup Assistant is a Django-based web application for managing patient follow-up workflows in clinical research. It supports structured longitudinal records across patient profiles, treatment history, follow-up visits, research projects, scales, attachments, data export, and optional AI-assisted summaries.

## Overview

This repository contains the user installation edition of the system. It is designed for clinical research teams that need a practical, deployment-ready tool for organizing follow-up data and keeping research records consistent over time.

Main use cases:

- Manage patient profiles and treatment records
- Plan and record follow-up visits
- Track research project enrollment and status
- Maintain scale templates and structured assessment records
- Store clinical terms, prescription templates, and attachments
- Export structured data for analysis and reporting
- Generate AI-assisted follow-up summaries when enabled

## Key Features

- Patient management with basic demographic and clinical information
- Treatment management with longitudinal visit history
- Follow-up scheduling, status tracking, and overdue reminders
- Research project management and project-based patient enrollment
- Scale and questionnaire template management
- Attachment upload and organized export
- Role-based access control with `root`, `admin`, and `normal` roles
- Export permissions and record modification time-window control
- Optional AI integration for patient summary assistance

## Technology Stack

- Backend: Django 5.2.12
- Language: Python, HTML, CSS, JavaScript, Shell/Batch
- Database: SQLite
- Deployment: Windows or Linux
- Python version: 3.11+ recommended, 3.12 preferred

## Deployment Options

The system can be deployed in different ways:

- Local access on one computer
- LAN access inside a local network
- Public deployment on a server with port `8000` enabled

## Quick Start

The setup scripts create a virtual environment, install dependencies, generate `.env.local`, apply migrations, and prompt for the `root` account on first-time setup.

1. Unzip the installation package.
2. Install Python `3.11` or above and make sure it is added to your system `PATH`.
3. Open the project folder.
4. Run the setup script for your operating system.
5. Start the service and open the system in your browser.

### Windows Local Setup

```bat
setup_windows.bat
start_local.bat
```

Open:

```text
http://127.0.0.1:8000/
```

### Linux Local Setup

```bash
bash setup_linux.sh
bash start_local.sh
```

Open:

```text
http://127.0.0.1:8000/
```

### Windows Public or LAN Setup

```bat
setup_public_windows.bat
start_public_windows.bat
```

### Linux Public or LAN Setup

```bash
bash setup_public_linux.sh
bash start_public_linux.sh
```

If you use public deployment, make sure port `8000` is allowed by the firewall or cloud security group.

## First Login

- Username: `root`
- Password: set manually during the first installation

Important notes:

- No default password is included
- If the `root` account already exists, setup keeps it and skips account creation
- Old account data is not migrated automatically
- If you replace an older version, remove the old folder before unpacking the new package

## AI Configuration

After installation, the system generates `.env.local`. You can edit the AI settings if needed:

```env
AI_PROVIDER=aliyun
AI_API_KEY=
AI_MODEL=qwen-plus
AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

Supported providers in this package:

- `aliyun`
- `zhipu`

Example for Zhipu:

```env
AI_PROVIDER=zhipu
AI_MODEL=glm-5
AI_BASE_URL=https://open.bigmodel.cn/api/paas/v4/chat/completions
```

Restart the service after updating the configuration.

## Package Scope

This repository includes the runtime application code, templates, static assets, setup scripts, and base configuration needed to run the system:

- Application code: `config/`, `followup/`, `templates/`, `static/`
- Setup and startup scripts for Windows and Linux
- Basic configuration files such as `.env.example` and `requirements.txt`

It intentionally excludes local research documents, copyright-submission materials, and packaged release archives.

## Deployment Notes

- For public deployment, expose port `8000` only behind proper firewall and access controls.
- Enable AI services only if their use is compatible with your institution's data governance requirements.
