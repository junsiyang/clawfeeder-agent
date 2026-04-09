import os
import yaml
from pathlib import Path
from typing import Optional

class Config:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self._load()

    def _load(self):
        with open(self.config_path, 'r') as f:
            self._data = yaml.safe_load(f)

    @property
    def api_base_url(self) -> str:
        # Set by launcher (embedded at install time); fallback to config file
        return os.environ.get('CLAWFEEDER_BASE_URL') or self._data.get('api', {}).get('base_url', '')

    @property
    def heartbeat_interval(self) -> int:
        # Set by launcher (embedded at install time); fallback to config file
        env_val = os.environ.get('CLAWFEEDER_HEARTBEAT_INTERVAL')
        if env_val:
            return int(env_val)
        return self._data.get('api', {}).get('heartbeat_interval', 60)

    @property
    def data_dir(self) -> Path:
        return Path(os.path.expanduser(self._data['storage']['data_dir']))

    @property
    def expired_dir(self) -> Path:
        return Path(os.path.expanduser(self._data['storage']['expired_dir']))

    @property
    def device_id(self) -> str:
        return self._data['device']['device_id']

    @property
    def device_name(self) -> str:
        return self._data['device']['device_name']

    @property
    def master_key(self) -> Optional[str]:
        return os.environ.get('MASTER_KEY') or self._data.get('master_key', '')
