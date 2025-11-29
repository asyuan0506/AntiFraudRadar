import base64
import mimetypes
import os

def encode_image(image_path):
    """
    Read and base64-encode the image file.
    Args:
        image_path: Path to the image file.
    Returns:
        A base64-encoded data URL of the image.
    """

    accepted_extensions = [".png", ".jpeg", ".webp", ".gif"]
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    if not any(image_path.endswith(ext) for ext in accepted_extensions):
        raise ValueError(f"Unsupported image format: {image_path}")

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    mime = mimetypes.guess_type(image_path)[0] or "application/octet-stream"
    data_url = f"data:{mime};base64,{b64}"
    return data_url

def decode_image(data_url, output_path):
    """
    Decode a base64-encoded data URL and save it as an image file.
    Args:
        data_url: A base64-encoded data URL of the image.
        output_path: Path to save the decoded image file.
    """
    header, b64 = data_url.split(",", 1)
    with open(output_path, "wb") as f:
        f.write(base64.b64decode(b64))

