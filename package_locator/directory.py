import tempfile
import os
import json
from git import Repo
from pathlib import Path
from os.path import join, relpath
import toml
import re
import requests
from zipfile import ZipFile
import tarfile

from package_locator.common import NotPackageRepository


def locate_file_in_dir(repo_path, target_file):
    """locate *filename"""

    candidates = []
    for root, dirs, files in os.walk(repo_path):
        for file in files:
            if file.endswith(target_file):
                candidates.append(relpath(join(root, file), repo_path))
    return candidates


def locate_dir_in_repo(repo_path, target_dir):
    """return the top-level dir"""
    candidates = []
    for root, dirs, files in os.walk(repo_path):
        for dir in dirs:
            if dir.endswith(target_dir):
                candidates.append(relpath(join(root, dir), repo_path))
    return candidates


def get_package_name_from_npm_json(filepath):
    with open(filepath, "r") as f:
        try:
            data = json.load(f)
            return data.get("name", None)
        except:
            # there could be test files for erroneous data
            return None


def get_package_name_from_composer_json(filepath):
    with open(filepath, "r") as f:
        try:
            data = json.load(f)
            return data.get("name", None)
        except:
            # there could be test files for erroneous data
            return None


def get_package_name_from_cargo_toml(filepath):
    with open(filepath, "r") as f:
        try:
            data = toml.load(f)
            return data.get("package", {}).get("name", None)
        except:
            # there could be test files for erroneous data
            return None


def get_npm_subdir(package, repo_url):
    manifest_filename = "package.json"
    temp_dir = tempfile.TemporaryDirectory()
    repo = Repo.clone_from(repo_url, temp_dir.name)
    repo_path = Path(repo.git_dir).parent

    subdirs = locate_file_in_dir(repo_path, manifest_filename)
    for subdir in subdirs:
        name = get_package_name_from_npm_json(join(repo_path, subdir))
        if name and (name.endswith(package) or name.replace("/", "-").endswith(package.replace("/", "-"))):
            return subdir.removesuffix(manifest_filename).removesuffix("/")
    raise NotPackageRepository


def get_rubygems_subdir(package, repo_url):
    manifest_filename = ".gemspec".format(package)
    temp_dir = tempfile.TemporaryDirectory()
    repo = Repo.clone_from(repo_url, temp_dir.name)
    repo_path = Path(repo.git_dir).parent

    candidate_manifests = locate_file_in_dir(repo_path, manifest_filename)
    pattern = re.compile(r"""name(\s*)=(\s*)("|'){}("|')""".format(package))
    for candidate in candidate_manifests:
        with open(join(repo_path, candidate), "r") as f:
            for line in f:
                if re.search(pattern, line):
                    subdir = Path(candidate).parent
                    return str(subdir).removesuffix(".").removesuffix("/")
    raise NotPackageRepository


def get_composer_subdir(package, repo_url):
    manifest_filename = "composer.json"
    temp_dir = tempfile.TemporaryDirectory()
    repo = Repo.clone_from(repo_url, temp_dir.name)
    repo_path = Path(repo.git_dir).parent

    subdirs = locate_file_in_dir(repo_path, manifest_filename)
    for subdir in subdirs:
        if get_package_name_from_composer_json(join(repo_path, subdir)) == package:
            return subdir.removesuffix(manifest_filename).removesuffix("/")
    raise NotPackageRepository


def get_cargo_subdir(package, repo_url):
    manifest_filename = "Cargo.toml"
    temp_dir = tempfile.TemporaryDirectory()
    repo = Repo.clone_from(repo_url, temp_dir.name)
    repo_path = Path(repo.git_dir).parent

    subdirs = locate_file_in_dir(repo_path, manifest_filename)
    for subdir in subdirs:
        if get_package_name_from_cargo_toml(join(repo_path, subdir)) == package:
            return subdir.removesuffix(manifest_filename).removesuffix("/")
    raise NotPackageRepository


def get_pypi_wheel(package):
    # get download link for the latest wheel
    url = "https://pypi.org/pypi/{}/json".format(package)
    page = requests.get(url)
    data = json.loads(page.content)
    data = data["releases"]
    latest_version = list(data.keys())[-1]
    url = data[latest_version][-1]["url"]

    # download wheel
    temp_dir = tempfile.TemporaryDirectory()
    path = temp_dir.name
    compressed_file_name = "wheel.tar.gz"
    dest_file = "{}/{}".format(path, compressed_file_name)
    r = requests.get(url, stream=True)
    with open(dest_file, "wb") as output_file:
        output_file.write(r.content)

    # extract file
    t = tarfile.open(dest_file)
    t.extractall(path)
    t.close()

    dirs = os.listdir(path)
    for dir in dirs:
        dirpath = join(path, dir)
        init_files = locate_file_in_dir(dirpath, "__init__.py")
        if not init_files:
            continue
        # we want to ge the the top-level init file
        init_files.sort(key=lambda x: len(x.split("/")))
        return init_files[0]


def get_pypi_subdir(package, repo_url):
    """
    There is no manifest file for pypi
    We work on the heuristic that python packages have a common pattern
    of putting library specific code into a directory named on the package
    and then checking if the directory contains a __init__.py files
    indicating to be a python module
    """
    temp_dir = tempfile.TemporaryDirectory()
    repo = Repo.clone_from(repo_url, temp_dir.name)
    repo_path = Path(repo.git_dir).parent
    candidate_dirs = locate_dir_in_repo(repo_path, package)
    init_filename = "__init__.py"
    for dir in candidate_dirs:
        init_files = locate_file_in_dir(join(repo_path, dir), init_filename)
        if init_filename in init_files:
            return dir.removesuffix(package).removesuffix("/")
    raise NotPackageRepository
