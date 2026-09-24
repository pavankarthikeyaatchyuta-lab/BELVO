"""
Serverless entrypoint for Vercel deployment.
Routes all incoming HTTP requests to the FastAPI application.
"""

from app.api import app
