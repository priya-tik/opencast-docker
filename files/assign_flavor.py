#!/usr/bin/env python3
import subprocess
import os
import json
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG, handlers=[logging.StreamHandler()])
logger = logging.getLogger(__name__)

presenter = sys.argv[1]
presentation = sys.argv[2]
outputfile = sys.argv[3]

def get_audio_duration(filename):
    logger.debug("Getting audio duration for: %s", filename)
    result = subprocess.run([
        'ffprobe', '-v', 'error',
        '-select_streams', 'a:0',
        '-show_entries', 'stream=duration',
        '-of', 'json',
        filename
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    info = json.loads(result.stdout)
    return float(info['streams'][0]['duration'])

def determine_sync_status(presenter, presentation):
    a1 = get_audio_duration(presenter)
    a2 = get_audio_duration(presentation)
    offset = abs(a1 - a2)
    status = "no-fix-needed" if offset < 0.1 else "fix-needed"

    if offset < 0.1:
        fixed_type = "none"
    else:
        fixed_type = "presenter" if a1 < a2 else "presentation"

    return status, fixed_type, offset

def write_properties(status, fixed_type, offset, outputfile):
    with open(outputfile, "w", encoding="utf-8") as f:
        f.write(f"sync_status={status}\n")
        f.write(f"sync_video={fixed_type}\n")
        f.write(f"offset.seconds={offset:.2f}\n")
    logger.info("Properties written to: %s", outputfile)

# Main execution
status, fixed_type, offset = determine_sync_status(presenter, presentation)
write_properties(status, fixed_type, offset, outputfile)
