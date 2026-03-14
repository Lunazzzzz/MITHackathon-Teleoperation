#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-pipeline}"
if [[ $# -gt 0 ]]; then
  shift
fi
EXTRA_ARGS=("$@")

ENV_NAME="${ENV_NAME:-grasp-gpu}"
CAN_CHANNEL="${CAN_CHANNEL:-can0}"
CAN_BITRATE="${CAN_BITRATE:-1000000}"
CAMERA_SERIAL="${CAMERA_SERIAL:-241222074755}"
MODEL_PATH="${MODEL_PATH:-$ROOT_DIR/yolo26s.pt}"
YOLO_DEVICE="${YOLO_DEVICE:-0}"
FOLLOW_RATE_HZ="${FOLLOW_RATE_HZ:-30}"
FOLLOW_FILTER_ALPHA="${FOLLOW_FILTER_ALPHA:-0.20}"
FOLLOW_FILTER_RESET_DISTANCE_M="${FOLLOW_FILTER_RESET_DISTANCE_M:-0.08}"
HOVER_HEIGHT_M="${HOVER_HEIGHT_M:-0.20}"
DISPLAY_VALUE="${DISPLAY_VALUE:-:0}"
XAUTHORITY_VALUE="${XAUTHORITY_VALUE:-/run/user/1000/gdm/Xauthority}"

PIPELINE_CONFIG="${PIPELINE_CONFIG:-$ROOT_DIR/config/sort_trash_pipeline.example.yaml}"
CALIBRATION_FILE_DEFAULT="$ROOT_DIR/data/calib_run_02/calibration_result.yaml"
IDENTITY_CALIBRATION="$ROOT_DIR/config/calibration.identity.yaml"
CALIBRATION_FILE="${CALIBRATION_FILE:-$CALIBRATION_FILE_DEFAULT}"

usage() {
  cat <<EOF
Usage:
  bash run_project.sh [mode] [extra args...]

Modes:
  self-test   Run pipeline self-test only
  stream      View RealSense color/depth stream
  detect2d    Run RealSense + YOLO 2D detection
  detectxyz   Run RealSense + YOLO + depth XYZ output
  follow      Run hover-follow mode (no drop action)
  pipeline    Run the main pipeline entrypoint
  fake-grasp  Run the fake grasp cycle script

Examples:
  bash run_project.sh self-test
  bash run_project.sh detect2d
  bash run_project.sh follow
  bash run_project.sh pipeline

Environment overrides:
  ENV_NAME, CAN_CHANNEL, CAN_BITRATE, CAMERA_SERIAL
  MODEL_PATH, YOLO_DEVICE
  FOLLOW_RATE_HZ, FOLLOW_FILTER_ALPHA, FOLLOW_FILTER_RESET_DISTANCE_M
  HOVER_HEIGHT_M, PIPELINE_CONFIG, CALIBRATION_FILE
  DISPLAY_VALUE, XAUTHORITY_VALUE
EOF
}

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

has_flag() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    if [[ "$item" == "$needle" ]]; then
      return 0
    fi
  done
  return 1
}

default_go_modes() {
  case "$MODE" in
    follow|pipeline|fake-grasp)
      if ! has_flag --go "${EXTRA_ARGS[@]}"; then
        EXTRA_ARGS+=(--go)
      fi
      ;;
  esac
}

load_conda() {
  if ! command -v conda >/dev/null 2>&1; then
    echo "conda not found"
    exit 1
  fi
  local conda_base
  conda_base="$(conda info --base)"
  # shellcheck disable=SC1091
  source "$conda_base/etc/profile.d/conda.sh"
  conda activate "$ENV_NAME"
}

load_kernel_modules() {
  log "Loading kernel modules"
  sudo modprobe can || true
  sudo modprobe can_raw || true
  sudo modprobe can_dev || true
  sudo modprobe gs_usb || true
  sudo modprobe uvcvideo || true
}

activate_can() {
  log "Activating ${CAN_CHANNEL} at ${CAN_BITRATE}"
  sudo bash "$ROOT_DIR/pyAgxArm/pyAgxArm/scripts/ubuntu/can_activate.sh" "$CAN_CHANNEL" "$CAN_BITRATE"
  ip -details link show "$CAN_CHANNEL"
}

ensure_runtime_dirs() {
  cd "$ROOT_DIR"
}

ensure_real_calibration_for_go() {
  if has_flag --go "${EXTRA_ARGS[@]}"; then
    if [[ ! -f "$CALIBRATION_FILE" ]]; then
      echo "Missing calibration file: $CALIBRATION_FILE"
      exit 1
    fi
    if [[ "$CALIBRATION_FILE" == "$IDENTITY_CALIBRATION" ]]; then
      echo "Refusing to run with --go using identity calibration."
      exit 1
    fi
  fi
}

pick_calibration_file() {
  if [[ -f "$CALIBRATION_FILE_DEFAULT" && -z "${CALIBRATION_FILE:-}" ]]; then
    CALIBRATION_FILE="$CALIBRATION_FILE_DEFAULT"
  elif [[ ! -f "$CALIBRATION_FILE" ]]; then
    CALIBRATION_FILE="$IDENTITY_CALIBRATION"
  fi
}

run_python() {
  log "Running: $*"
  python "$@"
}

run_with_display() {
  log "Running with DISPLAY=${DISPLAY_VALUE}"
  DISPLAY="$DISPLAY_VALUE" XAUTHORITY="$XAUTHORITY_VALUE" python "$@"
}

mode_needs_can() {
  case "$MODE" in
    follow|fake-grasp)
      return 0
      ;;
    pipeline)
      if has_flag --go "${EXTRA_ARGS[@]}"; then
        return 0
      fi
      return 1
      ;;
    *)
      return 1
      ;;
  esac
}

ensure_runtime_dirs
default_go_modes
load_conda
load_kernel_modules
pick_calibration_file

if mode_needs_can; then
  activate_can
fi

case "$MODE" in
  self-test)
    run_python scripts/control/run_sort_trash_pipeline.py \
      --config "$PIPELINE_CONFIG" \
      --device "$YOLO_DEVICE" \
      --allow-cpu \
      --self-test \
      "${EXTRA_ARGS[@]}"
    ;;
  stream)
    run_python scripts/vision/view_realsense_stream.py "${EXTRA_ARGS[@]}"
    ;;
  detect2d)
    run_python scripts/vision/detect_realsense_yolo_2d.py \
      --model "$MODEL_PATH" \
      --device "$YOLO_DEVICE" \
      --allow-cpu \
      "${EXTRA_ARGS[@]}"
    ;;
  detectxyz)
    run_python scripts/vision/detect_realsense_yolo_xyz.py \
      --model "$MODEL_PATH" \
      --device "$YOLO_DEVICE" \
      --allow-cpu \
      --calibration-file "$CALIBRATION_FILE" \
      "${EXTRA_ARGS[@]}"
    ;;
  follow)
    ensure_real_calibration_for_go
    run_with_display scripts/control/hover_detected_target.py \
      --camera-serial "$CAMERA_SERIAL" \
      --model "$MODEL_PATH" \
      --device "$YOLO_DEVICE" \
      --allow-cpu \
      --calibration-file "$CALIBRATION_FILE" \
      --follow-rate-hz "$FOLLOW_RATE_HZ" \
      --follow-filter-alpha "$FOLLOW_FILTER_ALPHA" \
      --follow-filter-reset-distance-m "$FOLLOW_FILTER_RESET_DISTANCE_M" \
      --hover-height-m "$HOVER_HEIGHT_M" \
      "${EXTRA_ARGS[@]}"
    ;;
  pipeline)
    ensure_real_calibration_for_go
    run_python scripts/control/run_sort_trash_pipeline.py \
      --config "$PIPELINE_CONFIG" \
      --device "$YOLO_DEVICE" \
      --allow-cpu \
      "${EXTRA_ARGS[@]}"
    ;;
  fake-grasp)
    ensure_real_calibration_for_go
    run_with_display scripts/control/run_fake_grasp_cycle.py \
      --camera-serial "$CAMERA_SERIAL" \
      --model "$MODEL_PATH" \
      --device "$YOLO_DEVICE" \
      --allow-cpu \
      --calibration-file "$CALIBRATION_FILE" \
      --hover-height-m "$HOVER_HEIGHT_M" \
      "${EXTRA_ARGS[@]}"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Unknown mode: $MODE"
    usage
    exit 1
    ;;
esac
