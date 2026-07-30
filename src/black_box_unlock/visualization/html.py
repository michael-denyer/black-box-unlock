"""Self-contained HTML report generator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

from black_box_unlock.core.models import AnalysisResult
from black_box_unlock.visualization.report_data import build_report_payload


@dataclass(frozen=True, slots=True)
class ReportAssets:
    template: str
    report_css: str
    report_js: str
    echarts_js: str
    tabulator_css: str
    tabulator_js: str


def _resource_text(path: str) -> str:
    return (
        files("black_box_unlock.visualization")
        .joinpath("assets", *path.split("/"))
        .read_text(encoding="utf-8")
    )


@cache
def load_report_assets() -> ReportAssets:
    """Load pinned package resources once per process."""
    return ReportAssets(
        template=_resource_text("report.html"),
        report_css=_resource_text("report.css"),
        report_js=_resource_text("report.js"),
        echarts_js=_resource_text("vendor/echarts-6.1.0.min.js"),
        tabulator_css=_resource_text("vendor/tabulator-6.5.2.min.css"),
        tabulator_js=_resource_text("vendor/tabulator-6.5.2.min.js"),
    )


def _json_for_script(value: object) -> str:
    """Serialize JSON without allowing data to terminate its script element."""
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _replace_once(document: str, sentinel: str, value: str) -> str:
    if document.count(sentinel) != 1:
        raise ValueError(f"report template must contain {sentinel!r} exactly once")
    return document.replace(sentinel, value)


def generate_html_report(result: AnalysisResult) -> str:
    """Return one complete, offline HTML investigation report."""
    assets = load_report_assets()
    document = assets.template
    replacements = {
        "/*__TABULATOR_CSS__*/": assets.tabulator_css,
        "/*__REPORT_CSS__*/": assets.report_css,
        "/*__ECHARTS_JS__*/": assets.echarts_js,
        "/*__TABULATOR_JS__*/": assets.tabulator_js,
        "/*__REPORT_JS__*/": assets.report_js,
        "__CI_OBSERVATION_VISIBILITY__": (
            " hidden" if result.ci_status.state.value in {"disabled", "unavailable"} else ""
        ),
        "__REPORT_DATA__": _json_for_script(build_report_payload(result)),
    }
    for sentinel, value in replacements.items():
        document = _replace_once(document, sentinel, value)
    return document
