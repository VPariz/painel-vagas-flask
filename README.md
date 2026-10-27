# Technical Application & Internship Pipeline Dashboard (Flask + SQLite)

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Framework](https://img.shields.io/badge/Framework-Flask-000000?style=flat-square&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Database](https://img.shields.io/badge/Database-SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://sqlite.org/)
[![Calendar](https://img.shields.io/badge/Calendar-iCal%20%7C%20Google%20API-4285F4?style=flat-square&logo=googlecalendar&logoColor=white)](https://developers.google.com/calendar)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

Full-stack web application and CLI terminal utility to track recruitment pipelines, technical interviews, recruiter networking notes, and two-way deadline synchronization with **Google Calendar** and standard **iCalendar (.ics)** feeds.

---

## 🏗️ Application Architecture

```mermaid
flowchart TD
    subgraph UI["User Interface"]
        HTML["Jinja2 HTML Templates<br/>(index.html / login.html)"]
        CSS["Tokyo Night Dark Theme<br/>(static/css/style.css)"]
        JS["Dynamic Vanilla JS Client<br/>(static/js/app.js)"]
        CLI["Terminal CLI Utility<br/>(app/gerenciar.py)"]
    end

    subgraph BACKEND["Web Application Server (Python / Flask)"]
        APP["RESTful Routes & PBKDF2 Auth<br/>(app/app.py)"]
        CAL["iCalendar .ics Feed Generator<br/>(app/calendario.py)"]
        SYNC["Google Calendar Sync (OAuth 2.0)<br/>(app/google_sync.py)"]
    end

    subgraph PERSISTENCE["Storage & External Calendars"]
        DB[("Embedded SQLite DB<br/>(data/painel_vagas.db)")]
        ICS["Dynamic .ics Subscription"]
        GAPI["Google Calendar API"]
    end

    HTML & CSS & JS --> APP
    CLI --> DB
    APP --> DB
    APP --> CAL --> ICS
    APP --> SYNC --> GAPI
```

---

## ⚡ Key Features

- **Recruitment Pipeline Tracking:** Manage engineering roles, company dossiers, work modes (remote/hybrid/onsite), salary benchmarks, and stage transitions (Applied, Interview, Technical Assessment, Offer).
- **Recruiter & Engineer CRM:** Track contacts, historical interactions, follow-up cadence, and referral connections.
- **Two-Way Calendar Synchronization:**
  - Dynamic `.ics` subscription URL compatible with Apple Calendar, Google Calendar, and Microsoft Outlook.
  - Native Google Calendar OAuth 2.0 integration with automatic event alarms.
- **Terminal CLI (`gerenciar.py`):** Query upcoming interview dates, task deadlines, and recruiter lists directly from the terminal.
- **Security:** Protected by salted PBKDF2-SHA256 hashed PIN authentication and temporary rate-limiting against brute-force attempts.
- **Mock Demonstration Fixtures:** Initial boot automatically populates explicit `[EXAMPLE] (Fictitious)` mock records with zeroed compensation values (`$ 0.00`) for instant component inspection without exposing sensitive real-world records.

---

## 📂 Repository Structure

```
painel-vagas-flask/
├── app/
│   ├── app.py                  # Flask server, REST endpoints & automatic schema migration
│   ├── calendario.py           # RFC 5545 iCalendar (.ics) feed generator
│   ├── google_sync.py          # Google Calendar API integration (OAuth 2.0)
│   ├── gerenciar.py            # Headless terminal CLI utility
│   ├── static/
│   │   ├── css/style.css       # Clean responsive dark stylesheet
│   │   └── js/app.js           # Client-side DOM interactions and AJAX calls
│   └── templates/
│       ├── index.html          # Main pipeline dashboard
│       └── login.html          # Hashed PIN gatekeeper view
├── data/                       # Local SQLite database (gitignored)
├── requirements.txt            # Python dependencies (Flask, requests, etc.)
├── .gitignore                  # Prevents local credentials and DB artifacts from committing
└── README.md
```

---

## 🚀 Setup & Execution

### 1. Installation

```bash
git clone https://github.com/VPariz/painel-vagas-flask.git
cd painel-vagas-flask
python -m venv venv

# Activate virtual environment:
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Launch Web Application

```bash
python app/app.py
```
Open your browser at `http://127.0.0.1:5000`  
*Default PIN:* `1234` (configurable via login screen or `APP_PIN` environment variable).

### 3. Headless Terminal CLI

```bash
# View pending tasks and approaching deadlines
python app/gerenciar.py tarefas

# View recruiter contacts and message statuses
python app/gerenciar.py contatos

# List all tracked job applications
python app/gerenciar.py vagas
```

---

## 📜 License
This project is licensed under the **MIT License** — see the `LICENSE` file for details.
