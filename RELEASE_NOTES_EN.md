# Release Notes

## Clinical Research Followup Assistant V1.0

User Installation Package  
Date: 2026-04-23
Release asset: `Clinical-Research-Followup-Assistant-User-Package-20260423.zip`

This release provides a user-ready deployment package for the Clinical Research Followup Assistant.

### Included in this package

- Runtime application files only
- One-click setup scripts for Windows and Linux
- Local deployment mode
- LAN or public deployment mode
- Optional AI configuration for assisted patient summaries
- Updated setup messages and validated installation flow

### Main functions

- Patient management
- Treatment and follow-up management
- Research project enrollment tracking
- Scale and questionnaire management
- Attachment management
- Data export
- Role-based permission control

### Important notes

- No default account password is included
- The `root` password must be created during the first setup
- Old account credentials are not migrated automatically
- For public deployment, port `8000` must be enabled

### Environment

- Windows 10/11 or Linux
- Python 3.11+ recommended
- Django 5.2.12
- SQLite
