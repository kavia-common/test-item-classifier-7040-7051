#!/bin/bash
cd /home/kavia/workspace/code-generation/test-item-classifier-7040-7051/backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

