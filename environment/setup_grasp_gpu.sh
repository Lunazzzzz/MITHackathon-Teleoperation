#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_NAME="${1:-grasp-gpu}"

if ! command -v conda >/dev/null 2>&1; then
  echo "conda not found"
  exit 1
fi

if conda env list | awk '{print $1}' | grep -qx "${ENV_NAME}"; then
  echo "Updating conda environment: ${ENV_NAME}"
  conda env update -n "${ENV_NAME}" -f "${ROOT_DIR}/environment/grasp-gpu.yml"
else
  echo "Creating conda environment: ${ENV_NAME}"
  conda env create -n "${ENV_NAME}" -f "${ROOT_DIR}/environment/grasp-gpu.yml"
fi

echo "Installing local pyAgxArm in editable mode"
conda run -n "${ENV_NAME}" python -m pip install -e "${ROOT_DIR}/pyAgxArm" --no-deps

echo "Running setup smoke check"
conda run -n "${ENV_NAME}" python "${ROOT_DIR}/scripts/dev/check_setup.py" --config "${ROOT_DIR}/config/sort_trash_pipeline.example.yaml"
