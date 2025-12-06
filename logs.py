import datetime

class LogManager:
    def __init__(self):
        self.logs = []

    def add_log(self, source: str, message: str, level: str = "INFO"):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = {
            "timestamp": timestamp,
            "source": source,
            "level": level,
            "message": message
        }
        self.logs.append(log_entry)
        # Keep only last 1000 logs to prevent memory overflow
        if len(self.logs) > 1000:
            self.logs.pop(0)
        return log_entry

    def get_logs(self, limit: int = 100):
        return self.logs[-limit:]

    def clear_logs(self):
        self.logs = []

# Global instance
logger = LogManager()

def log(source: str, message: str, level: str = "INFO"):
    print(f"[{level}] {source}: {message}")
    logger.add_log(source, message, level)

def get_all_logs():
    return logger.get_logs()
