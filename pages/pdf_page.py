"""Module 7: PDF Tools — merge, split, extract images, convert, compress."""
from core.sounds import play_done, play_error
import os
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QListWidget, QAbstractItemView, QProgressBar, QTextEdit, QFrame,
    QTabWidget, QLineEdit, QMessageBox, QSpinBox
)

class DropList(QFrame):
    files_dropped = Signal(list)
    def __init__(self, label="Drop files here", parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(70)
        self.setStyleSheet("QFrame { border: 2px solid #e8542e; border-radius: 8px; background: #1e2235; }")
        from PySide6.QtWidgets import QVBoxLayout
        l = QVBoxLayout(self)
        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("border: none; color: #666666;")
        l.addWidget(lbl)
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
        self.setStyleSheet("QFrame { border: 2px solid #ff6b45; border-radius: 8px; background: #252a42; }")
    def dragLeaveEvent(self, e):
        self.setStyleSheet("QFrame { border: 2px solid #e8542e; border-radius: 8px; background: #1e2235; }")
    def dropEvent(self, e):
        self.setStyleSheet("QFrame { border: 2px solid #e8542e; border-radius: 8px; background: #1e2235; }")
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile()]
        if paths: self.files_dropped.emit(paths)

class PdfWorker(QThread):
    log_message = Signal(str)
    progress_value = Signal(int)
    finished = Signal(bool)
    def __init__(self, task, params, parent=None):
        super().__init__(parent)
        self.task = task
        self.params = params
    def run(self):
        try:
            getattr(self, f"_task_{self.task}")(**self.params)
        except Exception as e:
            import traceback
            self.log_message.emit(f"ERROR: {e}\n{traceback.format_exc()}")
            self.finished.emit(False)

    def _task_merge(self, input_files, output_path):
        from pypdf import PdfWriter, PdfReader
        w = PdfWriter()
        total = len(input_files)
        for i, path in enumerate(input_files, 1):
            for page in PdfReader(path).pages:
                w.add_page(page)
            self.log_message.emit(f"[{i}/{total}] Added: {os.path.basename(path)}")
            self.progress_value.emit(int(i/total*90))
        with open(output_path, "wb") as f: w.write(f)
        self.log_message.emit(f"✔ Merged PDF saved: {output_path}")
        self.progress_value.emit(100)
        self.finished.emit(True)

    def _task_split(self, input_file, output_dir, page_range):
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(input_file)
        total = len(reader.pages)
        base = os.path.splitext(os.path.basename(input_file))[0]
        os.makedirs(output_dir, exist_ok=True)
        pages = _parse_range(page_range, total) if page_range else list(range(1, total+1))
        for idx, p in enumerate(pages, 1):
            ww = PdfWriter()
            ww.add_page(reader.pages[p-1])
            out = os.path.join(output_dir, f"{base}_page{p:04d}.pdf")
            with open(out, "wb") as f: ww.write(f)
            self.log_message.emit(f"Page {p} → {os.path.basename(out)}")
            self.progress_value.emit(int(idx/len(pages)*100))
        self.log_message.emit(f"✔ Pages saved to: {output_dir}")
        self.finished.emit(True)

    def _task_extract_images(self, input_file, output_dir):
        import fitz
        os.makedirs(output_dir, exist_ok=True)
        doc = fitz.open(input_file)
        base = os.path.splitext(os.path.basename(input_file))[0]
        count = 0
        seen = set()
        for p_idx in range(len(doc)):
            page = doc[p_idx]
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                if xref in seen: continue
                seen.add(xref)
                try:
                    d = doc.extract_image(xref)
                    if d and d.get("image"):
                        ext = d.get("ext", "jpg")
                        name = f"{base}_p{p_idx+1:04d}_img{count+1:03d}.{ext}"
                        with open(os.path.join(output_dir, name), "wb") as f:
                            f.write(d["image"])
                        count += 1
                        self.log_message.emit(f"✔ {name}  ({d.get('width')}×{d.get('height')} px)")
                except Exception as e:
                    self.log_message.emit(f"  ⚠ xref={xref} skipped: {e}")
            self.progress_value.emit(int((p_idx+1)/len(doc)*80))
        if count == 0:
            self.log_message.emit("No embedded images found — rendering pages at 300 DPI...")
            mat = fitz.Matrix(300/72, 300/72)
            for i in range(len(doc)):
                pix = doc[i].get_pixmap(matrix=mat)
                name = f"{base}_p{i+1:04d}.jpg"
                pix.save(os.path.join(output_dir, name))
                count += 1
                self.log_message.emit(f"  Page {i+1} → {name}")
                self.progress_value.emit(int((i+1)/len(doc)*100))
        self.log_message.emit(f"✔ {count} image(s) extracted to: {output_dir}")
        self.finished.emit(True)

    def _task_pdf_to_word(self, input_file, output_path):
        from pdf2docx import Converter
        self.log_message.emit("Converting PDF → Word...")
        cv = Converter(input_file)
        cv.convert(output_path)
        cv.close()
        self.log_message.emit(f"✔ Word file saved: {output_path}")
        self.progress_value.emit(100)
        self.finished.emit(True)

    def _task_pdf_to_excel(self, input_file, output_path):
        import pdfplumber, openpyxl
        self.log_message.emit("Extracting tables PDF → Excel...")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Page 1"
        with pdfplumber.open(input_file) as pdf:
            total = len(pdf.pages)
            for i, page in enumerate(pdf.pages, 1):
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        for row in table: ws.append([c or "" for c in row])
                        ws.append([])
                else:
                    for line in (page.extract_text() or "").split("\n"):
                        ws.append([line])
                    ws.append([])
                self.log_message.emit(f"Page {i}/{total}")
                self.progress_value.emit(int(i/total*90))
        wb.save(output_path)
        self.log_message.emit(f"✔ Excel saved: {output_path}")
        self.progress_value.emit(100)
        self.finished.emit(True)

    def _task_pdf_to_jpeg(self, input_file, output_dir, dpi):
        import fitz
        os.makedirs(output_dir, exist_ok=True)
        doc = fitz.open(input_file)
        base = os.path.splitext(os.path.basename(input_file))[0]
        mat = fitz.Matrix(dpi/72, dpi/72)
        for i, page in enumerate(doc, 1):
            pix = page.get_pixmap(matrix=mat)
            out = os.path.join(output_dir, f"{base}_page{i:04d}.jpg")
            pix.save(out)
            self.log_message.emit(f"Page {i}/{len(doc)} → {os.path.basename(out)}")
            self.progress_value.emit(int(i/len(doc)*100))
        self.log_message.emit(f"✔ Images saved to: {output_dir}")
        self.finished.emit(True)

    def _task_compress(self, input_file, output_path):
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(input_file)
        writer = PdfWriter()
        total = len(reader.pages)
        for i, page in enumerate(reader.pages, 1):
            page.compress_content_streams()
            writer.add_page(page)
            self.progress_value.emit(int(i/total*80))
        writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
        with open(output_path, "wb") as f: writer.write(f)
        in_sz = os.path.getsize(input_file)
        out_sz = os.path.getsize(output_path)
        ratio = (1 - out_sz/in_sz)*100
        self.log_message.emit(f"✔ Compressed: {_sz(in_sz)} → {_sz(out_sz)} ({ratio:.1f}% reduction)")
        self.progress_value.emit(100)
        self.finished.emit(True)

    def _task_doc_to_pdf(self, input_file, output_path):
        try:
            from docx2pdf import convert
            self.log_message.emit("Converting Word → PDF (requires Microsoft Word)...")
            convert(input_file, output_path)
            self.log_message.emit(f"✔ PDF saved: {output_path}")
            self.progress_value.emit(100)
            self.finished.emit(True)
            return
        except Exception as e:
            self.log_message.emit(f"docx2pdf failed ({e}), falling back to text-only conversion...")
        from docx import Document as D
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        doc = D(input_file)
        rdoc = SimpleDocTemplate(output_path, pagesize=A4)
        styles = getSampleStyleSheet()
        elems = []
        for p in doc.paragraphs:
            if p.text.strip():
                elems.append(Paragraph(p.text, styles["Normal"]))
                elems.append(Spacer(1, 6))
        rdoc.build(elems)
        self.log_message.emit(f"✔ PDF saved (text only): {output_path}")
        self.progress_value.emit(100)
        self.finished.emit(True)


def _parse_range(text, total):
    pages = set()
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            pages.update(range(int(a), int(b)+1))
        elif part.isdigit():
            pages.add(int(part))
    return sorted(p for p in pages if 1 <= p <= total)

def _sz(n):
    for u in ("B","KB","MB","GB"):
        if n < 1024: return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


class PdfPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)

        top = QHBoxLayout()
        back = QPushButton("← Home")
        back.clicked.connect(self.back_requested.emit)
        top.addWidget(back)
        top.addStretch()
        layout.addLayout(top)

        title = QLabel("PDF Tools")
        title.setStyleSheet("font-size:18px;font-weight:bold;")
        layout.addWidget(title)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._tab_merge(),    "📎 Merge")
        self._tabs.addTab(self._tab_split(),    "✂ Split")
        self._tabs.addTab(self._tab_images(),   "🖼 Extract Images")
        self._tabs.addTab(self._tab_to_word(),  "📝 → Word")
        self._tabs.addTab(self._tab_to_excel(), "📊 → Excel")
        self._tabs.addTab(self._tab_to_jpeg(),  "🖼 → JPEG")
        self._tabs.addTab(self._tab_compress(), "🗜 Compress")
        self._tabs.addTab(self._tab_to_pdf(),   "📄 Doc → PDF")
        layout.addWidget(self._tabs)

        layout.addWidget(QLabel("Log:"))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFixedHeight(100)
        layout.addWidget(self.log_output)
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

    def _single_file_tab(self, drop_text, attr, ext):
        w = QWidget(); l = QVBoxLayout(w)
        drop = DropList(drop_text)
        lbl = QLabel("No file loaded."); lbl.setStyleSheet("color:#555;")
        drop.files_dropped.connect(lambda p: self._set_file(p[0], attr, lbl, ext))
        l.addWidget(drop); l.addWidget(lbl)
        btn = QPushButton("Browse...")
        btn.clicked.connect(lambda: self._browse_single(attr, lbl, ext))
        l.addWidget(btn)
        return w, l

    def _tab_merge(self):
        w = QWidget(); l = QVBoxLayout(w)
        drop = DropList("Drop multiple PDF files here")
        self._merge_list = QListWidget()
        self._merge_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._merge_files = []
        drop.files_dropped.connect(lambda p: self._add_files(p, self._merge_files, self._merge_list))
        l.addWidget(drop)
        row = QHBoxLayout()
        add = QPushButton("Add files..."); add.clicked.connect(lambda: self._browse_files(self._merge_files, self._merge_list))
        rm = QPushButton("Remove"); rm.clicked.connect(lambda: self._remove_sel(self._merge_files, self._merge_list))
        row.addWidget(add); row.addWidget(rm)
        l.addLayout(row); l.addWidget(self._merge_list)
        btn = QPushButton("Merge into one PDF"); btn.setMinimumHeight(34)
        btn.clicked.connect(self._run_merge); l.addWidget(btn)
        return w

    def _tab_split(self):
        w, l = self._single_file_tab("Drop a PDF here", "_split_file", ".pdf")
        self._split_file = ""
        row = QHBoxLayout(); row.addWidget(QLabel("Pages (e.g. 1-3,5  or empty = all):"))
        self._split_range = QLineEdit(); self._split_range.setPlaceholderText("Leave empty for all pages")
        row.addWidget(self._split_range); l.addLayout(row)
        btn = QPushButton("Split"); btn.setMinimumHeight(34); btn.clicked.connect(self._run_split); l.addWidget(btn)
        return w

    def _tab_images(self):
        self._extract_file = ""
        w, l = self._single_file_tab("Drop a PDF here", "_extract_file", ".pdf")
        btn = QPushButton("Extract Images"); btn.setMinimumHeight(34); btn.clicked.connect(self._run_extract); l.addWidget(btn)
        return w

    def _tab_to_word(self):
        self._toword_file = ""
        w, l = self._single_file_tab("Drop a PDF here", "_toword_file", ".pdf")
        QLabel("Requires: pip install pdf2docx", styleSheet="color:#888;font-size:11px;")
        btn = QPushButton("Convert to Word (.docx)"); btn.setMinimumHeight(34); btn.clicked.connect(self._run_to_word); l.addWidget(btn)
        return w

    def _tab_to_excel(self):
        self._toexcel_file = ""
        w, l = self._single_file_tab("Drop a PDF here", "_toexcel_file", ".pdf")
        btn = QPushButton("Convert to Excel (.xlsx)"); btn.setMinimumHeight(34); btn.clicked.connect(self._run_to_excel); l.addWidget(btn)
        return w

    def _tab_to_jpeg(self):
        self._tojpeg_file = ""
        w, l = self._single_file_tab("Drop a PDF here", "_tojpeg_file", ".pdf")
        row = QHBoxLayout(); row.addWidget(QLabel("Resolution (DPI):"))
        self._dpi = QSpinBox(); self._dpi.setRange(72, 600); self._dpi.setValue(150)
        row.addWidget(self._dpi); l.addLayout(row)
        btn = QPushButton("Convert to JPEG (one image per page)"); btn.setMinimumHeight(34); btn.clicked.connect(self._run_to_jpeg); l.addWidget(btn)
        return w

    def _tab_compress(self):
        self._compress_file = ""
        w, l = self._single_file_tab("Drop a PDF here", "_compress_file", ".pdf")
        QLabel("Compresses internal PDF streams (results vary).", styleSheet="color:#888;font-size:11px;")
        btn = QPushButton("Compress"); btn.setMinimumHeight(34); btn.clicked.connect(self._run_compress); l.addWidget(btn)
        return w

    def _tab_to_pdf(self):
        self._doctopdf_file = ""
        w, l = self._single_file_tab("Drop a Word (.docx) file here", "_doctopdf_file", ".docx")
        note = QLabel("For faithful conversion (layout preserved):\npip install docx2pdf  +  Microsoft Word installed.\nOtherwise: plain text conversion via python-docx.")
        note.setStyleSheet("color:#888;font-size:11px;"); l.addWidget(note)
        btn = QPushButton("Convert to PDF"); btn.setMinimumHeight(34); btn.clicked.connect(self._run_to_pdf); l.addWidget(btn)
        return w

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _add_files(self, paths, lst, widget):
        for p in paths:
            if p not in lst:
                lst.append(p); widget.addItem(os.path.basename(p))

    def _browse_files(self, lst, widget):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select PDF files", filter="PDF (*.pdf)")
        if paths: self._add_files(paths, lst, widget)

    def _remove_sel(self, lst, widget):
        for item in widget.selectedItems():
            row = widget.row(item); widget.takeItem(row); del lst[row]

    def _set_file(self, path, attr, lbl, ext):
        if os.path.splitext(path)[1].lower() == ext:
            setattr(self, attr, path); lbl.setText(os.path.basename(path))

    def _browse_single(self, attr, lbl, ext):
        path, _ = QFileDialog.getOpenFileName(self, "Select file", filter=f"Files (*{ext})")
        if path: self._set_file(path, attr, lbl, ext)

    def _out_dir(self, src):
        return QFileDialog.getExistingDirectory(self, "Output folder", os.path.dirname(src))

    def _run_worker(self, task, params):
        self.log_output.clear(); self.progress_bar.setValue(0)
        self.worker = PdfWorker(task, params)
        self.worker.log_message.connect(self.log_output.append)
        self.worker.progress_value.connect(self.progress_bar.setValue)
        self.worker.finished.connect(lambda ok: (play_done() if ok else play_error(),
            QMessageBox.information(self, "Done", "Operation successful!") if ok
            else QMessageBox.warning(self, "Error", "See the log for details.")))
        self.worker.start()

    def _run_merge(self):
        if len(self._merge_files) < 2:
            QMessageBox.warning(self, "Not enough files", "Add at least 2 PDF files."); return
        path, _ = QFileDialog.getSaveFileName(self, "Save merged PDF", "merged.pdf", "PDF (*.pdf)")
        if path: self._run_worker("merge", {"input_files": list(self._merge_files), "output_path": path})

    def _run_split(self):
        if not self._split_file: QMessageBox.warning(self, "No file", "Select a PDF first."); return
        d = self._out_dir(self._split_file)
        if d: self._run_worker("split", {"input_file": self._split_file, "output_dir": d, "page_range": self._split_range.text().strip()})

    def _run_extract(self):
        if not self._extract_file: QMessageBox.warning(self, "No file", "Select a PDF first."); return
        d = self._out_dir(self._extract_file)
        if d: self._run_worker("extract_images", {"input_file": self._extract_file, "output_dir": d})

    def _run_to_word(self):
        if not self._toword_file: QMessageBox.warning(self, "No file", "Select a PDF first."); return
        base = os.path.splitext(self._toword_file)[0]
        path, _ = QFileDialog.getSaveFileName(self, "Save Word file", base+".docx", "Word (*.docx)")
        if path: self._run_worker("pdf_to_word", {"input_file": self._toword_file, "output_path": path})

    def _run_to_excel(self):
        if not self._toexcel_file: QMessageBox.warning(self, "No file", "Select a PDF first."); return
        base = os.path.splitext(self._toexcel_file)[0]
        path, _ = QFileDialog.getSaveFileName(self, "Save Excel file", base+".xlsx", "Excel (*.xlsx)")
        if path: self._run_worker("pdf_to_excel", {"input_file": self._toexcel_file, "output_path": path})

    def _run_to_jpeg(self):
        if not self._tojpeg_file: QMessageBox.warning(self, "No file", "Select a PDF first."); return
        d = self._out_dir(self._tojpeg_file)
        if d: self._run_worker("pdf_to_jpeg", {"input_file": self._tojpeg_file, "output_dir": d, "dpi": self._dpi.value()})

    def _run_compress(self):
        if not self._compress_file: QMessageBox.warning(self, "No file", "Select a PDF first."); return
        base = os.path.splitext(self._compress_file)[0]
        path, _ = QFileDialog.getSaveFileName(self, "Save compressed PDF", base+"_compressed.pdf", "PDF (*.pdf)")
        if path: self._run_worker("compress", {"input_file": self._compress_file, "output_path": path})

    def _run_to_pdf(self):
        if not self._doctopdf_file: QMessageBox.warning(self, "No file", "Select a .docx file first."); return
        base = os.path.splitext(self._doctopdf_file)[0]
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", base+".pdf", "PDF (*.pdf)")
        if path: self._run_worker("doc_to_pdf", {"input_file": self._doctopdf_file, "output_path": path})

    def set_lang(self, lang): pass
