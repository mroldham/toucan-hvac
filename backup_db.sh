#!/bin/bash

cd /Users/stephenoldham/toucan_hvac_clean

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

cp instance/hvac.db backups/hvac_$TIMESTAMP.db

echo "Backup created: backups/hvac_$TIMESTAMP.db"

ls -t backups/hvac_*.db | tail -n +11 | xargs rm -f 2>/dev/null
