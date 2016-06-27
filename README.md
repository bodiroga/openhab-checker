## Introduction

This script controls the status of the openHAB installation and the distributed ZWave networks.

## Installation

You don't even need to clone the repository to use this script, just download the install.sh file to your Raspberry Pi, execute it with root privileges, configure the configuration.ini file with your requirements and start the script through '/etc/init.d/openhab-checker start'. The script will automatically control your openHAB installation.

wget https://raw.githubusercontent.com/bodiroga/openhab-checker/master/install.sh

sudo chmod +x install.sh

sudo ./install.sh
