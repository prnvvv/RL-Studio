#!/bin/bash

# Ensure we are in a git repository
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Error: Not a git repository."
    exit 1
fi

# Use -u to untangle untracked directories into individual files
git status --porcelain -u | while IFS= read -r line; do
    [ -z "$line" ] && continue

    # Extract status code and file path
    status="${line:0:2}"
    file="${line:3}"

    # Strip quotes added by Git for filenames with special characters
    file="${file#\"}"
    file="${file%\"}"

    # Handle renamed files (extract destination path)
    if [[ "$file" == *" -> "* ]]; then
        file="${file##* -> }"
        file="${file#\"}"
        file="${file%\"}"
    fi

    # Ensure it's a file, not a remaining directory entry
    if [ -n "$file" ] && [ -f "$file" ]; then
        echo "Staging and committing: $file"
        git add -- "$file"
        
        # Ensure changes are staged before committing
        if ! git diff --cached --quiet -- "$file"; then
            git commit -m "chore: update $file"
        fi
    fi
done

echo "Successfully committed all changes into separate individual commits."
