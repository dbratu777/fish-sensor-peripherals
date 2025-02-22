#!/usr/bin/env bash

_SCRIPT_DIR=$(dirname "$(realpath "$0")")

if command -v conda &>/dev/null; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
else
    echo "ERROR: conda is not installed or not in the PATH."
    exit 1
fi

conda activate fish-sensor-peripherals      || { echo "ERROR: failed to activate conda environment"; exit 1; }

trap 'conda deactivate' EXIT
python "$_SCRIPT_DIR"/sensor-peripherals.py || { echo "ERROR: failed to run fishapp.py"; exit 1; }
