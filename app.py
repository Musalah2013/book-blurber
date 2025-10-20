import os
import re
import io
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Tuple
import logging
import base64

import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
import PyPDF2
import docx
import ebooklib
from ebooklib import epub

# === Gemini: NEW unified SDK ===
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("samawy_blurb")

# ---------- Constants ----------
MODEL_PRICING = {
    # Update these if you want to estimate in-app costs for the 2.x family.
    # Public pages don't publish exact $/M token for all models; keep zeros or your own internal sheet.
    "gemini-2.0-flash": {"input_per_million": 0.0, "output_per_million": 0.0},
    "gemini-2.0-flash-lite": {"input_per_million": 0.0, "output_per_million": 0.0},
    "gemini-2.5-pro": {"input_per_million": 0.0, "output_per_million": 0.0},
    "unknown": {"input_per_million": 0.0, "output_per_million": 0.0},
}
SUPPORTED_MODELS = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-pro"]

BOOK_CATEGORIES = [
    "التقنية والكمبيوتر", "القواميس والموسوعات", "معلومات عامة", "العلوم الاجتماعية والسياسية",
    "التراجم والسير", "التاريخ والجغرافيا", "الإدارة والأعمال", "القصة والرواية", "القانون",
    "العلوم والرياضيات", "الهوايات والأشغال اليدوية", "تعليم اللغات", "هندسة العمارة والتصميم",
    "الطبخ", "المجلات", "السفر والخرائط", "الفلسفة والفكر", "المقررات والمناهج", "كتب الأطفال",
    "المرأة والأسرة", "الصحة العامة والتغذية والحمية", "الكتب المدرسية", "الكتب الطبية",
    "الأدب والشعر", "الطبيعة والزراعة وعلم الحيوان", "تطوير الذات", "العناية بالطفل",
    "التربية والتعليم", "كتب الهندسة", "الكتب الإسلامية والدينية"
]

EXTRACTED_SAMPLES_FOLDER_NAME = "extracted_text_samples"

# ---------- Helpers ----------
def get_client():
    # Key priority: secrets -> env
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        st.stop()  # Streamlit-native hard stop with a nice message in UI
    try:
        client = genai.Client(api_key=api_key)  # Gemini Developer API backend
        return client
    except Exception as e:
        st.error(f"Failed to init Gemini client: {e}")
        st.stop()

@st.cache_data(show_spinner=False)
def list_available_models():
    """Return a set of model IDs this key can access."""
    try:
        client = get_client()
        models = client.models.list()
        return {m.name for m in models}
    except Exception as e:
        log.warning(f"Could not list models: {e}")
        return set()

def resolve_model_id(preferred: str) -> str:
    """Return a working model id or a safe default from SUPPORTED_MODELS."""
    available = list_available_models()
    # The new SDK typically returns "models/<id>" in name; accept both.
    normalized = {m.split("/")[-1] for m in available}
    if preferred in normalized:
        return preferred
    for m in SUPPORTED_MODELS:
        if m in normalized:
            return m
    # Fall back to preferred anyway; backend will 404 -> we handle.
    return preferred

def _usage_counts(resp) -> Tuple[int, int]:
    # google-genai response.usage_metadata has input_tokens/output_tokens
    prompt_tokens = getattr(getattr(resp, "usage_metadata", None), "input_tokens", 0) or 0
    output_tokens = getattr(getattr(resp, "usage_metadata", None), "output_tokens", 0) or 0
    return prompt_tokens, output_tokens

def calculate_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    p = MODEL_PRICING.get(model_name, MODEL_PRICING["unknown"])
    return (prompt_tokens/1_000_000)*p["input_per_million"] + (completion_tokens/1_000_000)*p["output_per_million"]

# ---------- Extraction ----------
def extract_text_from_pdf(file_bytes: bytes) -> str:
    text = ""
    reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    for page in reader.pages:
        t = page.extract_text()
        if t:
            text += t + "\n"
    return text.strip()

def extract_text_from_docx(file_bytes: bytes) -> str:
    with io.BytesIO(file_bytes) as buff:
        doc = docx.Document(buff)
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    parts.append(cell.text)
        return "\n".join(parts).strip()

def extract_text_from_txt(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8", errors="ignore").strip()

def extract_text_from_epub(file_bytes: bytes) -> str:
    with io.BytesIO(file_bytes) as buff:
        book = epub.read_epub(buff)
        text = ""
        for it in book.get_items():
            if it.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(it.get_content(), "html.parser")
                text += soup.get_text(separator="\n") + "\n"
        return text.strip()

def extract_text_from_indd(file_bytes: bytes) -> str:
    # Very basic heuristic: scrape long printable runs
    text_matches = re.findall(rb'[\x20-\x7E\xA0-\xFF]{10,}', file_bytes)
    return ' '.join([m.decode('utf-8', errors='ignore') for m in text_matches]).strip()

def extract_text(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    if name.endswith(".pdf"):
        return extract_text_from_pdf(data)
    if name.endswith(".docx") or name.endswith(".doc"):
        return extract_text_from_docx(data)
    if name.endswith(".txt"):
        return extract_text_from_txt(data)
    if name.endswith(".epub"):
        return extract_text_from_epub(data)
    if name.endswith(".indd"):
        return extract_text_from_indd(data)
    raise ValueError(f"Unsupported format: {name}")

def clean_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s\.,!?;:\'"()\-\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def chunk_text(text: str, max_words: int = 1500, start_percentage: float = 0.4) -> Tuple[str, str]:
    words = text.split()
    n = len(words)
    if n <= max_words:
        return text, f"The complete available text ({n} words)."
    num_start = int(max_words * start_percentage)
    num_rem = max_words - num_start
    start_words = words[:num_start]
    remaining = words[num_start:]
    if num_rem <= 0 or not remaining:
        final_words = start_words
        descr = f"A sample consisting of the first {len(start_words)} words. Total sample: {len(final_words)} words."
    else:
        if len(remaining) <= num_rem:
            final_words = start_words + remaining
            descr = f"A sample including the first {len(start_words)} words and all remaining {len(remaining)} words. Total: {len(final_words)}."
        else:
            interval = max(1, len(remaining) // num_rem)
            sampled = [remaining[i] for i in range(0, len(remaining), interval)][:num_rem]
            final_words = start_words + sampled
            descr = f"A sample including the first {len(start_words)} words and {len(sampled)} words sampled from the rest. Total: {len(final_words)}."
    return ' '.join(final_words).strip(), descr

# ---------- Gemini calls ----------
def _gen_content(model: str, prompt: str):
    client = get_client()
    try:
        resp = client.models.generate_content(
            model=model,
            contents=[prompt],
            config=types.GenerateContentConfig(),
        )
        return resp
    except genai_errors.APIError as e:
        # If model 404s, try to auto-resolve to an available one once.
        if e.code == 404:
            fallback = resolve_model_id(model)
            if fallback != model:
                return client.models.generate_content(model=fallback, contents=[prompt], config=types.GenerateContentConfig())
        raise

def generate_blurb(model: str, text_chunk: str, chunk_description: str) -> Tuple[str, int, int, str]:
    prompt = f"""
بالاستناد إلى المقطع التالي المقتبس من كتاب، أَنتِج نبذة تعريفية قصيرة بالعربية (١٦٠–٥٠٠ حرف).

- نبرة أدبية قريبة من أسلوب النص.
- تعكس جوهر الموضوع أو النبرة الشعورية.
- عربية سليمة دون دعاية صريحة أو أوامر (مثل: "اقرأ").
- دون حشو أو تكرار. علامات تشكيل فقط عند الضرورة.
- فضّل الجمل الفعلية. لا تبدأ بشبه جملة.

معلومة عن المقطع: {chunk_description}

النص (حتى ٣٠٠٠ حرف):
{text_chunk[:3000]}

أخرج "النبذة" فقط.
"""
    resp = _gen_content(model, prompt)
    text = (getattr(resp, "text", None) or "").strip()
    pt, ct = _usage_counts(resp)
    used_model = resp.model_version.split("/")[-1] if getattr(resp, "model_version", "") else model
    if not text:
        text = "Error generating blurb."
    # Ensure minimum length padding (as you did)
    return text.ljust(160), pt, ct, used_model

def categorize_book(model: str, text_chunk: str, chunk_description: str) -> Tuple[str, int, int, str]:
    cats_str = ", ".join(BOOK_CATEGORIES)
    prompt = f"""
Based on the following Arabic book text, pick ONE category from this list:
{cats_str}

Info about the sample: "{chunk_description}"

Text (<=3000 chars):
{text_chunk[:3000]}

Return only the category name, nothing else.
"""
    resp = _gen_content(model, prompt)
    cat = (getattr(resp, "text", None) or "").strip()
    pt, ct = _usage_counts(resp)
    used_model = resp.model_version.split("/")[-1] if getattr(resp, "model_version", "") else model
    if cat not in BOOK_CATEGORIES:
        # fuzzy fallback
        match = next((c for c in BOOK_CATEGORIES if cat.lower() in c.lower() or c.lower() in cat.lower()), "القصة والرواية")
        cat = match
    return cat, pt, ct, used_model

# ---------- Streamlit UI ----------
st.set_page_config(page_title="Samawy Book Blurb Writer (Streamlit)", page_icon="📖", layout="wide")

st.title("📖 Samawy Book Blurb Writer — Streamlit Edition")
st.caption("AI-Powered Arabic blurbs & categorization (Gemini 2.x/2.5).")

with st.sidebar:
    st.header("🔑 AI Configuration")
    # Let user choose model (we map + auto-fallback)
    chosen_model = st.selectbox(
        "Model",
        options=SUPPORTED_MODELS,
        index=0,
        help="Use 2.x/2.5 models to avoid 404s."
    )
    st.markdown("**Tip:** Add your API key in *App → Settings → Secrets* as `GEMINI_API_KEY`.")
    # Inspect available models for the current key
    if st.button("List Available Models"):
        st.write(sorted(list_available_models()))

tab1, tab2 = st.tabs(["Single File", "Bulk (multi-upload)"])

with tab1:
    st.subheader("Single File Analysis")
    up = st.file_uploader("Upload one book file (.pdf, .docx/.doc, .txt, .epub, .indd)", type=["pdf","docx","doc","txt","epub","indd"])
    if up is not None:
        with st.spinner("Extracting text..."):
            try:
                raw = extract_text(up)
            except Exception as e:
                st.error(f"Extraction failed: {e}")
                st.stop()
        if not raw:
            st.warning("No text found in this file.")
            st.stop()
        clean = clean_text(raw)
        chunk, descr = chunk_text(clean, max_words=1500, start_percentage=0.4)

        c1, c2 = st.columns(2)
        with c1:
            st.write("**AI Input Description**")
            st.info(descr)
        with c2:
            st.write("**AI Input Word Count**")
            st.metric(label="Words sent to AI", value=len(chunk.split()))

        # Generate blurb & category
        if st.button("Generate Blurb & Category"):
            try:
                with st.spinner("Generating blurb..."):
                    blurb, p1, c1t, used_model1 = generate_blurb(chosen_model, chunk, descr)
                with st.spinner("Categorizing..."):
                    cat, p2, c2t, used_model2 = categorize_book(chosen_model, chunk, descr)
            except genai_errors.APIError as e:
                st.error(f"Gemini API error [{e.code}]: {e.message}")
                st.stop()
            except Exception as e:
                st.error(f"Error: {e}")
                st.stop()

            total_prompt = p1 + p2
            total_output = c1t + c2t
            cost = calculate_cost(chosen_model, total_prompt, total_output)

            st.write("### 📝 Blurb")
            st.text_area("Generated Blurb", value=blurb, height=200)
            st.caption(f"Characters: {len(blurb)}")

            st.write("### 📚 Category")
            st.success(cat)

            st.write("### 📈 Stats")
            st.code(
                f"""Model (blurb): {used_model1}
Model (category): {used_model2}
Total Cleaned Words: {len(clean.split()):,}
AI Input Words: {len(chunk.split()):,}
Blurb (Prompt/Output): {p1:,} / {c1t:,} tokens
Category (Prompt/Output): {p2:,} / {c2t:,} tokens
Total Tokens Used: {total_prompt + total_output:,}
Estimated Cost: ${cost:.6f} (placeholder)"""
            )

with tab2:
    st.subheader("Bulk Analysis (Upload many files)")
    save_samples = st.checkbox("Save the AI input text samples to a downloadable .zip")
    ups = st.file_uploader(
        "Upload multiple files", type=["pdf","docx","doc","txt","epub","indd"], accept_multiple_files=True
    )
    if ups:
        rows = []
        sample_files = []
        for f in ups:
            name = f.name
            try:
                raw = extract_text(f)
                if not raw:
                    rows.append({"File": name, "Status": "Error: No text", "Blurb": "", "Category": ""})
                    continue
                clean = clean_text(raw)
                chunk, descr = chunk_text(clean)
                blurb, p1, c1t, used_model1 = generate_blurb(chosen_model, chunk, descr)
                cat, p2, c2t, used_model2 = categorize_book(chosen_model, chunk, descr)
                rows.append({
                    "File": name,
                    "Status": "Success",
                    "Blurb": blurb,
                    "Category": cat,
                    "AI Input Words": len(chunk.split()),
                    "Blurb Prompt": p1, "Blurb Output": c1t,
                    "Cat Prompt": p2, "Cat Output": c2t,
                    "Model Blurb": used_model1, "Model Cat": used_model2
                })
                if save_samples:
                    sample_files.append((Path(name).stem + "_sample.txt", chunk))
            except Exception as e:
                rows.append({"File": name, "Status": f"Error: {e}", "Blurb": "", "Category": ""})

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)

        # Offer Excel download
        if not df.empty:
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine="openpyxl") as w:
                df.to_excel(w, index=False, sheet_name="Results")
            st.download_button("⬇️ Download Excel", data=out.getvalue(), file_name="samawy_blurb_results.xlsx")

        # Offer samples zip
        if save_samples and sample_files:
            import zipfile as _zip
            zbuf = io.BytesIO()
            with _zip.ZipFile(zbuf, "w", _zip.ZIP_DEFLATED) as zf:
                for fname, content in sample_files:
                    zf.writestr(fname, content)
            st.download_button("⬇️ Download Text Samples (.zip)", data=zbuf.getvalue(), file_name="ai_input_samples.zip")
