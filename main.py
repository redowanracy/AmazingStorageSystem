import os
import sys

os.environ["REQUESTS_CA_BUNDLE"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Lib", "site-packages", "certifi", "cacert.pem")
os.environ["SSL_CERT_FILE"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Lib", "site-packages", "certifi", "cacert.pem")
# os.environ["ASS_ENCRYPTION_KEY"] = "easymoneyeasylife" # Encryption removed

from amazing_storage.web.app import run_app
# Import run_bot if you plan to run it concurrently later
# from amazing_storage.bot import run_bot 

if __name__ == "__main__":
    print("Starting Amazing Storage System...")
    # TODO: Implement concurrent execution for Flask app and Telegram bot if needed.
    run_app()
    # run_bot() # This needs to be run concurrently with run_app()
