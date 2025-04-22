import os
import sys

# Load environment variables from .env file if it exists
from dotenv import load_dotenv
load_dotenv() 

os.environ["REQUESTS_CA_BUNDLE"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Lib", "site-packages", "certifi", "cacert.pem")
os.environ["SSL_CERT_FILE"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Lib", "site-packages", "certifi", "cacert.pem")

from amazing_storage.web.app import run_app
if __name__ == "__main__":
    print("Starting Amazing Storage System...")
    run_app()
