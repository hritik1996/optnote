"""
Utility to generate a sample competitive exam PDF using PyMuPDF.
Creates 'competitive_exam_mcq_sample.pdf' with 20 questions across multiple topics.
"""
import pymupdf
from sample_data import SAMPLE_RAW_MCQ_TEXT

def create_sample_pdf(output_path="competitive_exam_mcq_sample.pdf"):
    doc = pymupdf.open()
    
    # We will format the sample text across pages
    lines = SAMPLE_RAW_MCQ_TEXT.strip().split("\n")
    
    page = doc.new_page(width=595, height=842) # A4
    y = 50
    margin_x = 50
    line_height = 14
    
    # Header
    page.insert_text((margin_x, y), "MOCK TEST SERIES: SSC CGL / UPSC / BANKING EXAM 2026", fontsize=12, fontname="helv", color=(0.1, 0.2, 0.6))
    y += 18
    page.insert_text((margin_x, y), "Subject: English Vocabulary, Static GK & General Science", fontsize=10, fontname="helv", color=(0.3, 0.3, 0.3))
    y += 16
    page.draw_line(pymupdf.Point(margin_x, y), pymupdf.Point(545, y), color=(0.7, 0.7, 0.7))
    y += 20
    
    for line in lines:
        if y > 780:
            page = doc.new_page(width=595, height=842)
            y = 50
        
        if line.startswith("Topic:"):
            y += 8
            page.insert_text((margin_x, y), line, fontsize=11, fontname="helv", color=(0.8, 0.2, 0.2))
            y += 16
        elif line.startswith("Answer:") or line.startswith("Ans:"):
            page.insert_text((margin_x, y), line, fontsize=9.5, fontname="helv", color=(0.1, 0.5, 0.2))
            y += line_height
        elif line.startswith("Explanation:"):
            page.insert_text((margin_x, y), line, fontsize=9, fontname="helv", color=(0.4, 0.4, 0.4))
            y += line_height + 6
        else:
            page.insert_text((margin_x, y), line, fontsize=10, fontname="helv", color=(0, 0, 0))
            y += line_height
            
    doc.save(output_path)
    doc.close()
    print(f"Sample PDF created successfully at: {output_path}")

if __name__ == "__main__":
    create_sample_pdf()
