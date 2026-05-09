import json
from datetime import datetime
import os

LOG_FILE = "local_storage/logs.txt"

def log_event(data):
    if not isinstance(data, dict):
        data = {"message": str(data)};
    
    # os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    entry = {
      "timestamp": datetime.now().isoformat(),
      **data
    };

    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n");