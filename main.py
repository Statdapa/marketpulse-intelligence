"""
MarketPulse Intelligence — Entry Point

Run:
  python main.py
  # or
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload

The API mounts on http://localhost:8000
Interactive docs at http://localhost:8000/docs
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
import uvicorn
from api.routes import app  # noqa: F401 — registers all routes & lifecycle hooks
from config.settings import settings

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/marketpulse.log"),
    ]
)

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower(),
        reload=False,
    )