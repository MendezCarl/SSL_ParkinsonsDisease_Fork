import threading
import os
import json

#Refactor to sql
class TestHistoryManager:
    _lock = threading.Lock()

    def __init__(self, file_path: str = "test_history.json"):
        self.file_path = file_path
        self._load()

    def _load(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r') as f:
                self.data = json.load(f)
        else:
            self.data = {}

    def _save(self):
        with open(self.file_path, 'w') as f:
            json.dump(self.data, f, indent=2)

    def get_patient_tests(self, patient_id: str):
        return self.data.get(patient_id, [])

    def add_patient_test(self, patient_id: str, test_data: dict):
        with self._lock:
            self._load()
            if patient_id not in self.data:
                self.data[patient_id] = []
            self.data[patient_id].append(test_data)
            self._save()

    def get_all_tests(self):
        return self.data
