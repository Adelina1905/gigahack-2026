import io
import fitz  # PyMuPDF pentru fisiere PDF
from PIL import Image
import pytesseract
import ollama
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Permitem accesul Front-end-ului (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite orice conexiune locala
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Baza de date in memorie pentru textul extras din fisiere
knowledge_base = []

# --- 1. FUNCTII DE CITIRE A FISIERELOR ---

def read_pdf(file_bytes: bytes) -> str:
    """Extrage textul din fisiere PDF."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text

def read_image(file_bytes: bytes) -> str:
    """Extrage textul din imagini (JPG/PNG) folosind OCR."""
    image = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(image)

# --- 2. ENDPOINT-URI BACKEND (API) ---

class QueryModel(BaseModel):
    question: str

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Incarca un fisier (PDF sau Imagine) si ii extrage textul."""
    contents = await file.read()
    extracted_text = ""

    if file.filename.endswith(".pdf"):
        extracted_text = read_pdf(contents)
    elif file.filename.lower().endswith((".jpg", ".jpeg", ".png")):
        extracted_text = read_image(contents)
    else:
        return {"error": "Format necomportat! Incarca doar PDF, JPG sau PNG."}

    # Adaugam textul extras in baza noastra de date
    knowledge_base.append(extracted_text)
    return {"message": f"Fisierul '{file.filename}' a fost citit si adaugat in baza de date cu succes!"}

@app.post("/ask")
async def ask_question(data: QueryModel):
    """Primeste o intrebare, cauta in baza de date si raspunde prin Ollama."""
    context = "\n".join(knowledge_base)
    
    if not context:
        context = "Nu exista informatii adaugate in baza de date."

    prompt = (
        f"Foloseste URMATORUL CONTEXT pentru a raspunde la intrebare.\n"
        f"Context:\n{context}\n\n"
        f"Intrebare: {data.question}\n"
        f"Raspuns:"
    )

    response = ollama.chat(
        model="llama3.2",
        messages=[{"role": "user", "content": prompt}]
    )

    return {"answer": response["message"]["content"]}