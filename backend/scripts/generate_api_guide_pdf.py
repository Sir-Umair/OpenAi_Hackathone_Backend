from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle


OUTPUT_PATH = Path(__file__).resolve().parents[1] / "O2N_Engine_API_Guide.pdf"


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style)


def code(text: str, style: ParagraphStyle) -> Preformatted:
    return Preformatted(text.strip(), style)


def footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#52606D"))
    canvas.drawString(1.5 * cm, 1.1 * cm, "O2N Engine API Guide")
    canvas.drawRightString(A4[0] - 1.5 * cm, 1.1 * cm, f"Page {document.page}")
    canvas.restoreState()


def build_pdf() -> None:
    document = SimpleDocTemplate(
        str(OUTPUT_PATH),
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.8 * cm,
        title="O2N Engine API Guide",
        author="O2N Engine",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("GuideTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=colors.HexColor("#17324D"), alignment=TA_CENTER, spaceAfter=8)
    subtitle = ParagraphStyle("Subtitle", parent=styles["BodyText"], fontSize=10, leading=14, textColor=colors.HexColor("#52606D"), alignment=TA_CENTER, spaceAfter=20)
    heading = ParagraphStyle("GuideHeading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=colors.HexColor("#0B6E69"), spaceBefore=14, spaceAfter=7)
    body = ParagraphStyle("GuideBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.5, leading=14, spaceAfter=6)
    small = ParagraphStyle("Small", parent=body, fontSize=8.5, leading=12)
    code_style = ParagraphStyle("Code", fontName="Courier", fontSize=7.5, leading=10, backColor=colors.HexColor("#F3F6F8"), borderColor=colors.HexColor("#D5DEE5"), borderWidth=0.5, borderPadding=7, spaceAfter=9)
    story = []

    story += [
        paragraph("O2N Engine API Guide", title),
        paragraph("Postman testing, endpoint payloads and responses, plus a frontend implementation prompt", subtitle),
        paragraph("Local Server", heading),
        paragraph("Start the backend before testing. The API base URL in this guide is <b>http://127.0.0.1:8081</b>.", body),
        code("cd E:\\hackthon\\OpenAi_Hackathone_Backend\\backend\npython -m uvicorn app.main:app --host 127.0.0.1 --port 8081 --reload", code_style),
        paragraph("Swagger documentation: http://127.0.0.1:8081/docs", body),
        paragraph("Important Path Rule", heading),
        paragraph("The project path is read by the backend machine. For this local setup, use a real absolute Windows path such as E:\\projects\\legacy-shop. A hosted browser application cannot access a visitor's disk path without a ZIP upload or desktop integration.", body),
        paragraph("Postman Collection", heading),
        paragraph("Import <b>O2N_Engine_API.postman_collection.json</b> in Postman: Import -> File -> select the collection. Then update collection variables: baseUrl, projectPath, and outputDirectory. outputDirectory must be a new path outside projectPath.", body),
        paragraph("Endpoint Summary", heading),
    ]
    endpoint_data = [
        ["Method", "Endpoint", "Purpose"],
        ["GET", "/", "Backend startup status"],
        ["GET", "/health", "Health check"],
        ["GET", "/api/v1/conversion-targets", "Target stack dropdown values"],
        ["POST", "/api/v1/projects/analyze", "Analyze a codebase and get roadmap"],
        ["POST", "/api/v1/projects/analyze/github", "Clone and analyze a public GitHub repository"],
        ["POST", "/api/v1/projects/convert", "Generate converted files into a new folder"],
    ]
    table = Table(endpoint_data, colWidths=[2 * cm, 7.1 * cm, 7.2 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 11),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C6CF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F8FA")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [table, Spacer(1, 8)]

    story += [
        paragraph("1. GET /", heading),
        paragraph("Use this optional endpoint to verify that the backend is running.", body),
        code("GET http://127.0.0.1:8081/\n\n200 OK\n{\n  \"message\": \"O2N Engine Backend Running\",\n  \"status\": \"success\",\n  \"docs\": \"/docs\",\n  \"health\": \"/health\"\n}", code_style),
        paragraph("2. GET /health", heading),
        paragraph("Use before enabling Analyze or Convert actions in the frontend.", body),
        code("GET http://127.0.0.1:8081/health\n\n200 OK\n{\n  \"status\": \"ok\"\n}", code_style),
        paragraph("3. GET /api/v1/conversion-targets", heading),
        paragraph("Use this response for a target technology dropdown. The frontend should additionally allow a custom target text value.", body),
        code("GET http://127.0.0.1:8081/api/v1/conversion-targets\n\n200 OK\n{\n  \"targets\": [\"Next.js + FastAPI\", \"React + Node.js/Express\", \"React + Django\", \"Vue + FastAPI\", \"Angular + Spring Boot\", \"Laravel\", \"Django\", \"FastAPI\", \"Node.js/Express\", \".NET Web API\", \"Java Spring Boot\"],\n  \"custom_target_supported\": true\n}", code_style),
        paragraph("4. POST /api/v1/projects/analyze/github", heading),
        paragraph("Use when the user chooses a public GitHub repository instead of a local folder. The backend accepts only HTTPS github.com owner/repository URLs, clones the repository to its managed workspace, then runs the normal analysis flow. Private repositories need GitHub OAuth/App support and are not supported yet.", body),
        code("{\n  \"name\": \"Public GitHub Repository\",\n  \"repository_url\": \"https://github.com/owner/repository\",\n  \"target_stack\": \"Next.js + FastAPI\"\n}\n\n200 OK response includes:\n{\n  \"source_type\": \"github_repository\",\n  \"repository_url\": \"https://github.com/owner/repository\",\n  \"path\": \"...\\\\repository_workspace\\\\repository_a1b2c3d4\"\n}\n\n400 invalid URL:\n{\n  \"detail\": \"Use a public HTTPS GitHub URL such as https://github.com/owner/repository.\"\n}", code_style),
        PageBreak(),
        paragraph("5. POST /api/v1/projects/analyze", heading),
        paragraph("Analyzes supported source files, counts languages, runs optional syntax and Semgrep scans, detects PHP/jQuery/Python 2 patterns, and returns a roadmap. The call is synchronous, so show a loading state.", body),
        paragraph("Payload", heading),
        code("{\n  \"name\": \"Legacy Shop\",\n  \"path\": \"E:\\\\projects\\\\legacy-shop\",\n  \"target_stack\": \"Next.js + FastAPI\"\n}", code_style),
        paragraph("Required fields: name (1-120 chars), path (existing absolute backend-readable directory). target_stack is optional and defaults to Next.js + FastAPI.", small),
        paragraph("Successful response: 200 OK", heading),
        code("{\n  \"id\": \"b92cae61-78bf-48c8-96b7-5f8b1e335baf\",\n  \"name\": \"Legacy Shop\",\n  \"path\": \"E:\\\\projects\\\\legacy-shop\",\n  \"status\": \"complete\",\n  \"created_at\": \"2026-07-20T12:30:00Z\",\n  \"languages\": {\"PHP\": 18, \"JavaScript\": 12},\n  \"findings\": [{\"severity\": \"medium\", \"category\": \"syntax\", \"message\": \"Tree-sitter found a syntax error\", \"file\": \"E:\\\\projects\\\\legacy-shop\\\\api\\\\example.py\"}],\n  \"recommendations\": [{\"current_technology\": \"PHP\", \"reason\": \"PHP source files were detected; modern API boundaries can simplify an incremental migration.\", \"recommended_targets\": [\"FastAPI\", \"Laravel\", \"Node.js/Express\"]}],\n  \"roadmap\": [{\"phase\": \"1. Baseline\", \"action\": \"Add tests and capture current behavior\", \"rationale\": \"Protect business logic before changing the migration surface.\"}],\n  \"summary\": \"Scanned 30 source files across 2 language(s).\"\n}", code_style),
        paragraph("Error response: 400 Bad Request", heading),
        code("{\n  \"detail\": \"The provided project path does not exist or is not a folder.\"\n}", code_style),
        PageBreak(),
        paragraph("6. POST /api/v1/projects/convert", heading),
        paragraph("Converts selected project-relative files or folders with Claude AI. ANTHROPIC_API_KEY is required. The source project is never overwritten; generated files are written only to a new output directory.", body),
        paragraph("Payload", heading),
        code("{\n  \"name\": \"Legacy Shop Migration\",\n  \"path\": \"E:\\\\projects\\\\legacy-shop\",\n  \"source_paths\": [\"api/users.php\", \"public/js/app.js\"],\n  \"target_stack\": \"Next.js + FastAPI\",\n  \"output_directory\": \"E:\\\\converted-projects\\\\legacy-shop-next-fastapi\"\n}", code_style),
        paragraph("source_paths must be relative to path. A directory is allowed, but no more than 20 supported source files may be expanded. output_directory is optional, must be outside path, and must not exist already.", small),
        paragraph("Successful response: 200 OK", heading),
        code("{\n  \"id\": \"9c1e977f-6f4f-4d6d-a943-9af1126c4eb4\",\n  \"name\": \"Legacy Shop Migration\",\n  \"project_path\": \"E:\\\\projects\\\\legacy-shop\",\n  \"target_stack\": \"Next.js + FastAPI\",\n  \"output_directory\": \"E:\\\\converted-projects\\\\legacy-shop-next-fastapi\",\n  \"generated_files\": [{\"path\": \"backend/app/routes/users.py\", \"content\": \"from fastapi import APIRouter...\"}],\n  \"findings\": [],\n  \"summary\": \"Generated 1 file(s) from 2 selected source file(s).\"\n}", code_style),
        paragraph("Common conversion errors", heading),
        code("{ \"detail\": \"ANTHROPIC_API_KEY is required to generate converted code.\" }\n{ \"detail\": \"Source path does not exist: api/missing.php\" }\n{ \"detail\": \"Source path escapes the project directory: ../private-file.py\" }\n{ \"detail\": \"Output directory already exists; choose a new empty location.\" }", code_style),
        paragraph("Frontend Integration Prompt", heading),
        paragraph("Copy the following prompt into your frontend coding assistant.", body),
        code("Build a responsive React or Next.js frontend for the O2N Engine API at http://127.0.0.1:8081. Do not show raw JSON.\n\nCreate these flows:\n1. On load, call GET /health and GET /api/v1/conversion-targets.\n2. Add a source selector: Local Folder or Public GitHub Repository.\n3. Local form: name, absolute project path, target stack dropdown, and custom target input. Submit POST /api/v1/projects/analyze.\n4. GitHub form: name, public HTTPS GitHub URL, and target stack. Submit POST /api/v1/projects/analyze/github.\n5. Report UI: language counts, findings grouped by severity, selectable legacy recommendations, roadmap steps, summary, and source type.\n6. Conversion form: returned project path, selected project-relative source paths, target stack, optional separate output directory. Submit POST /api/v1/projects/convert.\n7. Conversion result: output directory, generated-file sidebar, selected file code preview, findings, error state, and loading state.\n\nUse the response shapes from this guide. Show backend detail messages on non-2xx responses. Disable submit controls during requests. Treat project paths as local-backend paths. Use a clean developer-tool interface with responsive mobile layout.", code_style),
        paragraph("Configuration", heading),
        code("ANTHROPIC_API_KEY=your_key_here\nMONGODB_URI=mongodb://localhost:27017\nMONGODB_DATABASE=o2n_engine\nCORS_ORIGINS=http://localhost:3000,http://localhost:5173", code_style),
        paragraph("Without ANTHROPIC_API_KEY, analysis returns a fallback roadmap but code conversion returns 400. MongoDB and static-analysis tools are optional; unavailable services do not stop the core analysis response.", body),
    ]
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"Created {OUTPUT_PATH}")


if __name__ == "__main__":
    build_pdf()