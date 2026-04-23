# Clinical Research Followup Assistant

Clinical Research Followup Assistant is a web-based application for managing patient follow-up work in clinical research. It supports structured longitudinal tracking for patient records, treatment history, follow-up visits, research projects, scales, attachments, data export, and AI-assisted summaries.

Repository:

[https://github.com/ZENGJingqi/Clinical-Research-Followup-Assistant](https://github.com/ZENGJingqi/Clinical-Research-Followup-Assistant)

## Overview

This project helps clinical research teams keep follow-up data clear, structured, and easy to manage in one system. It supports both daily follow-up work and research-oriented data collection.

Main use cases:

- Manage patient profiles and treatment records
- Plan and record follow-up visits
- Track research project enrollment and status
- Maintain scale templates and follow-up scale records
- Store clinical terms, prescription templates, and attachments
- Export data for research analysis
- Generate AI-assisted patient follow-up summaries

## Key Features

- Patient management with basic demographic and clinical information
- Treatment management with longitudinal visit history
- Follow-up scheduling, status tracking, and overdue reminders
- Research project management and project-based patient enrollment
- Scale and questionnaire template management
- Attachment upload and organized export
- Role-based access control with `root`, `admin`, and `normal` users
- Export permissions and record modification time-window control
- Optional AI integration for structured patient summary assistance

## Technology Stack

- Backend: Django 5.2.12
- Language: Python, HTML, CSS, JavaScript, Shell/Batch
- Database: SQLite
- Deployment: Windows or Linux
- Python version: 3.11+ recommended, 3.12 preferred

## Deployment Modes

The system can be deployed in different ways:

- Local access on one computer
- LAN access inside a local network
- Public deployment on a server with port `8000` enabled

## Quick Start

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

## Included Runtime Files

This user installation package keeps only the files needed for running the system:

- Application code: `config/`, `followup/`, `templates/`, `static/`
- Setup and startup scripts for Windows and Linux
- Basic configuration files such as `.env.example` and `requirements.txt`

## Keywords

clinical research, followup, patient management, treatment tracking, research enrollment, longitudinal data, medical data export, Django, SQLite, AI-assisted summary
