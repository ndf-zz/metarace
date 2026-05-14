#!/usr/bin/env sh
#
# Script version 0.1
# provisioning staging script for WSL based Debian

# Exit on error
set -e

check_command() {
  command -v "$1" >/dev/null 2>&1
}

check_yesno() {
  echo
  echo "$1 [y/n]"
  read -r yesno
  if [ "$yesno" = "y" ] ; then
    return 0
  else
    return 1
  fi
}

echo_continue() {
  echo "  - $1"
}

echo "Starting Post-Install WSL Debian provisioning..."

# Install common packages
if check_command sudo ; then
  # Update 
  sudo apt-get update

  # Install recommended packages
  sudo apt-get install -y wget cups thunar
fi

# Start Metarace AutoInstaller
sh /mnt/c/temp/metarace-install.sh

