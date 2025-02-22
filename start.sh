#!/usr/bin/env bash

_SCRIPT_DIR=$(dirname "$(realpath "$0")")
cd "$_SCRIPT_DIR" || exit 1

if command -v conda &>/dev/null; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
else
    echo "ERROR: conda is not installed or not in the PATH."
    exit 1
fi

conda activate fish-sensor-peripherals                              || { echo "ERROR: failed to activate conda environment"; exit 1; }

trap 'conda deactivate' EXIT
cd "$_SCRIPT_DIR" || exit 1
$(conda run -n fish-sensor-peripherals which python) sensor-peripherals.py   || { echo "ERROR: failed to run sensor-peripherals.py"; exit 1; }

read -p "press ENTER to exit..."