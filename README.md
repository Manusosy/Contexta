# Contexta — AI Editorial Automation

Contexta is an automated content curation platform that aggregates RSS feeds, uses AI to generate high-quality editorial articles based on factual news, optimizes them for SEO, and optionally publishes them directly to WordPress.

## Setup Instructions

### Prerequisites
- Python 3.10+
- A valid OpenRouter API key

### Installation

1. Clone the repository and navigate to the project directory:
   ```bash
   git clone <repo_url>
   cd contexta
   ```

2. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```

3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure the environment variables:
   Copy `.env.example` to `.env` and fill in your details:
   ```bash
   cp .env.example .env
   ```
   **Important:** Change the `SECRET_KEY` in production. Setting a new `ADMIN_PASSWORD` is highly recommended.

### Running the Application

1. Start the Flask application:
   ```bash
   python app.py
   ```
   *Note: Upon first run, the database defaults and initial admin user will be seeded automatically.*

2. Access the application in your browser at `http://127.0.0.1:5000/`.

3. Log in using the default admin or demo credentials:

   **Demo Client User:**
   - **Username:** nairovibe@gmail.com
   - **Password:** Demo@12345

   **Demo Admin User:**
   - **Username:** admin@kazinikazi.co.ke
   - **Password:** Demo@12345

   *(Or use the values set in `ADMIN_USER` and `ADMIN_PASSWORD`)*

### First Steps

1. **Configure AI Settings:** Go to "Settings -> AI" and insert your OpenRouter API key. Choose your preferred AI model.
2. **Add RSS Feeds:** Go to "Feeds" and add URLs for sources you want to aggregate.
3. **Configure WordPress:** (Optional) If you want to auto-publish, set your WP URL and Application Password in the Settings page.
4. **Run Automation:** Click "Run Engine" on the dashboard to start processing new articles!
