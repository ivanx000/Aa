from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./pipeline.db"

    # LinkedIn watch (--watch-linkedin) — overridable per-run with --keywords/--location
    linkedin_keywords: str = "Software Engineer Intern"
    linkedin_location: str = "Canada"

    # Filtering
    target_keywords: list[str] = [
        "machine learning", "ml engineer", "ai engineer", "llm",
        "artificial intelligence", "generative ai", "genai",
        "full stack", "fullstack", "full-stack",
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
