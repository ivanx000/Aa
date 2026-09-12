from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./pipeline.db"

    # Ollama
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"   # change to any model you have pulled, e.g. mistral, phi3

    # Adzuna (free tier — register at https://developer.adzuna.com/)
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""

    # LinkedIn watch (--watch-linkedin) — overridable per-run with --keywords/--location
    linkedin_keywords: str = "Software Engineer Intern"
    linkedin_location: str = "Canada"

    # Filtering
    target_keywords: list[str] = [
        "machine learning", "ml engineer", "ai engineer", "llm",
        "robotics", "full stack", "fullstack", "full-stack",
        "backend", "back-end", "back end",
        "frontend", "front-end", "front end",
        "software engineer", "software developer", "swe",
        "mobile developer", "ios developer", "android developer",
        "data engineer", "cloud engineer", "devops",
        "saas",
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
