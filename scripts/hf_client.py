import urllib.error
import urllib.request
import json
import os
import uuid
import socket
import bpy
from datetime import datetime
# Leave for tests
import tempfile

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

# Maximum time (seconds) for any network request
REQUEST_TIMEOUT = 120

# Base URL for your Hugging Face Space
SPACE_BASE = "https://ascarlettvfx-testpbr2026.hf.space"

# ------------------------------------------------------------
# Main Public Entry Point
# ------------------------------------------------------------

def call_hf_pbr(image_path, prompt=""):
    """
    Send an image to the Hugging Face Space,
    wait for processing to complete,
    download generated PBR maps,
    and return a texture dictionary.
    """
    try:
        project_dir = bpy.path.abspath("//")

        if not bpy.data.filepath:
            raise RuntimeError("Please save the Blender project before generating textures.")

        textures_dir = os.path.join(project_dir, "PlaneToPBR_textures")
        os.makedirs(textures_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Resolve the correct Gradio function index dynamically
        fn_index = _resolve_fn_index("predict")
        # Unique session identifier for queue polling
        session_hash = uuid.uuid4().hex

        # Validate image exists before proceeding
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Read image bytes
        with open(image_path, "rb") as f:
            raw_bytes = f.read()

        # Upload file to Space
        uploaded_path = _upload_file(image_path, raw_bytes)
        filename = os.path.basename(image_path)

        # Construct Gradio payload
        payload = {
            "data": [
                {
                    "path": uploaded_path,
                    "orig_name": filename,
                    "size": len(raw_bytes),
                    "mime_type": "image/png",
                },
                prompt,
            ],
            "fn_index": fn_index,
            "session_hash": session_hash
        }

        # Join Gradio processing queue
        _join_queue(payload)

        # Poll until job completes
        output = _poll_queue(session_hash)

        # Save original image locally as diffuse fallback
        diffuse_path = os.path.join(textures_dir, f"diffuse_{timestamp}.png")
        with open(diffuse_path, "wb") as out:
            out.write(raw_bytes)

        # Download generated PBR outputs
        return _download_results(output, textures_dir, timestamp, diffuse_path)

    except Exception as e:
        raise RuntimeError(f"HF PBR generation failed: {e}")


# ------------------------------------------------------------
# Gradio Function Resolution
# ------------------------------------------------------------

def _resolve_fn_index(api_name="predict"):
    """
    Fetch Space config and determine which fn_index
    corresponds to the provided api_name.
    """
    try:
        with urllib.request.urlopen(
                f"{SPACE_BASE}/config",
                timeout=REQUEST_TIMEOUT
        ) as resp:
            config = json.loads(resp.read().decode())

    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP error fetching Space config: {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Connection error fetching Space config: {e.reason}")
    except json.JSONDecodeError:
        raise RuntimeError("Invalid JSON received from Space config.")
    except socket.timeout:
        raise RuntimeError("Timeout fetching Space config.")

    dependencies = config.get("dependencies")
    if not dependencies:
        raise RuntimeError("Space config missing 'dependencies' field.")

    for i, dep in enumerate(dependencies):
        if dep.get("api_name") == api_name:
            return i

    raise RuntimeError(f"api_name '{api_name}' not found in Space config.")

# ------------------------------------------------------------
# File Upload
# ------------------------------------------------------------

def _upload_file(image_path, raw_bytes):
    """
    Upload image to Gradio Space file endpoint.
    Returns uploaded file path used in queue payload.
    """
    boundary = "----Boundary" + uuid.uuid4().hex
    filename = os.path.basename(image_path)

    body = (
               f"--{boundary}\r\n"
               f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
               f"Content-Type: image/png\r\n\r\n"
           ).encode("utf-8") + raw_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    upload_req = urllib.request.Request(
        f"{SPACE_BASE}/gradio_api/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(upload_req, timeout=REQUEST_TIMEOUT) as resp:
            upload_data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Upload HTTP error: {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Upload connection error: {e.reason}")
    except json.JSONDecodeError:
        raise RuntimeError("Invalid JSON returned during upload.")
    except socket.timeout:
        raise RuntimeError("Upload request timed out.")

    if not upload_data:
        raise RuntimeError("Upload returned empty response.")

    return upload_data[0]


# ------------------------------------------------------------
# Queue Join
# ------------------------------------------------------------

def _join_queue(payload):
    """
    Submit payload to Gradio queue and return event_id.
    """
    join_req = urllib.request.Request(
        f"{SPACE_BASE}/gradio_api/queue/join",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(join_req, timeout=REQUEST_TIMEOUT) as resp:
            join_data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Queue join HTTP error: {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Queue join connection error: {e.reason}")
    except json.JSONDecodeError:
        raise RuntimeError("Invalid JSON returned from queue join.")
    except socket.timeout:
        raise RuntimeError("Queue join timed out.")

    event_id = join_data.get("event_id")
    if not event_id:
        raise RuntimeError(f"Invalid queue response: {join_data}")

    return event_id


# ------------------------------------------------------------
# Queue Polling (SSE Stream)
# ------------------------------------------------------------

def _poll_queue(session_hash):
    """
    Poll the Gradio SSE queue until processing completes.
    Returns the result data list.
    """

    poll_url = f"{SPACE_BASE}/gradio_api/queue/data?session_hash={session_hash}"

    try:
        with urllib.request.urlopen(poll_url, timeout=REQUEST_TIMEOUT) as resp:
            for raw_line in resp:
                line = raw_line.decode().strip()

                # Only process SSE "data:" lines
                if not line.startswith("data:"):
                    continue

                json_str = line.replace("data:", "").strip()
                if not json_str:
                    continue

                event = json.loads(json_str)

                # Processing completed successfully
                if event.get("msg") == "process_completed":
                    result_output = event.get("output")

                    if isinstance(result_output, dict) and result_output.get("data"):
                        return result_output["data"]
                    else:
                        raise RuntimeError(f"Space error: {event}")

                # Processing failed
                if event.get("msg") == "process_failed":
                    raise RuntimeError(f"Space failed: {event}")

    except urllib.error.URLError as e:
        raise RuntimeError(f"Queue polling connection error: {e.reason}")
    except socket.timeout:
        raise RuntimeError("Queue polling timed out.")
    except json.JSONDecodeError:
        raise RuntimeError("Invalid JSON received while polling queue.")

    raise RuntimeError("No output received from Space.")

# ------------------------------------------------------------
# Download Generated Results
# ------------------------------------------------------------

def _download_results(output, textures_dir, timestamp, diffuse_path):
    """
    Download all expected PBR maps and return texture dictionary.
    """
    if not isinstance(output, list) or len(output) < 4:
        raise RuntimeError(f"Unexpected output format: {output}")

    output_dir = textures_dir

    try:
        depth = _download_file(output[0]["url"], os.path.join(output_dir, f"depth_{timestamp}.png"))
        normal = _download_file(output[1]["url"], os.path.join(output_dir, f"normal_{timestamp}.png"))
        roughness = _download_file(output[2]["url"], os.path.join(output_dir, f"roughness_{timestamp}.png"))
        mask = _download_file(output[3]["url"], os.path.join(output_dir, f"mask_{timestamp}.png"))
    except KeyError as e:
        raise RuntimeError(f"Missing expected output field: {e}")

    textures = {
        "diffuse": diffuse_path,
        "depth": depth,
        "normal": normal,
        "roughness": roughness,
        "mask": mask,
    }

    return textures


# ------------------------------------------------------------
# File Downloader Helper
# ------------------------------------------------------------

def _download_file(url, path):
    """
    Download file from URL and write to disk.
    Returns local file path.
    """
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Download HTTP error: {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Download connection error: {e.reason}")
    except socket.timeout:
        raise RuntimeError("Download timed out.")

    try:
        with open(path, "wb") as f:
            f.write(data)
    except OSError as e:
        raise RuntimeError(f"Failed to write file {path}: {e}")

    return path
