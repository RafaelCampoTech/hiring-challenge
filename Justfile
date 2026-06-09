# Contact Finder — task runner

python := "contact_finder/.venv/bin/python3"

# Create venv and install dependencies (skipped if venv already exists)
_setup:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -f contact_finder/.venv/bin/python3 ]; then
        echo "Creating venv and installing dependencies..."
        python3 -m venv contact_finder/.venv
        contact_finder/.venv/bin/pip install -r contact_finder/requirements.txt -q
    fi

# Run the contact finder against challenge/data/ and challenge/mocks/
run: _setup
    {{python}} contact_finder/contact_finder.py

# Show the output CSV as a formatted table (press q to exit)
show:
    column -t -s, output/results.csv | less -S

# Run then show results
all: run show
