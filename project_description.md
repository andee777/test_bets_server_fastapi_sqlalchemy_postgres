# Code Description: Asynchronous Sports Data Fetcher and Processor

This Python application is an asynchronous web service designed to fetch, process, and store sports match data and betting odds from external APIs into a PostgreSQL database. It utilizes FastAPI for the web framework, SQLAlchemy for asynchronous database interaction, `httpx` for making asynchronous HTTP requests, and `asyncio` for managing background tasks.

## Overall Functionality

The core purpose of the application is to:

1.  **Fetch Data:** Periodically retrieve sports match information (like teams, start times, current scores, status) and associated betting odds (specifically 1X2 - Home Win, Draw, Away Win) from configured external API endpoints. It handles different categories like live football, pregame football, and pregame basketball.
2.  **Process Data:** Parse and transform the raw data received from the APIs. This includes:
    * Parsing scores (e.g., "1:0").
    * Determining a canonical `match_time` based on the `event_status` (e.g., "Halftime" -> "45:00", "Penalties" -> "120:00").
    * Extracting relevant odds values.
    * Converting data types (e.g., string odds to floats).
3.  **Store Data:** Persist the processed information into a PostgreSQL database using SQLAlchemy's asynchronous engine and session management. It uses several tables:
    * `match`: Stores general information about each match (ID, teams, competition, start time, status, live flag). Uses an **upsert** mechanism (insert or update if exists based on `match_id`).
    * `odds`: Stores historical odds data points fetched over time for each match, linked via `match_id`. Includes scores and odds values at the time of fetching.
    * `latest_odd`: Stores *only the most recent* odds record for each match. This table is updated automatically by a database trigger.
    * `initial_odd`: Stores *only the very first* odds record captured for each match. This table is populated by a database trigger on the first insert for a match and then remains unchanged for that match.
4.  **Maintain State:** Includes logic to update the status of matches in the database, particularly handling cases where a live match is no longer reported by the live API (potentially marking it as 'pending' or 'ended').
5.  **Run Continuously:** Operates using background tasks (`asyncio`) to fetch data at regular intervals (e.g., every 10 seconds for live data, every 5 minutes for pregame data).
6.  **Provide API:** Exposes a simple HTTP API using FastAPI:
    * `/health`: A basic endpoint to check if the service is running.
    * `/fetch/*`: Endpoints to manually trigger the data fetching process for different categories.

## Key Components & Logic Breakdown

* **Configuration (`.env`, `config.py`):**
    * Loads sensitive information (database credentials, API URLs) from a `.env` file using `python-dotenv`.
    * Stores configuration variables like `DATABASE_URL` and `API_URLS`.
    * Configures logging format and level.
* **Database Setup (`database.py`):**
    * Creates an asynchronous SQLAlchemy engine (`create_async_engine`) configured for PostgreSQL (`postgresql+asyncpg`) with connection pooling.
    * Defines an asynchronous session maker (`sessionmaker`) for database transactions.
    * Declares the `Base` class for declarative models.
* **Data Models (`models.py`):**
    * Defines the structure of the database tables (`Match`, `Odds`, `LatestOdd`, `InitialOdd`) using SQLAlchemy's ORM syntax (Column, ForeignKey, etc.).
    * Specifies primary keys, indexes, data types, and relationships between tables.
* **Database Triggers (`triggers.py`):**
    * Defines a PostgreSQL trigger function (`update_odd_summary`) in PL/pgSQL.
    * This trigger automatically runs *after* every `INSERT` or `UPDATE` on the `odds` table.
    * **Functionality:**
        * It inserts the new/updated odds data into `latest_odd`, overwriting any existing entry for that `match_id` (`ON CONFLICT (match_id) DO UPDATE`).
        * It attempts to insert the new/updated odds data into `initial_odd`, but does *nothing* if an entry for that `match_id` already exists (`ON CONFLICT (match_id) DO NOTHING`).
    * The `create_trigger_functions` async function ensures this trigger and its associated function are created in the database when the application starts.
* **Utility Functions (`utils.py`):**
    * `get_match_time`: Maps specific event statuses (like "Halftime", "Penalties") to standardized minute marks.
    * `parse_score`: Converts score strings ("1:0", "-:-") into integer tuples `(home_score, away_score)`.
    * `Workspace_data`: Asynchronously fetches JSON data from a given URL using `httpx`, handling potential errors.
    * `event_status_not_live`: Helper to check if a match status is different from "live".
    * `to_double`: Safely converts values to floats, defaulting to `0.0` on error.
    * `prepare_odds_data`: Transforms the raw match data list into a list of dictionaries ready for insertion into the `Odds` table.
* **Data Processing & Tasks (`tasks.py`):**
    * `upsert_matches`: Takes fetched match data, prepares it for the `Match` model, and performs an upsert operation into the `match` table using `sqlalchemy.dialects.postgresql.insert` with `on_conflict_do_update`.
    * `update_missing_live_matches` / `handle_missing_live_matches`: Compares the list of currently live matches from the API with those marked as live (`live=True`) in the database for a specific category. If a match is marked live in the DB but *not* in the latest API fetch, its status is updated (e.g., to `live=False, event_status='pending'` or `event_status='ended'` if the match time indicates completion).
    * `Workspace_and_store_data`: Orchestrates the process for a given URL and category: fetches data, upserts matches, updates statuses for missing live matches (if applicable), prepares odds data, and inserts it into the `odds` table within a single database session/transaction.
    * `periodic_fetch_live`: An infinite loop background task that calls `Workspace_and_store_data` for the live API URL every 10 seconds.
    * `periodic_fetch_others`: An infinite loop background task that calls `Workspace_and_store_data` for pregame football and basketball URLs every 300 seconds (5 minutes).
* **FastAPI Application (`main.py`):**
    * Initializes the `FastAPI` application instance.
    * Uses a `lifespan` asynchronous context manager:
        * **On startup:** Connects to the database, ensures all tables defined in the models are created (`Base.metadata.create_all`), creates the database triggers (`create_trigger_functions`), and starts the background tasks (`periodic_fetch_live`, `periodic_fetch_others`).
        * **On shutdown:** Cancels the background tasks gracefully.
    * Defines the HTTP API endpoints (`/health`, `/fetch/live`, `/fetch/football`, `/fetch/basketball`) that either return status or manually trigger the data fetching logic.
    * Includes the `if __name__ == "__main__":` block to run the application using the `uvicorn` ASGI server.

## Use Cases

* **Live Odds Monitoring:** Tracking real-time odds fluctuations for live football matches.
* **Pregame Odds Collection:** Gathering opening and subsequent pregame odds for football and basketball.
* **Sports Data Aggregation:** Serving as a backend data source for a sports analytics platform, a betting odds comparison site, or a custom application requiring historical and live sports data.
* **Arbitrage Opportunity Identification (Potential):** The stored odds data could be analyzed to find potential arbitrage opportunities (though this application only fetches and stores).
* **Model Training Data:** Providing historical odds and match data for building predictive sports models.

## Refactoring Explanation

The original monolithic code was refactored into a more modular structure within an `app/` directory. This is a standard practice in software development to improve the organization and maintainability of the codebase.

**Goal of Refactoring:**

* **Separation of Concerns:** Grouping related functionality into distinct files (e.g., all database models together, all configuration together).
* **Improved Readability:** Smaller, focused files are easier to understand than one large file.
* **Enhanced Maintainability:** Changes to one part of the application (e.g., adding a new model) are localized to specific files, reducing the risk of unintended side effects elsewhere.
* **Better Testability:** Individual modules can potentially be tested in isolation more easily.
* **Increased Reusability:** Utility functions or database setup logic might be reusable in other projects.

**File Breakdown (Post-Refactoring):**

* **`app/__init__.py`:** Makes the `app` directory a Python package.
* **`app/main.py`:** Contains the core FastAPI application setup (`FastAPI` instance), the `lifespan` manager (handling startup/shutdown logic like DB setup, trigger creation, and task launching), and the API endpoint definitions (`@app.get(...)`). It imports necessary components from other modules.
* **`app/config.py`:** Centralizes configuration loading (`load_dotenv`) and variable definitions (`DB_CREDENTIALS`, `DATABASE_URL`, `API_URLS`). Also includes logging configuration.
* **`app/database.py`:** Responsible for setting up the database connection: creating the SQLAlchemy `engine`, the `async_session` maker, and the declarative `Base`.
* **`app/models.py`:** Contains only the definitions of the SQLAlchemy database models (`Match`, `Odds`, `LatestOdd`, `InitialOdd`).
* **`app/utils.py`:** Holds general-purpose helper functions not specific to database models or FastAPI endpoints (e.g., `parse_score`, `Workspace_data`, `get_match_time`, `prepare_odds_data`).
* **`app/triggers.py`:** Isolates the logic for defining and creating the PostgreSQL trigger functions (`create_trigger_functions`).
* **`app/tasks.py`:** Contains the functions responsible for the application's core logic: fetching data from APIs, processing it, interacting with the database (upserting/updating), and the periodic background task loops (`Workspace_and_store_data`, `upsert_matches`, `update_missing_live_matches`, `periodic_fetch_live`, etc.).
* **`.env`:** (Outside `app/`) Stores environment variables (credentials, URLs). Not code, but essential configuration.
* **`requirements.txt`:** (Outside `app/`) Lists project dependencies.

By breaking down the single script into these specialized modules, the codebase becomes significantly cleaner, easier to navigate, and simpler to modify or extend in the future.