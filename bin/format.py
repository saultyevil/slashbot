import os
from pathlib import Path

style = "'{based_on_style: pep8, column_limit: 120}'"
for file in Path(".").rglob("*.py"):
    print(file)
    os.system(f"isort {file} > /dev/null; black {file} --line-length 120;" f"docformatter -i {file} > /dev/null")
