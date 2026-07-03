from datetime import date
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDINGS_DIR = os.path.join(BASE_DIR, "routes", "recordings")
print(str(RECORDINGS_DIR))
