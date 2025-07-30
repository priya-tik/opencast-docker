#!/usr/bin/env python3
import subprocess
import os
import json
import sys
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Check argument length
if len(sys.argv) < 4:
    logger.error("Usage: audio_video_sync.py presenter.mp4 presentation.mp4 output.mp4")
    sys.exit(1)

presenter_input = sys.argv[1]
presentation_input = sys.argv[2]
outputfile = sys.argv[3]

# Log inputs
logger.debug("Working directory: %s", os.getcwd())
logger.debug("Presenter input: %s", presenter_input)
logger.debug("Presentation input: %s", presentation_input)
logger.debug("Output file: %s", outputfile)

# Validate input files
for path in [presenter_input, presentation_input]:
    if not os.path.exists(path):
        logger.error("File not found: %s", path)
        sys.exit(1)

def get_audio_duration(filename):
    logger.debug("Getting audio duration for: %s", filename)
    result = subprocess.run([
        'ffprobe', '-v', 'error',
        '-select_streams', 'a:0',
        '-show_entries', 'stream=duration',
        '-of', 'json',
        filename
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    logger.debug("ffprobe stdout: %s", result.stdout)
    logger.debug("ffprobe stderr: %s", result.stderr)

    try:
        info = json.loads(result.stdout)
        return float(info['streams'][0]['duration'])
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as e:
        logger.error("Failed to parse ffprobe output for audio: %s", e)
        sys.exit(1)

def get_video_duration(filename):
    logger.debug("Getting video duration for: %s", filename)
    result = subprocess.run([
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'json',
        filename
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    logger.debug("ffprobe stdout: %s", result.stdout)
    logger.debug("ffprobe stderr: %s", result.stderr)

    try:
        info = json.loads(result.stdout)
        return float(info['format']['duration'])
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as e:
        logger.error("Failed to parse ffprobe output for video: %s", e)
        sys.exit(1)

def create_offset_video(ref_video, offset_duration, resolution="1280x720", output="blank_with_audio.mp4"):
    logger.info("Creating blank video of %.2fs using audio from: %s", offset_duration, ref_video)

    try:
        subprocess.run([
            'ffmpeg', '-y',
            '-i', ref_video,
            '-t', str(offset_duration),
            '-vn',
            '-ar', '44100', '-ac', '2', '-b:a', '192k', '-acodec', 'aac',
            'temp_offset_audio.aac'
        ], check=True)

        subprocess.run([
            'ffmpeg', '-y',
            '-f', 'lavfi', '-i', f'color=black:s={resolution}:d={offset_duration}',
            '-i', 'temp_offset_audio.aac',
            '-vf', f'scale={resolution},fps=25',
            '-ar', '44100', '-ac', '2',
            '-c:v', 'libx264', '-c:a', 'aac', '-b:a', '192k',
            '-shortest', output
        ], check=True)

        if os.path.exists("temp_offset_audio.aac"):
            os.remove("temp_offset_audio.aac")

    except subprocess.CalledProcessError as e:
        logger.error("Error during creating offset video: %s", e)
        sys.exit(1)

def reencode_video(video_path, output_path):
    logger.info("Re-encoding video: %s -> %s", video_path, output_path)
    try:
        subprocess.run([
            'ffmpeg', '-y',
            '-i', video_path,
            '-vf', 'scale=1280:720,fps=25',
            '-ar', '44100', '-ac', '2',
            '-c:v', 'libx264', '-c:a', 'aac', '-b:a', '192k',
            output_path
        ], check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Error during re-encoding video: %s", e)
        sys.exit(1)

def concat_videos(video1, video2, output):
    logger.info("Concatenating videos: %s + %s -> %s", video1, video2, output)
    with open("concat_list.txt", "w") as f:
        f.write(f"file '{os.path.abspath(video1)}'\n")
        f.write(f"file '{os.path.abspath(video2)}'\n")

    try:
        subprocess.run([
            'ffmpeg', '-y',
            '-f', 'concat', '-safe', '0',
            '-i', 'concat_list.txt',
            '-c', 'copy',
            output
        ], check=True)
        if os.path.exists("concat_list.txt"):
            os.remove("concat_list.txt")
    except subprocess.CalledProcessError as e:
        logger.error("Error during concatenation: %s", e)
        sys.exit(1)

def auto_fix_offset(video_a, video_b, output="good_fixed.mp4", presenter="presenter.mp4", presentation="presentation.mp4"):
    logger.info("=== Starting Sync Check ===")

    a1 = get_audio_duration(video_a)
    a2 = get_audio_duration(video_b)

    logger.info("Audio Durations -> Presenter: %.2fs, Presentation: %.2fs", a1, a2)

    status = "no-fix-needed"
    offset = 0
    fixed_type = "none"

    if abs(a1 - a2) < 0.1:
        logger.info("No sync adjustment needed.")
    else:
        status = "fix-needed"

        if a1 > a2:
            ref = video_a
            desynced = video_b
            offset = a1 - a2
        else:
            ref = video_b
            desynced = video_a
            offset = a2 - a1

        if os.path.abspath(desynced) == os.path.abspath(presenter):
            fixed_type = "presenter"
        elif os.path.abspath(desynced) == os.path.abspath(presentation):
            fixed_type = "presentation"
        else:
            fixed_type = "unknown"

        logger.info("Fixing sync issue for %s with offset %.2fs", fixed_type, offset)
        create_offset_video(ref, offset_duration=offset, output="blank_with_audio.mp4")
        reencode_video(desynced, "desynced_fixed.mp4")
        concat_videos("blank_with_audio.mp4", "desynced_fixed.mp4", output)

        for temp_file in ["blank_with_audio.mp4", "desynced_fixed.mp4"]:
            if os.path.exists(temp_file):
                os.remove(temp_file)

        logger.info("Output saved as: %s", output)

    with open("/tmp/video_params.log", "w") as f:
        f.write(" ".join(sys.argv))

    if not os.path.exists(output) or os.path.getsize(output) < 10000:
        logger.error("Final output video was not created or is too small.")
        sys.exit(1)

# Run the function
auto_fix_offset(
    presenter_input,
    presentation_input,
    outputfile,
    presenter_input,
    presentation_input
)

logger.info("=== Script Completed ===")
