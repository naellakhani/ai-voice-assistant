#!/bin/bash
# Simplified container manager with proper sleep mode handling
trap cleanup SIGINT SIGTERM

APP_NAME="inbound-call-app"
DB_NAME="inbound-call-db"
LOG_DIR="./logs"
LOG_FILE="$LOG_DIR/container-$(date +%Y%m%d).log"
DOCKER_COMPOSE="docker-compose.yml"
HEALTH_ENDPOINT="http://localhost:5000/simple-health"
START_TIME="08:00"
STOP_TIME="23:00"
CHECK_INTERVAL=120  # seconds
NGROK_CONFIG="ngrok.yml"
NGROK_PID_FILE="$LOG_DIR/ngrok.pid"

# Make sure log directory exists
mkdir -p "$LOG_DIR"

# Log with timestamp
log() {
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Proper sleep mode disabling for Windows
disable_sleep_mode() {
  log "Disabling sleep mode..."
  
  # Check for Windows environment
  if grep -q Microsoft /proc/version || grep -q microsoft /proc/version || [ -f /proc/sys/fs/binfmt_misc/WSLInterop ]; then
    log "Windows WSL environment detected, disabling sleep mode..."
    
    # Create a temporary PowerShell script with all our commands
    powershell_script="$LOG_DIR/disable_sleep.ps1"
    cat <<EOF > "$powershell_script"
# Disable standby (sleep)
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0

# Disable monitor timeout
powercfg /change monitor-timeout-ac 0
powercfg /change monitor-timeout-dc 0

# Disable hibernation - requires admin privileges
try {
  powercfg /hibernate off
} catch {
  Write-Host "Failed to disable hibernation: \$_"
}

# Disable network adapter power saving
powercfg /setacvalueindex scheme_current sub_none connectivityinstandby 1

# HP-specific settings
powercfg /setacvalueindex scheme_current sub_sleep awaymode 0

# Apply all changes
powercfg /setactive scheme_current

Write-Host "Sleep mode disabled successfully"
EOF

    # Run the PowerShell script with elevated privileges
    # "-NoProfile -ExecutionPolicy Bypass" allows script execution
    # "-WindowStyle Hidden" hides the PowerShell window
    powershell.exe "Start-Process PowerShell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"$(wslpath -w "$powershell_script")\"' -Verb RunAs -WindowStyle Hidden"
    
    # Give some time for the commands to run
    sleep 5
    
    log "Sleep mode and power-saving features disabled on Windows"
  elif command -v cmd.exe >/dev/null 2>&1; then
    log "Windows detected via cmd.exe availability"
    
    # Create a batch file to elevate the command prompt
    batch_file="$LOG_DIR/disable_sleep.bat"
    cat <<EOF > "$batch_file"
@echo off
:: Check for admin rights
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrative privileges...
  powershell -Command "Start-Process cmd -ArgumentList '/c cd %CD% && powercfg /change standby-timeout-ac 0 && powercfg /change standby-timeout-dc 0 && powercfg /hibernate off && powercfg /change monitor-timeout-ac 0 && powercfg /change monitor-timeout-dc 0 && powercfg /setacvalueindex scheme_current sub_none connectivityinstandby 1 && powercfg /setactive scheme_current' -Verb RunAs"
) else (
  powercfg /change standby-timeout-ac 0
  powercfg /change standby-timeout-dc 0
  powercfg /hibernate off
  powercfg /change monitor-timeout-ac 0
  powercfg /change monitor-timeout-dc 0
  powercfg /setacvalueindex scheme_current sub_none connectivityinstandby 1
  powercfg /setactive scheme_current
)
EOF

    cmd.exe /c "$(wslpath -w "$batch_file")"
    sleep 5
    log "Sleep mode disabled using cmd.exe with elevation script"
  else
    log "No Windows environment detected, skipping sleep mode configuration"
  fi
}

# Start ngrok with multiple tunnels
start_ngrok() {
  log "Starting ngrok with multiple tunnels..."
  
  # Check if ngrok is already running
  if [ -f "$NGROK_PID_FILE" ]; then
    ngrok_pid=$(cat "$NGROK_PID_FILE")
    if ps -p $ngrok_pid > /dev/null 2>&1; then
      log "Ngrok is already running with PID $ngrok_pid"
      return 0
    else
      log "Stale ngrok PID file found, removing..."
      rm "$NGROK_PID_FILE"
    fi
  fi
  
  # Check if ngrok config exists
  if [ ! -f "$NGROK_CONFIG" ]; then
    log "ERROR: Ngrok config file $NGROK_CONFIG not found"
    return 1
  fi
  
  # Load environment variables from .env.docker for ngrok token
  if [ -f "../.env.docker" ]; then
    log "Loading NGROK_AUTH_TOKEN from .env.docker"
    export NGROK_AUTH_TOKEN=$(grep "NGROK_AUTH_TOKEN=" "../.env.docker" | cut -d'=' -f2)
  fi
  
  # Start ngrok in background
  log "Starting ngrok with config: $NGROK_CONFIG"
  nohup ngrok start --all --config "$NGROK_CONFIG" > "$LOG_DIR/ngrok.log" 2>&1 &
  ngrok_pid=$!
  echo $ngrok_pid > "$NGROK_PID_FILE"
  
  log "Ngrok started with PID $ngrok_pid"
  
  # Wait for ngrok to start up
  log "Waiting for ngrok to initialize..."
  sleep 10
  
  # Get tunnel URLs and export as environment variables
  if command -v jq >/dev/null 2>&1; then
    # Use jq if available
    APP1_URL=$(curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[] | select(.name=="app-instance1") | .public_url')
    APP2_URL=$(curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[] | select(.name=="app-instance2") | .public_url')
    VIEWER1_URL=$(curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[] | select(.name=="viewer-instance1") | .public_url')
    VIEWER2_URL=$(curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[] | select(.name=="viewer-instance2") | .public_url')
  else
    # Fallback without jq - get first tunnel URL for primary instance
    APP1_URL=$(curl -s http://localhost:4040/api/tunnels | grep -o '"public_url":"[^"]*' | head -1 | cut -d'"' -f4)
    log "Warning: jq not found, using first tunnel URL: $APP1_URL"
    APP2_URL="$APP1_URL"
    VIEWER1_URL="$APP1_URL"
    VIEWER2_URL="$APP1_URL"
  fi
  
  # Export URLs for use by containers
  export NGROK_APP1_URL="$APP1_URL"
  export NGROK_APP2_URL="$APP2_URL"
  export NGROK_VIEWER1_URL="$VIEWER1_URL"
  export NGROK_VIEWER2_URL="$VIEWER2_URL"
  
  log "Ngrok tunnels created:"
  log "App Instance 1: $APP1_URL"
  log "App Instance 2: $APP2_URL"
  log "Viewer Instance 1: $VIEWER1_URL"
  log "Viewer Instance 2: $VIEWER2_URL"
  
  # Save URLs to file for container use
  cat > "$LOG_DIR/ngrok_urls.env" <<EOF
NGROK_APP1_URL=$APP1_URL
NGROK_APP2_URL=$APP2_URL
NGROK_VIEWER1_URL=$VIEWER1_URL
NGROK_VIEWER2_URL=$VIEWER2_URL
EOF
  
  return 0
}

# Stop ngrok
stop_ngrok() {
  log "Stopping ngrok..."
  
  if [ -f "$NGROK_PID_FILE" ]; then
    ngrok_pid=$(cat "$NGROK_PID_FILE")
    if ps -p $ngrok_pid > /dev/null 2>&1; then
      log "Killing ngrok process with PID $ngrok_pid"
      kill $ngrok_pid
      sleep 2
      # Force kill if still running
      if ps -p $ngrok_pid > /dev/null 2>&1; then
        log "Force killing ngrok process"
        kill -9 $ngrok_pid
      fi
    fi
    rm "$NGROK_PID_FILE"
  fi
  
  # Clean up URLs file
  if [ -f "$LOG_DIR/ngrok_urls.env" ]; then
    rm "$LOG_DIR/ngrok_urls.env"
  fi
  
  log "Ngrok stopped"
}

# Proper sleep mode enabling for Windows
enable_sleep_mode() {
  log "Re-enabling sleep mode..."
  
  # Check for Windows environment
  if grep -q Microsoft /proc/version || grep -q microsoft /proc/version || [ -f /proc/sys/fs/binfmt_misc/WSLInterop ]; then
    log "Windows WSL environment detected, re-enabling sleep mode..."
    
    # Create a temporary PowerShell script with all our commands
    powershell_script="$LOG_DIR/enable_sleep.ps1"
    cat <<EOF > "$powershell_script"
# Re-enable standby (sleep)
powercfg /change standby-timeout-ac 30
powercfg /change standby-timeout-dc 15

# Re-enable monitor timeout
powercfg /change monitor-timeout-ac 15
powercfg /change monitor-timeout-dc 5

# Re-enable hibernation - requires admin privileges
try {
  powercfg /hibernate on
} catch {
  Write-Host "Failed to re-enable hibernation: \$_"
}

# Apply all changes
powercfg /setactive scheme_current

Write-Host "Sleep mode re-enabled successfully"
EOF

    # Run the PowerShell script with elevated privileges
    powershell.exe "Start-Process PowerShell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"$(wslpath -w "$powershell_script")\"' -Verb RunAs -WindowStyle Hidden"
    
    # Give some time for the commands to run
    sleep 5
    
    log "Sleep mode re-enabled on Windows"
  elif command -v cmd.exe >/dev/null 2>&1; then
    log "Windows detected via cmd.exe availability"
    
    # Create a batch file to elevate the command prompt
    batch_file="$LOG_DIR/enable_sleep.bat"
    cat <<EOF > "$batch_file"
@echo off
:: Check for admin rights
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrative privileges...
  powershell -Command "Start-Process cmd -ArgumentList '/c cd %CD% && powercfg /change standby-timeout-ac 30 && powercfg /change standby-timeout-dc 15 && powercfg /hibernate on && powercfg /change monitor-timeout-ac 15 && powercfg /change monitor-timeout-dc 5 && powercfg /setactive scheme_current' -Verb RunAs"
) else (
  powercfg /change standby-timeout-ac 30
  powercfg /change standby-timeout-dc 15
  powercfg /hibernate on
  powercfg /change monitor-timeout-ac 15
  powercfg /change monitor-timeout-dc 5
  powercfg /setactive scheme_current
)
EOF

    cmd.exe /c "$(wslpath -w "$batch_file")"
    sleep 5
    log "Sleep mode re-enabled using cmd.exe with elevation script"
  else
    log "Not running in Windows environment, skipping sleep mode configuration"
  fi
}

# Simplified container start
start_containers() {
  log "Starting containers using $DOCKER_COMPOSE..."

  disable_sleep_mode
  
  # Check if containers are already running
  if docker ps --format '{{.Names}}' | grep -q "$APP_NAME"; then
    log "Application container is already running"
    return 0
  fi
  
  # Start ngrok first
  log "Starting ngrok tunnels..."
  if ! start_ngrok; then
    log "ERROR: Failed to start ngrok"
    return 1
  fi
  
  # Start containers with ngrok URLs
  log "Running 'docker compose up -d'..."
  # Source the ngrok URLs file if it exists
  if [ -f "$LOG_DIR/ngrok_urls.env" ]; then
    source "$LOG_DIR/ngrok_urls.env"
    log "Loaded ngrok URLs from environment file"
  fi
  
  docker compose --env-file ../env.docker up -d
  
  log "Containers started, waiting for health check..."
  # Wait briefly for containers to initialize
  sleep 10
  
  # No need for complex health checks during startup - the scheduler will handle that
  return 0
}

# Simplified container stop
stop_containers() {
  log "Stopping containers..."

  enable_sleep_mode
  
  # Check if containers are running
  if ! docker ps --format '{{.Names}}' | grep -q "$APP_NAME"; then
    log "Containers are not running"
  else
    # Stop containers gracefully
    docker compose --env-file ../env.docker down --timeout 30
    log "Containers stopped"
  fi
  
  # Stop ngrok
  stop_ngrok
  
  return 0
}

# Simplified health check
check_health() {
  # Simple status code check
  if curl -s --max-time 2 -o /dev/null -w "%{http_code}" "$HEALTH_ENDPOINT" | grep -q "200"; then
    log "Health check passed"
    return 0
  else
    log "Health check failed, restarting containers"
    stop_containers
    sleep 5
    start_containers
    return 1
  fi
}

cleanup() {
  log "Received termination signal. Cleaning up..."
  stop_containers
  stop_ngrok
  log "Cleanup complete. Exiting."
  exit 0
}

# Main scheduler loop
run_scheduler() {
  log "Starting scheduler. Containers will run from $START_TIME to $STOP_TIME"
  log "Health checks will run every $CHECK_INTERVAL seconds"
  
  while true; do
    current_time=$(date +"%H:%M")
    
    # Start containers at scheduled time
    if [ "$current_time" = "$START_TIME" ]; then
      log "Start time reached ($START_TIME)"
      start_containers
    fi
    
    # Stop containers at scheduled time
    if [ "$current_time" = "$STOP_TIME" ]; then
      log "Stop time reached ($STOP_TIME)"
      stop_containers
    fi
    
    # Check if containers should be running based on time
    is_operation_hours=false
    current_hour=$(date +"%H" | sed 's/^0//')
    current_minute=$(date +"%M" | sed 's/^0//')
    start_hour=$(echo $START_TIME | cut -d: -f1 | sed 's/^0//')
    start_minute=$(echo $START_TIME | cut -d: -f2 | sed 's/^0//')
    stop_hour=$(echo $STOP_TIME | cut -d: -f1 | sed 's/^0//')
    stop_minute=$(echo $STOP_TIME | cut -d: -f2 | sed 's/^0//')
    
    # Convert to minutes for comparison
    current_minutes=$((current_hour * 60 + current_minute))
    start_minutes=$((start_hour * 60 + start_minute))
    stop_minutes=$((stop_hour * 60 + stop_minute))
    
    # Handle overnight schedule (if stop time is earlier than start time)
    if [ $stop_minutes -lt $start_minutes ]; then
      # Either after start time or before stop time
      if [ $current_minutes -ge $start_minutes ] || [ $current_minutes -lt $stop_minutes ]; then
        is_operation_hours=true
      fi
    else
      # Regular daytime schedule
      if [ $current_minutes -ge $start_minutes ] && [ $current_minutes -lt $stop_minutes ]; then
        is_operation_hours=true
      fi
    fi
    
    # Manage containers based on operation hours
    if $is_operation_hours; then
      # During operation hours - start if not running, check health if running
      if ! docker ps --format '{{.Names}}' | grep -q "$APP_NAME"; then
        log "Containers should be running during operation hours but aren't. Starting..."
        start_containers
      else
        check_health
      fi
    else
      # Outside operation hours - stop if running
      if docker ps --format '{{.Names}}' | grep -q "$APP_NAME"; then
        log "Outside operation hours but containers are running. Stopping..."
        stop_containers
      fi
    fi
    
    # Sleep until next check
    sleep $CHECK_INTERVAL
  done
}

# Handle command line arguments
case "$1" in
  start)
    start_containers
    ;;
  stop)
    stop_containers
    ;;
  check)
    check_health
    ;;
  run)
    run_scheduler
    ;;
  daemon)
    # Run the scheduler as a background process without changing priority
    nohup "$0" run > "$LOG_DIR/scheduler.log" 2>&1 &
    echo "$!" > "$LOG_DIR/scheduler.pid"
    log "Scheduler started as background process with PID $!"
    ;;
  status)
    if [ -f "$LOG_DIR/scheduler.pid" ]; then
      pid=$(cat "$LOG_DIR/scheduler.pid")
      if ps -p $pid > /dev/null; then
        echo "Scheduler is running with PID $pid"
        exit 0
      else
        echo "Scheduler is not running (stale PID file)"
        exit 1
      fi
    else
      echo "Scheduler is not running"
      exit 1
    fi
    ;;
  stop-scheduler)
    if [ -f "$LOG_DIR/scheduler.pid" ]; then
      pid=$(cat "$LOG_DIR/scheduler.pid")
      if ps -p $pid > /dev/null; then
        echo "Stopping scheduler with PID $pid"
        kill $pid
        rm "$LOG_DIR/scheduler.pid"
        exit 0
      else
        echo "Scheduler is not running (stale PID file)"
        rm "$LOG_DIR/scheduler.pid"
        exit 1
      fi
    else
      echo "Scheduler is not running"
      exit 1
    fi
    ;;
  *)
    echo "Usage: $0 {start|stop|check|run|daemon|status|stop-scheduler}"
    echo ""
    echo "Commands:"
    echo "  start          - Start containers immediately"
    echo "  stop           - Stop containers immediately"
    echo "  check          - Run a health check"
    echo "  run            - Run the scheduler in the foreground"
    echo "  daemon         - Run the scheduler as a background process"
    echo "  status         - Check if the scheduler is running"
    echo "  stop-scheduler - Stop the background scheduler process"
    exit 1
    ;;
esac

exit $?