from fpdf import FPDF


def create_pdf(text, output_path: str):
    pdf_file = FPDF()
    pdf_file.add_font(family="Charis", fname="Charis-Regular.ttf", style="")
    pdf_file.set_font(family="Charis", style="", size=12)
    pdf_file.add_page()
    pdf_file.multi_cell(0, 10, text)
    pdf_file.output(output_path)
    return pdf_file
