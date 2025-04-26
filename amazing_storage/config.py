import os
import json
import logging
from typing import List, Dict, Optional, Union, Any
from dataclasses import dataclass, field

logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONFIG_FILE = "config.json"

def mask_sensitive_value(value: str) -> str:
    """Mask sensitive values for logging."""
    if not value or len(value) < 8:
        return "****"
    return value[:4] + "*" * (len(value) - 4)

@dataclass
class BucketConfig:
    type: str
    credentials: str
    folder_id: Optional[str] = None
    folder_path: Optional[str] = None

@dataclass
class AppConfig:
    buckets: List[BucketConfig] = field(default_factory=list)
    chunk_size: int = 5 * 1024 * 1024
    encryption_enabled: bool = False
    encryption_key: Optional[str] = None
    performance_monitoring: bool = False
    web_interface_host: str = "127.0.0.1"
    web_interface_port: int = 5000
    telegram_bot_token: Optional[str] = None
    chatbot_api_key: Optional[str] = None
    chatbot_provider: Optional[str] = None
    dropbox_app_key: Optional[str] = None
    dropbox_app_secret: Optional[str] = None
    dropbox_redirect_uri: Optional[str] = None

    @classmethod
    def load(cls, path: str = CONFIG_FILE) -> 'AppConfig':
        """Loads configuration from JSON and environment variables."""
        try:
            with open(path, 'r') as f:
                config_data = json.load(f)
            logger.info(f"Configuration loaded from {path}")
        except FileNotFoundError:
            logger.warning(f"Configuration file '{path}' not found. Using defaults.")
            config_data = {}
        except json.JSONDecodeError:
            logger.error(f"Error: Could not decode JSON from '{path}'. Using defaults.")
            config_data = {}

        config = cls()

        try:
            from dotenv import load_dotenv
            load_dotenv()
            logger.info("Loaded environment variables from .env file")
        except ImportError:
            logger.info("python-dotenv not installed, skipping .env file loading")

        env_prefix = "ASS_"
        env_vars = {
            "ENCRYPTION_KEY": "encryption_key",
            "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
            "CHATBOT_API_KEY": "chatbot_api_key",
            "DROPBOX_APP_KEY": "dropbox_app_key",
            "DROPBOX_APP_SECRET": "dropbox_app_secret",
            "DROPBOX_REDIRECT_URI": "dropbox_redirect_uri",
            "WEB_HOST": "web_interface_host",
            "WEB_PORT": "web_interface_port",
            "CHUNK_SIZE": "chunk_size"
        }

        bucket_configs = []
        for i, bucket_data in enumerate(config_data.get("buckets", [])):
            # Get credential filename from environment or config file
            env_cred = os.getenv(f'{env_prefix}CREDENTIALS_{i}')
            base_cred = bucket_data.get('credentials')
            credentials = env_cred if env_cred is not None else base_cred

            if not credentials:
                logger.warning(f"Bucket {i} ({bucket_data.get('type', 'unknown')}) has no credentials configured")
                continue
            if not os.path.exists(credentials):
                logger.warning(f"Bucket {i} credentials file not found: {credentials}")
                continue

            bucket_configs.append(BucketConfig(
                type=bucket_data['type'],
                credentials=credentials,
                folder_id=bucket_data.get('folder_id'),
                folder_path=bucket_data.get('folder_path')
            ))
            logger.info(f"Configured bucket {i}: type={bucket_data['type']}, "
                      f"credentials={os.path.basename(credentials)}")
        config.buckets = bucket_configs

        config.chunk_size = config_data.get("chunk_size", config.chunk_size)
        config.encryption_enabled = config_data.get("encryption_enabled", config.encryption_enabled)
        config.performance_monitoring = config_data.get("performance_monitoring", config.performance_monitoring)
        config.web_interface_host = config_data.get("web_interface_host", config.web_interface_host)
        config.web_interface_port = config_data.get("web_interface_port", config.web_interface_port)
        config.chatbot_provider = config_data.get("chatbot_provider", config.chatbot_provider)

        for env_name, attr_name in env_vars.items():
            env_value = os.getenv(f"{env_prefix}{env_name}")
            if env_value is not None:
                setattr(config, attr_name, env_value)
                if any(keyword in attr_name for keyword in ['key', 'secret', 'token', 'password']):
                    logger.info(f"Using {env_prefix}{env_name} from environment: {mask_sensitive_value(env_value)}")
                else:
                    logger.info(f"Using {env_prefix}{env_name} from environment: {env_value}")
            elif hasattr(config, attr_name) and getattr(config, attr_name) is None:
                # Fallback to config file for backward compatibility
                config_value = config_data.get(attr_name)
                if config_value:
                    setattr(config, attr_name, config_value)
                    if any(keyword in attr_name for keyword in ['key', 'secret', 'token', 'password']):
                        logger.warning(f"Using {attr_name} from config file: {mask_sensitive_value(config_value)}. "
                                    f"Consider moving this to {env_prefix}{env_name} environment variable.")
                    else:
                        logger.info(f"Using {attr_name} from config file: {config_value}")

        # Validate critical configs
        if config.encryption_enabled and not config.encryption_key:
            logger.warning("Encryption is enabled but no encryption key found. Set ASS_ENCRYPTION_KEY.")
        if not config.buckets:
            logger.warning("No storage buckets configured.")

        logger.info(f"Dropbox OAuth: app_key={mask_sensitive_value(config.dropbox_app_key or '')}")
        logger.info(f"Dropbox OAuth: redirect_uri={config.dropbox_redirect_uri}")
        return config

# Singleton instance
app_config = AppConfig.load()

if __name__ == "__main__":
    print("Loaded Configuration:")
    print(f"Chunk Size: {app_config.chunk_size}")
    print(f"Encryption Enabled: {app_config.encryption_enabled}")
    print(f"Number of Buckets: {len(app_config.buckets)}")
    if app_config.buckets:
        print(f"First Bucket Type: {app_config.buckets[0].type}")
        print(f"First Bucket Credentials File: {app_config.buckets[0].credentials}")
    print(f"Telegram Bot Token Set: {'Yes' if app_config.telegram_bot_token else 'No'}")
    print(f"Encryption Key Set: {'Yes' if app_config.encryption_key else 'No'}")