"""Generate a paginated, text-searchable evaluation PDF from benchmark results."""

from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#15283f")
BLUE = colors.HexColor("#245fa0")
PALE = colors.HexColor("#edf3f8")


def generate_pdf_report(report: dict, output_path: str | Path) -> Path:
    """Export execution health, subjective alignment and per-case evidence separately."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    font_dir = Path(reportlab.__file__).parent / "fonts"
    for name, filename in (("BenchmarkSans", "Vera.ttf"), ("BenchmarkBold", "VeraBd.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(font_dir / filename)))
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        if isinstance(style, ParagraphStyle):
            style.fontName = "BenchmarkBold" if "Bold" in style.fontName else "BenchmarkSans"
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            fontName="BenchmarkBold",
            fontSize=26,
            leading=31,
            textColor=INK,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Deck", fontName="BenchmarkSans", fontSize=11, leading=16, textColor=INK, spaceAfter=10
        )
    )
    styles.add(ParagraphStyle(name="Cell", fontName="BenchmarkSans", fontSize=8, leading=11, textColor=INK))
    styles.add(
        ParagraphStyle(name="White", fontName="BenchmarkBold", fontSize=8, leading=11, textColor=colors.white)
    )
    styles.add(
        ParagraphStyle(
            name="Metric",
            fontName="BenchmarkBold",
            fontSize=13,
            leading=19,
            textColor=INK,
            alignment=TA_CENTER,
        )
    )

    def p(text, style="Cell"):
        return Paragraph(escape(str(text)), styles[style])

    def pct(value):
        return "N/A" if value is None else f"{value:.2f}%"

    def table(headers, rows, widths):
        body = [[p(v, "White") for v in headers]] + [[p(v) for v in row] for row in rows]
        result = Table(body, colWidths=widths, repeatRows=1, hAlign="LEFT")
        result.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), INK),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return result

    width, height = landscape(A4)
    available = width - 32 * mm
    doc = SimpleDocTemplate(
        str(path),
        pagesize=(width, height),
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="CV-to-Job Matching Benchmark",
        author="Enterprise CV Parser",
    )
    summary = report["summary"]
    story = [
        p("CV-to-Job Matching Benchmark", "ReportTitle"),
        p("Independent AI-authored targets vs application scoring | 10 synthetic CV-JD pairs", "Deck"),
    ]
    banner = Table(
        [
            [
                p(f"{summary['total_cases']} CASES", "Metric"),
                p(f"MAE {summary['mae']:.2f} pp" if summary["mae"] is not None else "MAE N/A", "Metric"),
                p(f"ALIGNMENT {pct(summary['model_alignment_score'])}", "Metric"),
                p(f"STATUS {summary['final_status']}", "Metric"),
            ]
        ],
        colWidths=[available / 4] * 4,
    )
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    story += [
        banner,
        Spacer(1, 9 * mm),
        p(
            f"Execution: {summary['executed_successfully']}/{summary['total_cases']} successful ({summary['execution_success_rate']:.0f}%). Alignment: {summary['aligned_cases']}/{summary['total_cases']} within 10 percentage points. Generated {report['generated_at'][:19].replace('T', ' ')} UTC.",
            "Deck",
        ),
    ]
    headers = ["Pair", "Candidate role", "Job title", "AI baseline", "App score", "Delta (pp)", "Alignment"]
    rows = [
        [
            f"{r['pair_id']:02d}",
            r["candidate_role"],
            r["job_title"],
            pct(r["ai_expected_score"]),
            pct(r["app_model_score"]),
            "N/A" if r["absolute_delta"] is None else f"{r['absolute_delta']:.2f}",
            r["alignment_status"],
        ]
        for r in report["results"]
    ]
    story += [
        table(headers, rows, [42, 155, 155, 82, 82, 70, available - 586]),
        Spacer(1, 5 * mm),
        p(
            "MAE and deltas are percentage-point errors, not statistical precision. Alignment score = 100 - MAE. Final PASS requires every case to execute and every absolute delta to be at most 10 points."
        ),
    ]
    story += [
        PageBreak(),
        p("Granular category comparison", "ReportTitle"),
        p(
            "Each cell shows AI baseline / application score. Category labels are independently judged; they are not back-calculated from the application's weighting formula.",
            "Deck",
        ),
    ]
    rows = [
        [
            f"{r['pair_id']:02d}",
            *[
                f"{r['ai_expected_breakdown'][g]:.1f} / {r['app_model_breakdown'][g]:.1f}"
                if r["execution_status"] == "PASS"
                else "Execution error"
                for g in ("skills", "context", "experience", "education")
            ],
        ]
        for r in report["results"]
    ]
    story += [
        table(
            ["Pair", "Skills (%)", "Context (%)", "Experience (%)", "Education (%)"],
            rows,
            [40] + [(available - 40) / 4] * 4,
        ),
        Spacer(1, 7 * mm),
        p("Evaluation protocol", "Heading2"),
        p(report["baseline_source"], "Deck"),
        p(
            "Overall baseline targets and category judgments were frozen before application execution. They are subjective reference labels, not verified ground truth. The model's original weights, constraints and scores were not changed to improve this benchmark. Ten synthetic examples cannot establish real-world accuracy.",
            "Deck",
        ),
        p(
            f"Requested backend: {report['configuration']['backend_requested']}; reranker enabled: {report['configuration']['rerank_enabled']}. Actual methods: {', '.join(sorted({r['response']['semantic_method'] for r in report['results'] if r['response']}))}. No live external AI evaluator was called."
        ),
        p(f"Dataset SHA-256: {report['dataset_sha256']}"),
    ]
    story += [
        PageBreak(),
        p("Discrepancies & tuning priorities", "ReportTitle"),
        p(
            "Cases outside the predeclared tolerance. Suggestions are hypotheses for a separate held-out benchmark, not automatic tuning instructions.",
            "Deck",
        ),
    ]
    discrepant = [r for r in report["results"] if r["alignment_status"] != "PASS"]
    if not discrepant:
        story.append(
            p(
                "All ten cases are within tolerance. Expand the evaluation with independently reviewed real CVs before making accuracy claims.",
                "Deck",
            )
        )
    for r in discrepant:
        story.append(
            KeepTogether(
                [
                    p(f"Pair {r['pair_id']:02d} | {r['candidate_role']} to {r['job_title']}", "Heading2"),
                    p("Baseline rationale: " + r["baseline_rationale"], "Deck"),
                    *[p("- " + item, "Deck") for item in r["insights"]],
                ]
            )
        )
    story += [
        PageBreak(),
        p("Per-case scoring evidence", "ReportTitle"),
        p(
            "The following pages preserve all 12 application sub-scores. Complete synthetic CVs, JDs, model responses, routing and warnings are in the companion benchmark_match_results.json.",
            "Deck",
        ),
    ]
    for r in report["results"]:
        values = []
        if r["response"]:
            for group in ("skills", "context", "experience", "education"):
                for key, value in r["response"]["breakdown"][group].items():
                    values.append([group.title(), key.replace("_", " "), pct(value)])
        else:
            values = [["Execution", "See companion JSON for traceback", "ERROR"]]
        story.append(
            KeepTogether(
                [
                    p(f"Pair {r['pair_id']:02d} | {r['candidate_role']} to {r['job_title']}", "Heading2"),
                    p(r["baseline_rationale"], "Deck"),
                    table(["Category", "Sub-score", "App (%)"], values, [100, available - 190, 90]),
                ]
            )
        )
        story.append(Spacer(1, 6 * mm))

    def footer(canvas, document):
        canvas.setStrokeColor(BLUE)
        canvas.line(16 * mm, 12 * mm, width - 16 * mm, 12 * mm)
        canvas.setFont("BenchmarkSans", 8)
        canvas.setFillColor(INK)
        canvas.drawString(
            16 * mm, 8 * mm, "ENTERPRISE CV PARSER | Synthetic evaluation - not a hiring decision"
        )
        canvas.drawRightString(width - 16 * mm, 8 * mm, f"{document.page}")

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path
