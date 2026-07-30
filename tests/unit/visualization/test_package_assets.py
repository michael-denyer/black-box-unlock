"""Checks that the offline report resources are complete and untampered."""

import hashlib
import json
from importlib.resources import files


def test_pinned_vendor_assets_match_manifest() -> None:
    vendor = files("black_box_unlock.visualization").joinpath("assets", "vendor")
    manifest = json.loads(vendor.joinpath("manifest.json").read_text(encoding="utf-8"))

    for package in ("echarts", "tabulator"):
        for filename, expected_hash in manifest[package]["files"].items():
            digest = hashlib.sha256(vendor.joinpath(filename).read_bytes()).hexdigest()
            assert digest == expected_hash


def test_report_assets_and_licences_ship_as_package_resources() -> None:
    assets = files("black_box_unlock.visualization").joinpath("assets")

    for filename in (
        "report.html",
        "report.css",
        "report.js",
        "vendor/ECHARTS-LICENSE.txt",
        "vendor/ECHARTS-NOTICE.txt",
        "vendor/TABULATOR-LICENSE.txt",
    ):
        assert assets.joinpath(*filename.split("/")).is_file()
