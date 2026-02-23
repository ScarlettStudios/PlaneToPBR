import urllib.request
import json
import os
import uuid

SPACE_BASE = "https://ascarlettvfx-testpbr2026.hf.space"
ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
TEXTURE_DIR = os.path.join(ADDON_DIR, "textures")
os.makedirs(TEXTURE_DIR, exist_ok=True)

def call_hf_pbr(image_path, prompt=""):

    fn_index = _resolve_fn_index("predict")

    session_hash = uuid.uuid4().hex

    with open(image_path, "rb") as f:
        raw_bytes = f.read()

    uploaded_path = _upload_file(image_path, raw_bytes)
    filename = os.path.basename(image_path)

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

    event_id = _join_queue(payload)
    print("Joined queue:", event_id)

    output = _poll_queue(session_hash)
    diffuse_path = os.path.join(TEXTURE_DIR, "diffuse.png")
    with open(diffuse_path, "wb") as out:
        out.write(raw_bytes)

    return _download_results(output)


def _resolve_fn_index(api_name="predict"):
    """
    Resolve the fn_index for a given Gradio api_name
    from the Space config endpoint.
    """
    try:
        with urllib.request.urlopen(f"{SPACE_BASE}/config") as resp:
            config = json.loads(resp.read().decode())
    except Exception as e:
        raise RuntimeError(f"Failed to fetch Space config: {e}")

    dependencies = config.get("dependencies")
    if not dependencies:
        raise RuntimeError("Space config missing 'dependencies' field.")

    for i, dep in enumerate(dependencies):
        if dep.get("api_name") == api_name:
            return i

    raise RuntimeError(f"api_name '{api_name}' not found in Space config.")

def _upload_file(image_path, raw_bytes):
    """
    Upload a file to the Gradio Space and return the uploaded path.
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

    with urllib.request.urlopen(upload_req) as resp:
        upload_data = json.loads(resp.read().decode())

    return upload_data[0]

def _join_queue(payload):
    """
    Join the Gradio queue and return the event_id.
    """
    join_req = urllib.request.Request(
        f"{SPACE_BASE}/gradio_api/queue/join",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(join_req) as resp:
            join_data = json.loads(resp.read().decode())
    except Exception as e:
        raise RuntimeError(f"Failed to join queue: {e}")

    event_id = join_data.get("event_id")
    if not event_id:
        raise RuntimeError(f"Invalid queue response: {join_data}")

    return event_id

def _poll_queue(session_hash):
    """
    Poll the Gradio SSE queue until processing completes.
    Returns the output data list.
    """

    poll_url = f"{SPACE_BASE}/gradio_api/queue/data?session_hash={session_hash}"

    with urllib.request.urlopen(poll_url) as resp:
        for raw_line in resp:
            line = raw_line.decode().strip()

            if not line.startswith("data:"):
                continue

            json_str = line.replace("data:", "").strip()
            if not json_str:
                continue

            event = json.loads(json_str)

            if event.get("msg") == "process_completed":
                result_output = event.get("output")

                if isinstance(result_output, dict) and result_output.get("data"):
                    return result_output["data"]
                else:
                    raise RuntimeError(f"Space error: {event}")

            if event.get("msg") == "process_failed":
                raise RuntimeError(f"Space failed: {event}")

    raise RuntimeError("No output received from Space.")

def _download_results(output):
    if not isinstance(output, list) or len(output) < 4:
        raise RuntimeError(f"Unexpected output format: {output}")

    output_dir = TEXTURE_DIR

    depth = _download_file(output[0]["url"], os.path.join(output_dir, "depth.png"))
    normal = _download_file(output[1]["url"], os.path.join(output_dir, "normal.png"))
    roughness = _download_file(output[2]["url"], os.path.join(output_dir, "roughness.png"))
    mask = _download_file(output[3]["url"], os.path.join(output_dir, "mask.png"))

    textures = {
        "diffuse": os.path.join(TEXTURE_DIR, "diffuse.png"),
        "depth": depth,
        "normal": normal,
        "roughness": roughness,
        "mask": mask,
    }

    return textures

def _download_file(url, path):
    with urllib.request.urlopen(url) as resp:
        data = resp.read()
    with open(path, "wb") as f:
        f.write(data)
    return path
