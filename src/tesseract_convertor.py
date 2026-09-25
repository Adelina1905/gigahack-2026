from pathlib import Path
from PIL import Image, UnidentifiedImageError

import pytesseract

def convertImagePyPath(imagePath):
  text = pytesseract.image_to_string(Image.open(imagePath))
  return text

# Folder Paths
folder_path_images    = Path(__file__).resolve().parent / "tesseract_Images_To_Convert"
folder_path_text_save = Path(__file__).resolve().parent / "teeseract_Converted_Text"
folder_path_text_save.mkdir(parents=True, exist_ok=True)


# Image saving Functions
def is_image(file_path):
  try:
    with Image.open(file_path) as image:
      image.verify()
    return True
  except (UnidentifiedImageError, OSError):
    return False
  
def convertFolderImages(folderPath):
  counter = 1
  
  for filePath in folderPath.iterdir():
    if filePath.is_file() and is_image(filePath):
      
      text = convertImagePyPath(filePath)
      name = f"converted_document{counter}"
      text_file = folder_path_text_save / f"{name}.txt"
      text_file.write_text(text, encoding="utf-8")
      
      counter += 1
      
teseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = teseract_path
convertFolderImages(folder_path_images)