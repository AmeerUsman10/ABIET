# ABIET - Database AI Assistant
## Artificial Business Intelligence Enabled Tool

Next-generation database AI assistant with natural language capabilities

## Prerequisites

- Docker and Docker Compose
- OpenAI API Key (for AI features)

## Environment Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd ABIET
   ```

2. Create a `.env` file in the root directory:
   ```bash
   OPENAI_API_KEY=your_openai_api_key_here
   ```

## Running with Docker Compose

1. Build and start all services:
   ```bash
   docker-compose up --build
   ```

2. The application will be available at:
   - Backend API: http://localhost:8000
   - Frontend UI: http://localhost:8080
   - API Documentation: http://localhost:8000/docs

3. To run in background:
   ```bash
   docker-compose up -d --build
   ```

4. To stop the services:
   ```bash
   docker-compose down
   ```

## Services

- **backend**: FastAPI application serving the API
- **frontend**: Static file server for the web UI
- **db**: PostgreSQL database (optional, can be disabled)
- **redis**: Redis for Celery task queue

## Development

For development without Docker, see [DEVELOPMENT.md](docs/DEVELOPMENT.md)
