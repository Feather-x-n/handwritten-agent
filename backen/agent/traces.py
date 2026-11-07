import os
import json
from datetime import datetime
class Trace:
    def __init__(self):
        self.trace_dir = "traces"
        os.makedirs(self.trace_dir, exist_ok=True)
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.file_path = os.path.join(self.trace_dir,f"{now}.jsonl")
    def log(self,record):
        record["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.file_path,"a",encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")