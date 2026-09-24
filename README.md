# ABIET — Database AI Assistant

**Artificial Business Intelligence Enabled Tool**

ABIET is a public prototype for exploring how plain-language business questions can be translated into SQL-backed answers through a web application.

## What this repository demonstrates

- A FastAPI backend with a query-response API
- A natural-language-to-SQL processing path
- A browser-based frontend
- Docker Compose setup for the application services
- PostgreSQL and Redis service definitions for local development

## Prototype status

This repository is an inspectable technical sample, not a claim of a production deployment or measured client results. Generated SQL should be reviewed and tested against a safe, read-only or non-production database before operational use.

## Run locally

### Prerequisites

- Docker and Docker Compose
- An OpenAI API key for the AI-assisted features

### Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/AmeerUsman10/ABIET.git
   cd ABIET
   ```

2. Create a `.env` file in the repository root:

   ```bash
   OPENAI_API_KEY=your_openai_api_key_here
   ```

3. Build and start the services:

   ```bash
   docker-compose up --build
   ```

4. Open:

   - Backend API: http://localhost:8000
   - Frontend UI: http://localhost:8080
   - API documentation: http://localhost:8000/docs

5. Stop the services:

   ```bash
   docker-compose down
   ```

For development without Docker, see [DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Services

- **backend** — FastAPI application serving the API
- **frontend** — Static web interface
- **db** — PostgreSQL database service
- **redis** — Redis service for task-queue support

## Paid scoped help

I am available remotely from Karachi, Pakistan for bounded database, SQL-reporting and business-system work, including:

- SQL/report troubleshooting and exception analysis
- reporting requirements and data-quality checks
- database-backed workflow prototypes
- ERP/export reconciliation and operational reporting
- technical documentation and implementation coordination

A small **USD 100 fixed-scope diagnostic** can cover one supplied schema/export and one clearly defined reporting or data-quality question, with findings delivered before billing. Larger implementation or ongoing support is quoted only after the scope and access boundaries are agreed.

Contact: [ameerusman10@gmail.com](mailto:ameerusman10@gmail.com)

AI assistance may be used for drafting and implementation support. Client data, credentials and confidential materials are not published.
