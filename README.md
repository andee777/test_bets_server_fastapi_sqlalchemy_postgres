# FastAPI Cloud SQL Dockerized App with NGINX
## Overview
This project is a FastAPI application that fetches sports betting data from external APIs and stores it in a PostgreSQL database hosted on Google Cloud SQL. The application uses SQLAlchemy (with async support) for ORM, and it is dockerized with Docker Compose. An NGINX reverse proxy is set up to route incoming traffic to the FastAPI application.
## Architecture
The project comprises three main services:
- **app:** The FastAPI application running with Uvicorn.
- **cloudsql-proxy:** The Cloud SQL Proxy, which securely connects to your remote Google Cloud SQL PostgreSQL instance.
- **nginx:** An NGINX reverse proxy that forwards external requests (port 80) to the FastAPI app (port 8000).
## Prerequisites
- [Docker](https://www.docker.com/get-started)
- [Docker Compose](https://docs.docker.com/compose/install/)
- A Google Cloud SQL instance (e.g., `test-project:us-central1:test-db`)
- A service account JSON key file with the proper permissions for accessing your Cloud SQL instance.
## Setup Instructions
Clone the repository:
```bash
git clone <repository-url>
cd <repository-directory>
````

Create the `.env` file in the project root with the following content (adjust values as needed):
```dotenv
DB_USER=postgres
DB_PASSWORD=password
DB_HOST=cloudsql-proxy
DB_PORT=5432
DB_NAME=mydb1
CLOUD_SQL_INSTANCE=test-project-october-2024:us-central1:test-bets-db
````

Configure service account credentials:

Create a folder named secrets in the project root.
Obtain your service account JSON key file from the Google Cloud Console.
Place the JSON key file in the secrets folder and name it service-account.json. Dockerize the application: This project includes a Dockerfile to build the FastAPI application image and a docker-compose.yml file that defines the three services: the FastAPI app, Cloud SQL Proxy, and NGINX. To build and run the application, run:
```bash
docker-compose up --build
````

Access the application: NGINX listens on port 80 and routes traffic to the FastAPI application on port 8000. Open your web browser and navigate to http://localhost to access your app.

API Endpoints
The FastAPI application provides endpoints for manually triggering data fetch operations:

GET /fetch/live: Fetch and store live betting odds.
GET /fetch/football: Fetch and store football betting odds.
GET /fetch/basketball: Fetch and store basketball betting odds. A background task periodically fetches data every 10 seconds while the app is running.


## Project Structure
```plaintext
.
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
├── main.py
├── requirements.txt
├── .env
└── secrets
    └── service-account.json
````


## Customization
Modify the .env file to match your database credentials and Cloud SQL instance information. Update main.py to extend or customize API endpoints and models as needed.

## Cleanup
To stop the Docker containers, press Ctrl+C in your terminal, then run:
```bash
docker-compose down
````

## Additional Resources
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Google Cloud SQL Proxy Documentation](https://cloud.google.com/sql/docs/mysql/connect-admin-proxy)
