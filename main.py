import re
import io
import pdfplumber
import pandas as pd
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# ✅ Allow frontend (browser) to talk to backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Demo safe
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Extract text from uploaded PDF (MEMORY SAFE)
# -----------------------------
def extract_text_from_pdf(file_bytes):
    text = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        # 🔥 LIMIT to first 40 pages (prevents memory crash on Render free tier)
        for page in pdf.pages[:40]:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


# -----------------------------
# Detect financial statement lines
# -----------------------------
def get_income_statement_lines(text):
    lines = text.split("\n")
    extracted = []

    financial_terms = [
        "revenue", "sales", "cost", "gross",
        "operating income", "operating expenses",
        "net income", "earnings per share", "eps"
    ]

    for line in lines:
        clean = line.strip()
        lower = clean.lower()

        # Must contain numbers AND financial keywords
        if re.search(r"\d", clean) and any(term in lower for term in financial_terms):
            extracted.append(clean)

    return extracted


# -----------------------------
# Extract numbers safely
# -----------------------------
def extract_numbers(line):
    numbers = re.findall(r"\(?-?\d[\d,\.]*\)?", line)
    clean_numbers = []

    for num in numbers:
        num = num.replace(",", "")
        if "(" in num and ")" in num:
            num = "-" + num.replace("(", "").replace(")", "")
        clean_numbers.append(num)

    return clean_numbers


# -----------------------------
# Normalize financial labels
# -----------------------------
def normalize_label(line):
    lower = line.lower()

    if "total net sales" in lower or "net sales" in lower:
        return "Revenue"
    elif "cost of sales" in lower:
        return "Cost of Revenue"
    elif "gross margin" in lower or "gross profit" in lower:
        return "Gross Profit"
    elif "operating income" in lower:
        return "Operating Income"
    elif "operating expenses" in lower:
        return "Operating Expenses"
    elif "net income" in lower or "net profit" in lower or "net earnings" in lower:
        return "Net Income"
    elif "earnings per share" in lower or "eps" in lower:
        return "EPS"
    else:
        return "UNKNOWN"


# -----------------------------
# API Endpoint
# -----------------------------
@app.post("/extract-financials/")
async def extract_financials(file: UploadFile = File(...)):
    contents = await file.read()

    # Extract text (memory optimized)
    text = extract_text_from_pdf(contents)

    # Detect financial lines
    lines = get_income_statement_lines(text)

    data = []

    for line in lines:
        label = normalize_label(line)
        numbers = extract_numbers(line)

        # Only keep meaningful financial lines
        if label != "UNKNOWN" and numbers:
            row = {
                "Raw Line": line,
                "Standard Label": label,
                "Values Found": ", ".join(numbers)
            }
            data.append(row)

    # Convert to CSV
    df = pd.DataFrame(data)

    # Fallback if nothing found
    if df.empty:
        df = pd.DataFrame([{
            "Raw Line": "No income statement data detected in first 40 pages.",
            "Standard Label": "INFO",
            "Values Found": ""
        }])

    stream = io.StringIO()
    df.to_csv(stream, index=False)
    stream.seek(0)

    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=financial_extraction.csv"}
    )
