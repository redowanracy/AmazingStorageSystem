import json
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

CONFIG_FILE = "config.json"

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

    @classmethod
    def load(cls, path: str = CONFIG_FILE) -> 'AppConfig':
        """Loads configuration from a JSON file and environment variables."""
        try:
            with open(path, 'r') as f:
                config_data = json.load(f)
        except FileNotFoundError:
            print(f"Warning: Configuration file '{path}' not found. Using defaults.")
            config_data = {}
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from '{path}'. Using defaults.")
            config_data = {}

        config = cls()

        bucket_configs = []
        for bucket_data in config_data.get("buckets", []):
            bucket_configs.append(BucketConfig(**bucket_data))
        config.buckets = bucket_configs

        config.chunk_size = config_data.get("chunk_size", config.chunk_size)
        config.encryption_enabled = config_data.get("encryption_enabled", config.encryption_enabled)
        config.performance_monitoring = config_data.get("performance_monitoring", config.performance_monitoring)
        config.web_interface_host = config_data.get("web_interface_host", config.web_interface_host)
        config.web_interface_port = config_data.get("web_interface_port", config.web_interface_port)
        config.chatbot_provider = config_data.get("chatbot_provider", config.chatbot_provider)

        config.encryption_key = os.getenv("ASS_ENCRYPTION_KEY", config_data.get("encryption_key"))
        config.telegram_bot_token = os.getenv("ASS_TELEGRAM_BOT_TOKEN", config_data.get("telegram_bot_token"))
        config.chatbot_api_key = os.getenv("ASS_CHATBOT_API_KEY", config_data.get("chatbot_api_key"))

        if config.encryption_enabled and not config.encryption_key:
            print("Warning: Encryption is enabled but no encryption key found (set ASS_ENCRYPTION_KEY).")

        if not config.buckets:
             print("Warning: No storage buckets configured.")

        return config

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