# this exists to list / build the images in docker
import yaml
import sys
import subprocess

with open('dockerfile_gen/generated/benchmark_environments.yaml', 'r') as f:
    parsed = yaml.safe_load(f)
entries = dict()
for env in parsed["environments"]:
    entries[env["target"]] = env["image"]

if sys.argv[1:] == ["list"]:
    for image in entries.values():
        print(image)
elif sys.argv[1:] == ["build"]:
    for target, image in entries.items():
        print(f"building {target} as {image}...", flush=True)
        subprocess.run(["docker", "build",
                        "-f", "dockerfile_gen/generated/Dockerfile",
                        "--target", target, "-t", image, "."], check=True)
        print(f"image \"{image}\" successfully built.", flush=True)
else:
    sys.exit("usage: images.py [list|build]")

