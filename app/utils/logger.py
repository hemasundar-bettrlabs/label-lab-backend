import json
import textwrap
from datetime import datetime

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class PipelineLogger:
    def _timestamp(self):
        return datetime.now().strftime("%H:%M:%S")

    def stage(self, step, total, message):
        print(f"\n{Colors.OKBLUE}╔{'═' * 50}╗{Colors.ENDC}")
        print(f"{Colors.OKBLUE}║{Colors.ENDC}  STEP {step}/{total} │  {Colors.BOLD}{message:<34}{Colors.ENDC}{Colors.OKBLUE}║{Colors.ENDC}")
        print(f"{Colors.OKBLUE}╚{'═' * 50}╝{Colors.ENDC}")

    def info(self, section, message):
        print(f"  [{self._timestamp()}] {Colors.OKCYAN}► {section}:{Colors.ENDC} {message}")

    def error(self, section, message):
        print(f"  [{self._timestamp()}] {Colors.FAIL}✖ ERROR in {section}:{Colors.ENDC} {message}")

    def success(self, message):
        print(f"  [{self._timestamp()}] {Colors.OKGREEN}✓ SUCCESS:{Colors.ENDC} {message}\n")

    def json_dump(self, label, data):
        print(f"\n{Colors.WARNING}╭─ {label} {'─' * (48 - len(label))}{Colors.ENDC}")
        try:
            formatted = json.dumps(data, indent=2)
            for line in formatted.split('\n'):
                print(f"{Colors.WARNING}│{Colors.ENDC} {line}")
        except Exception:
            print(f"{Colors.WARNING}│{Colors.ENDC} {data}")
        print(f"{Colors.WARNING}╰{'─' * 50}{Colors.ENDC}\n")

pipeline_logger = PipelineLogger()
