import json
import logging
import pathlib

log = logging.getLogger(__name__)


class ConfigManager:
    def __init__(self, path: pathlib.Path):
        log.info(f'Initializing ConfigManager with path: {path}')
        self.path = path
        self.data = {}
        if self.path.exists():
            with self.path.open() as f:
                self.data = json.load(f)

    def __contains__(self, item):
        return item in self.data

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        log.info(f'Setting {key!r} to {value!r}')
        self.data[key] = value
        self._flush()

    def _flush(self):
        with self.path.open('w') as f:
            json.dump(self.data, f, indent=2, sort_keys=True)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def keys(self):
        return self.data.keys()

    def remove(self, key):
        log.info(f'Removing {key}')
        if key in self.data:
            del self.data[key]
            self._flush()

    def set(self, key, value):
        self[key] = value
