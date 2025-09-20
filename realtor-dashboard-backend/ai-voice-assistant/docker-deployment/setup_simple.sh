#!/bin/bash

# setup_simple.sh - Set up the simple scheduler and make it start automatically

# Path to the script
SCRIPT_PATH="$(pwd)/simple_scheduler.sh"
LOG_DIR="$(pwd)/logs"

# Ensure directories exist
mkdir -p "$LOG_DIR"

# Make script executable
chmod +x "$SCRIPT_PATH"

# Add to systemd for auto-start (if on a Linux system with systemd)
setup_systemd() {
  echo "Setting up systemd service..."
  
  # Create service file
  SERVICE_FILE="/etc/systemd/system/inbound-call-scheduler.service"
  
  echo "[Unit]
Description=Inbound Call Service Scheduler
After=docker.service

[Service]
Type=simple
User=$(whoami)
ExecStart=$SCRIPT_PATH run
Restart=on-failure
RestartSec=5
StandardOutput=append:$LOG_DIR/scheduler-service.log
StandardError=append:$LOG_DIR/scheduler-service.log

[Install]
WantedBy=multi-user.target" | sudo tee $SERVICE_FILE

  # Enable and start the service
  sudo systemctl daemon-reload
  sudo systemctl enable inbound-call-scheduler
  sudo systemctl start inbound-call-scheduler
  
  echo "Systemd service created and started!"
  echo "To check status: sudo systemctl status inbound-call-scheduler"
  echo "To view logs: sudo journalctl -u inbound-call-scheduler"
}

# Run as a simple background process
setup_background() {
  echo "Setting up background process..."
  
  # Run as daemon
  $SCRIPT_PATH daemon
  
  # Add to crontab to make it restart on reboot
  TEMP_CRONTAB=$(mktemp)
  crontab -l > "$TEMP_CRONTAB" 2>/dev/null
  
  if ! grep -q "$SCRIPT_PATH daemon" "$TEMP_CRONTAB"; then
    echo "# Restart scheduler on reboot" >> "$TEMP_CRONTAB"
    echo "@reboot $SCRIPT_PATH daemon" >> "$TEMP_CRONTAB"
    crontab "$TEMP_CRONTAB"
    echo "Added scheduler to crontab for restart on reboot"
  else
    echo "Scheduler already in crontab"
  fi
  
  rm "$TEMP_CRONTAB"
  
  echo "Background process started! PID stored in $LOG_DIR/scheduler.pid"
  echo "To check status: $SCRIPT_PATH status"
  echo "To stop: $SCRIPT_PATH stop-scheduler"
}

# Detect system and choose appropriate setup method
if command -v systemctl &> /dev/null; then
  read -p "Do you want to set up as a systemd service? (recommended) [Y/n]: " choice
  choice=${choice:-Y}
  
  if [[ $choice =~ ^[Yy] ]]; then
    setup_systemd
  else
    setup_background
  fi
else
  echo "Systemd not detected, setting up as a background process..."
  setup_background
fi

echo ""
echo "Setup complete! The scheduler will:"
echo "1. Start containers at 6:45 PM"
echo "2. Monitor health during operating hours (7 PM - 7 AM)"
echo "3. Stop containers at 7:00 AM"
echo ""
echo "Script location: $SCRIPT_PATH"
echo "Logs location: $LOG_DIR"