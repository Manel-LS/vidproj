"""Rattache un clip video a une scene, depuis la ligne de commande.

Genere le clip ou tu veux (Colab, un autre outil, une camera), puis :

    python scripts/import_motion_clip.py mon-clip.mp4 --project <id> --scene <id>

Sans --scene, la premiere scene qui porte une image est utilisee.
Sans --project, les projets sont listes et le script s'arrete.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DEFAULT_API = "http://127.0.0.1:8001/api/v1"


def call(api, method, path, token=None, body=None, upload=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if upload:
        filename, content, content_type = upload
        boundary = "----rc" + uuid.uuid4().hex
        data = b"".join([
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode(),
            content, f"\r\n--{boundary}--\r\n".encode(),
        ])
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    else:
        data = None

    request = urllib.request.Request(api + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except (ValueError, OSError):
            return exc.code, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("clip", type=Path, help="le fichier MP4, MOV ou WebM")
    parser.add_argument("--project", default="", help="id du projet")
    parser.add_argument("--scene", default="", help="id de la scene (defaut : la premiere avec une image)")
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--email", default="demo@reelcraft.app")
    parser.add_argument("--password", default="demo1234")
    args = parser.parse_args()

    if not args.clip.is_file():
        print(f"Fichier introuvable : {args.clip}")
        return 1

    status, res = call(args.api, "POST", "/auth/login",
                       body={"email": args.email, "password": args.password})
    if status != 200:
        print(f"Connexion refusee ({status}). Verifie --email / --password.")
        return 1
    token = res["access_token"]

    if not args.project:
        status, res = call(args.api, "GET", "/projects", token=token)
        items = res["items"] if isinstance(res, dict) else res
        print("Indique un projet avec --project :\n")
        for project in items:
            print(f"  {project['id']}  {project['name']}")
        return 1

    scene_id = args.scene
    if not scene_id:
        status, res = call(args.api, "GET", f"/projects/{args.project}/scenes", token=token)
        if status != 200:
            print(f"Projet introuvable ({status}).")
            return 1
        scenes = res["items"] if isinstance(res, dict) else res
        with_image = [s for s in scenes if s.get("media_id")]
        if not with_image:
            print("Ce projet n'a aucune scene avec une image.")
            return 1
        scene_id = with_image[0]["id"]
        print(f"Scene choisie automatiquement : {scene_id}")

    content_type = mimetypes.guess_type(args.clip.name)[0] or "video/mp4"
    status, res = call(
        args.api, "POST", f"/projects/{args.project}/scenes/{scene_id}/motion-clip",
        token=token, upload=(args.clip.name, args.clip.read_bytes(), content_type),
    )
    if status != 201:
        message = (res or {}).get("error", {}).get("message") or res
        print(f"Refuse ({status}) : {message}")
        return 1

    print(f"\nClip rattache : {res['duration_seconds']:.1f}s, {res['width']}x{res['height']}")
    print("Lance un rendu du projet pour le voir dans le montage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
