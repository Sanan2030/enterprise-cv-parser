"""Deterministic synthetic PDF stress suite. Run with the parser's dependencies.

python cv_stress_test.py --repo ./enterprise-cv-parser --output ./cv-stress-results
Runs locally with VERCEL=1, not against the live deployment. No LLM calls.
"""

import argparse
import concurrent.futures
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pymupdf as fitz
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
HEADERS = ["Summary", "Experience", "Education", "Skills", "Languages", "Certifications", "Projects"]
BODY = [
    ["Builds reliable software and clear business requirements."],
    ["Software Engineer | Example Systems", "Jan 2021 - Mar 2023", "- Built APIs with Python and SQL."],
    ["Example University", "Bachelor of Science: Computer Science", "Sep 2016 - Jun 2020", "GPA: 3.8/4.0"],
    ["Python, SQL, Docker, Communication"],
    ["English - C1", "Turkish - B2"],
    [
        "Certificate: Cloud Developer",
        "Issuer: Example Academy",
        "Issue Date: Jan 2024",
        "Credential ID: ABC-123",
    ],
    [
        "Project: Payments API",
        "Description: Processes payments.",
        "Technologies: Python, SQL",
        "Role: Developer",
    ],
]


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def base_expectations(name="Alex Morgan"):
    return {
        "personalInformation.fullName": name,
        "contactInformation.email": "alex@example.org",
        "contactInformation.mobilePhone": "+994501234567",
        "experience.0.company": "Example Systems",
        "experience.0.position": "Software Engineer",
        "experience.0.startDate": "2021-01",
        "experience.0.endDate": "2023-03",
        "experience.0.duration": "2 yrs 2 mos",
        "education.0.university": "Example University",
        "education.0.gpa": "3.8/4.0",
        "languages.0.level": "C1",
        "certifications.0.credentialID": "ABC-123",
        "projects.0.projectName": "Payments API",
        "skills.technical": {"contains": "Python"},
    }


def make_pdf(path, variant="standard", headers=None, name="Alex Morgan"):
    headers = headers or HEADERS
    c = canvas.Canvas(str(path), pagesize=(595, 842), invariant=1)
    c.setTitle("Synthetic CV stress fixture - " + variant)
    c.setAuthor("Synthetic test data")
    size = 8 if variant == "small_font" else 10

    def line(text, x, y, font_size=size):
        c.setFont("Fixture", font_size)
        c.drawString(x, 842 - y, text)

    if variant == "dark":
        c.setFillColorRGB(0.06, 0.09, 0.16)
        c.rect(0, 0, 595, 842, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
    if variant in ("graphics", "watermark", "photo"):
        c.setFillColorRGB(0.88, 0.91, 0.95)
        for i in range(18):
            c.circle(530, 70 + i * 40, 22, fill=1, stroke=0)
        if variant == "watermark":
            c.saveState()
            c.translate(150, 250)
            c.rotate(45)
            c.setFont("Fixture", 64)
            c.drawString(0, 0, "SYNTHETIC")
            c.restoreState()
        if variant == "photo":
            c.rect(470, 700, 90, 100, fill=1, stroke=0)
            c.setFillColorRGB(0.5, 0.55, 0.65)
            c.circle(515, 765, 17, fill=1, stroke=0)
            c.ellipse(485, 710, 545, 745, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)
    line(name, 40, 35, 20)
    if variant == "wrapped_name":
        # Actual line wrapping, with matching font evidence.
        c.setFillColorRGB(1, 1, 1)
        c.rect(35, 797, 300, 30, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)
        line("Alex", 40, 35, 20)
        line("Morgan", 40, 59, 20)
    line("alex@example.org", 40, 82)
    line("+994 50 123 45 67", 40, 98)
    c.linkURL("https://www.linkedin.com/in/alex-example/", (40, 805, 240, 830), relative=0)
    if variant in ("sidebar", "reverse_columns", "three_columns", "uneven_columns"):
        columns = [[2, 3, 4], [0, 1, 5, 6]]
        xs = [40, 260]
        if variant == "reverse_columns":
            columns.reverse()
        if variant == "three_columns":
            columns, xs = [[2, 4], [0, 1], [3, 5, 6]], [25, 210, 400]
        if variant == "uneven_columns":
            xs = [25, 205]
        for x, sections in zip(xs, columns):
            y = 130
            for index in sections:
                line(headers[index], x, y, 11)
                y += 20
                # Wrap long text to the available column width.
                width = 170 if variant == "three_columns" else 165 if x < 100 else 300
                for text in BODY[index]:
                    words = text.split()
                    current = ""
                    for word in words:
                        if current and pdfmetrics.stringWidth(current + " " + word, "Fixture", size) > width:
                            line(current, x, y)
                            y += 14
                            current = word
                        else:
                            current = (current + " " + word).strip()
                    line(current, x, y)
                    y += 14
                y += 22
    else:
        y = 125
        for index, header in enumerate(headers):
            if variant in ("multipage", "hybrid") and index == 3:
                c.showPage()
                y = 45
            if variant == "three_pages" and index in (2, 5):
                c.showPage()
                y = 45
            line(header, 40, y, 12)
            y += 19
            for text in BODY[index]:
                line(text, 40, y)
                y += 16
            y += 8
    c.save()


def rasterize(path, dpi=160, rotation=0, contrast=False, hybrid=False):
    with fitz.open(path) as source, fitz.open() as dest:
        for i, page in enumerate(source):
            if hybrid and i == 0:
                dest.insert_pdf(source, from_page=i, to_page=i)
                continue
            pix = page.get_pixmap(dpi=dpi)
            data = pix.tobytes("png")
            if contrast:
                from PIL import Image, ImageEnhance

                image = Image.open(io.BytesIO(data)).convert("RGB")
                image = ImageEnhance.Contrast(image).enhance(0.22)
                out = io.BytesIO()
                image.save(out, format="PNG")
                data = out.getvalue()
            target = dest.new_page(width=page.rect.width, height=page.rect.height)
            target.insert_image(target.rect, stream=data)
            if rotation:
                target.set_rotation(rotation)
        data = dest.tobytes(garbage=4, deflate=True)
    path.write_bytes(data)


def generate(root):
    pdfmetrics.registerFont(TTFont("Fixture", FONT))
    fixtures = root / "fixtures"
    fixtures.mkdir()
    cases = []

    def add(category, variant, **kwargs):
        case_id = f"{len(cases) + 1:02d}_{category}_{variant}"
        path = fixtures / (case_id + ".pdf")
        make_pdf(path, variant=variant, **kwargs)
        case = {
            "id": case_id,
            "category": category,
            "file": str(path.relative_to(root)),
            "expected": base_expectations(kwargs.get("name", "Alex Morgan")),
        }
        cases.append(case)
        return path, case

    for variant in ["standard", "small_font", "unicode", "wrapped_name"]:
        add("native", variant, name="Renée Morgan" if variant == "unicode" else "Alex Morgan")
    for variant in ["sidebar", "reverse_columns", "three_columns", "uneven_columns"]:
        add("columns", variant)
    for variant, dpi, rotation, contrast in [
        ("scan_160dpi", 160, 0, False),
        ("scan_220dpi", 220, 0, False),
        ("scan_rotated", 160, 90, False),
        ("scan_low_contrast", 120, 0, True),
    ]:
        path, _ = add("ocr", variant)
        rasterize(path, dpi, rotation, contrast)
    for variant in ["missing_cmap", "incorrect_cmap", "accented_missing_cmap", "unicode_decomposed"]:
        name = "Renée Morgan" if variant == "accented_missing_cmap" else "Alex Morgan"
        if variant == "unicode_decomposed":
            name = unicodedata.normalize("NFD", "Renée Morgan")
        path, case = add("encoding", variant, name=name)
        case["expected"]["personalInformation.fullName"] = unicodedata.normalize("NFC", name)
        if variant != "unicode_decomposed":
            with fitz.open(path) as doc:
                for font in doc[0].get_fonts():
                    xref = font[0]
                    kind, val = doc.xref_get_key(xref, "ToUnicode")
                    if kind == "xref":
                        if variant == "incorrect_cmap":
                            cmap = int(val.split()[0])
                            data = doc.xref_stream(cmap)
                            data = data.replace(b"<0041>", b"<005A>").replace(b"<0061>", b"<007A>")
                            doc.update_stream(cmap, data)
                        else:
                            doc.xref_set_key(xref, "ToUnicode", "null")
                data = doc.tobytes(garbage=4, deflate=True)
            path.write_bytes(data)
    for variant, replacement in [
        ("career_journey", "Career Journey"),
        ("professional_background", "Professional Background"),
        ("employment_record", "Employment Record"),
        ("my_toolbox", "My Toolbox"),
    ]:
        headers = HEADERS.copy()
        headers[3 if variant == "my_toolbox" else 1] = replacement
        add("headers", variant, headers=headers)
    translations = {
        "az": ["HAQQIMDA", "İŞ TƏCRÜBƏSİ", "TƏHSİL", "BACARIQLAR", "DİLLƏR", "SERTİFİKATLAR", "LAYİHƏLƏR"],
        "tr": ["Özet", "İş Deneyimi", "Eğitim", "Yetenekler", "Diller", "Sertifikalar", "Projeler"],
        "ru": ["О себе", "Опыт работы", "Образование", "Навыки", "Языки", "Сертификаты", "Проекты"],
        "mixed": ["Summary", "İŞ TƏCRÜBƏSİ", "Образование", "Skills", "DİLLƏR", "Certificates", "Projects"],
    }
    for language, headers in translations.items():
        add("language", language, headers=headers)
    for variant in ["graphics", "watermark", "photo", "dark"]:
        add("graphics", variant)
    for variant in ["multipage", "three_pages", "hybrid", "standard"]:
        path, _ = add("pagination", variant)
        if variant == "hybrid":
            rasterize(path, hybrid=True)
    for variant in ["truncated", "bad_header", "encrypted", "blank", "too_many_pages", "oversize"]:
        path, case = add("invalid", variant)
        case["expected"] = {}
        case["expected_exception"] = (
            "SecurityException" if variant in ("too_many_pages", "oversize") else "InvalidPDFException"
        )
        if variant == "truncated":
            path.write_bytes(path.read_bytes()[:-200])
        elif variant == "bad_header":
            path.write_bytes(b"NOTPDF!!" + path.read_bytes()[8:])
        elif variant == "oversize":
            path.write_bytes(path.read_bytes() + b" " * (16 * 1024 * 1024))
        elif variant in ("blank", "too_many_pages"):
            with fitz.open() as doc:
                for _ in range(31 if variant == "too_many_pages" else 1):
                    doc.new_page()
                doc.save(path)
        elif variant == "encrypted":
            with fitz.open(path) as doc:
                data = doc.tobytes(
                    encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="test-owner", user_pw="test-user"
                )
            path.write_bytes(data)
    for case in cases:
        path = root / case["file"]
        case["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        case["size_bytes"] = path.stat().st_size
    dump(root / "manifest.json", cases)
    return cases


def get_path(data, path):
    for key in path.split("."):
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


def worker(repo, root, case_id):
    sys.path.insert(0, str(repo))
    from app.services.dashboard_adapter import adapt_resume
    from app.services.resume_parser import ResumeParserService

    case = next(c for c in json.loads((root / "manifest.json").read_text()) if c["id"] == case_id)
    folder = root / "runs" / case_id
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / case["file"], folder / "input.pdf")
    dump(folder / "expected.json", case)
    started = time.perf_counter()
    response = None
    native = None
    mismatches = []
    error = None
    status = "FAIL"
    try:
        native = ResumeParserService().parse_pdf((folder / "input.pdf").read_bytes(), "input.pdf")
        response = adapt_resume(native).model_dump(mode="json")
        if case.get("expected_exception"):
            mismatches.append("Invalid input was accepted; expected " + case["expected_exception"])
        for field, expected in case["expected"].items():
            try:
                actual = get_path(response, field)
            except (KeyError, IndexError, TypeError):
                actual = None
            if isinstance(expected, dict):
                ok = isinstance(actual, list) and expected["contains"] in actual
            else:
                ok = isinstance(actual, str) and unicodedata.normalize("NFC", actual) == expected
            if not ok:
                mismatches.append({"field": field, "expected": expected, "actual": actual})
        if mismatches:
            raise AssertionError(json.dumps(mismatches, ensure_ascii=False))
        status = "PASS"
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
        (folder / "traceback.log").write_text(traceback.format_exc(), encoding="utf-8")
        if case.get("expected_exception") == type(exc).__name__:
            status = "EXPECTED_REJECTION"
    dump(folder / "response.json", response)
    dump(folder / "native_response.json", native.model_dump(mode="json") if native else None)
    dump(folder / "error.json", error)
    if not (folder / "traceback.log").exists():
        (folder / "traceback.log").write_text("No exception raised.\n")
    result = {
        "id": case_id,
        "category": case["category"],
        "status": status,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "mismatches": mismatches,
        "error": error,
    }
    dump(folder / "result.json", result)


def run_case(repo, root, case):
    folder = root / "runs" / case["id"]
    folder.mkdir(parents=True)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--repo",
        str(repo),
        "--output",
        str(root),
        "--worker",
        case["id"],
    ]
    env = os.environ.copy()
    env.update(VERCEL="1", USE_LLM_FALLBACK="false", SPACY_MODEL="", OMP_THREAD_LIMIT="1")
    # An empty model setting is equivalent to the project's disabled default.
    started = time.perf_counter()
    with (folder / "stdout.log").open("w") as stdout, (folder / "stderr.log").open("w") as stderr:
        try:
            process = subprocess.run(command, env=env, stdout=stdout, stderr=stderr, timeout=60)
            if process.returncode:
                raise RuntimeError(f"Worker exited with code {process.returncode}")
        except Exception as exc:
            shutil.copy2(root / case["file"], folder / "input.pdf")
            dump(folder / "response.json", None)
            dump(folder / "native_response.json", None)
            dump(folder / "expected.json", case)
            error = {"type": type(exc).__name__, "message": str(exc)}
            dump(folder / "error.json", error)
            (folder / "traceback.log").write_text(traceback.format_exc())
            dump(
                folder / "result.json",
                {
                    "id": case["id"],
                    "category": case["category"],
                    "status": "FAIL",
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "mismatches": [],
                    "error": error,
                },
            )
    result = json.loads((folder / "result.json").read_text())
    if result["status"] != "PASS":
        destination = root / ("failed_tests" if result["status"] == "FAIL" else "rejected_tests") / case["id"]
        shutil.copytree(folder, destination)
        result["artifact_directory"] = str(destination.relative_to(root))
    else:
        result["artifact_directory"] = str(folder.relative_to(root))
    print(result["id"], result["status"], result["elapsed_seconds"], flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker")
    parser.add_argument("--corpus", type=Path, help="Replay saved fixtures and unchanged expectations")
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = args.output.resolve()
    if args.worker:
        worker(repo, root, args.worker)
        return
    root.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    if args.corpus:
        shutil.copytree(args.corpus / "fixtures", root / "fixtures")
        shutil.copy2(args.corpus / "manifest.json", root / "manifest.json")
        cases = json.loads((root / "manifest.json").read_text())
        for case in cases:
            if hashlib.sha256((root / case["file"]).read_bytes()).hexdigest() != case["sha256"]:
                raise ValueError("Fixture checksum mismatch: " + case["id"])
    else:
        cases = generate(root)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda c: run_case(repo, root, c), cases))
    failed = [r for r in results if r["status"] == "FAIL"]
    rejected = [r for r in results if r["status"] == "EXPECTED_REJECTION"]
    passed = [r for r in results if r["status"] == "PASS"]
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_pdfs": len(cases),
        "extraction_pass": len(passed),
        "expected_rejections": len(rejected),
        "pass_including_expected_rejections": len(passed) + len(rejected),
        "fail": len(failed),
        "failure_rate_percent": round(len(failed) / len(cases) * 100, 2),
        "valid_pdf_count": sum("expected_exception" not in c for c in cases),
        "wall_seconds": round(time.perf_counter() - started, 3),
        "configuration": {
            "python": platform.python_version(),
            "vercel_mode": True,
            "llm": False,
            "spacy": False,
            "parallel_workers": 2,
            "timeout_seconds": 60,
            "source_tree": subprocess.check_output(
                ["git", "rev-parse", "HEAD^{tree}"], cwd=repo, text=True
            ).strip(),
            "app_source_sha256": {
                str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((repo / "app").rglob("*.py"))
            },
        },
        "results": results,
    }
    dump(root / "report.json", report)
    lines = [
        "# CV parser stress-test report",
        "",
        f"Total: {len(cases)} | Extraction passes: {len(passed)} | Expected rejections: {len(rejected)} | Failures: {len(failed)} | Failure rate: {report['failure_rate_percent']}%",
        "",
        "Local service pipeline with VERCEL=1, LLM disabled, no spaCy model, real English OCR; two isolated workers, 60 seconds per case. This is a deterministic synthetic robustness batch, not a live HTTP load test or a population accuracy estimate.",
        "",
        "32 readable fixtures and 6 deliberately invalid/unreadable inputs. A pass requires all manifest field assertions; an expected rejection requires the specified exception type. JSON null means extraction failed before a schema was available. Assertion tracebacks describe field mismatches, not parser crashes.",
        "",
        f"Source tree: `{report['configuration']['source_tree']}`. Wall time: {report['wall_seconds']} seconds.",
        "",
        "## All cases",
        "",
        "| Case | Category | Result | Seconds | Artifacts |",
        "|---|---|---|---:|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['id']} | {r['category']} | {r['status']} | {r['elapsed_seconds']} | `{r['artifact_directory']}/` |"
        )
    lines += ["", "## Failed case details", ""]
    for r in failed:
        lines += [
            f"### {r['id']}",
            "",
            f"Directory: `{r['artifact_directory']}/`",
            "",
            "Files: `input.pdf`, `response.json`, `native_response.json`, `expected.json`, `result.json`, `error.json`, `traceback.log`, `stdout.log`, `stderr.log`.",
            "",
            "```json",
            json.dumps(r["mismatches"] or r["error"], ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    (root / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    shutil.copy2(__file__, root / "cv_stress_test.py")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    main()
