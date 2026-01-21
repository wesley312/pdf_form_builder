import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk
from typing import List, Tuple

import fitz  # PyMuPDF


@dataclass
class FormField:
    """Represents a form field with its properties"""

    field_type: str  # text, multiline, checkbox, comb, radio, textarea
    rect: Tuple[float, float, float, float]  # x0, y0, x1, y1
    name: str
    page_num: int
    max_chars: int = 0  # For comb fields
    options: List[str] = None  # For radio buttons


class PDFFormBuilder:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Form Builder")
        self.root.geometry("1200x800")

        self.pdf_doc = None
        self.current_page = 0
        self.fields = []
        self.current_field_type = "text"
        self.selection_start = None
        self.temp_rect = None

        self.setup_ui()

    def setup_ui(self):
        # Top toolbar
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        ttk.Button(toolbar, text="Open PDF", command=self.open_pdf).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(toolbar, text="Save Form PDF", command=self.save_form_pdf).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(
            toolbar, text="Recognize Fields", command=self.recognize_fields
        ).pack(side=tk.LEFT, padx=2)

        # Page navigation
        ttk.Label(toolbar, text="Page:").pack(side=tk.LEFT, padx=(20, 2))
        self.page_var = tk.StringVar(value="1")
        self.page_entry = ttk.Entry(toolbar, textvariable=self.page_var, width=5)
        self.page_entry.pack(side=tk.LEFT, padx=2)
        self.page_label = ttk.Label(toolbar, text="/ 1")
        self.page_label.pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Go", command=self.go_to_page).pack(
            side=tk.LEFT, padx=2
        )

        # Main container
        main_container = ttk.Frame(self.root)
        main_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left panel - Field types
        left_panel = ttk.LabelFrame(main_container, text="Field Types", width=200)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        left_panel.pack_propagate(False)

        field_types = [
            ("Single Line Text", "text"),
            ("Multiline Text", "multiline"),
            ("Checkbox", "checkbox"),
            ("Comb Field", "comb"),
            ("Radio Button", "radio"),
            ("Text Area Box", "textarea"),
        ]

        self.field_type_var = tk.StringVar(value="text")
        for label, value in field_types:
            ttk.Radiobutton(
                left_panel,
                text=label,
                variable=self.field_type_var,
                value=value,
                command=self.on_field_type_change,
            ).pack(anchor=tk.W, padx=10, pady=5)

        # Comb field options
        ttk.Label(left_panel, text="Comb Chars:").pack(
            anchor=tk.W, padx=10, pady=(20, 2)
        )
        self.comb_chars_var = tk.StringVar(value="10")
        ttk.Entry(left_panel, textvariable=self.comb_chars_var, width=10).pack(
            anchor=tk.W, padx=10
        )

        ttk.Label(left_panel, text="\nInstructions:", font=("Arial", 9, "bold")).pack(
            anchor=tk.W, padx=10, pady=(20, 5)
        )
        instructions = tk.Text(
            left_panel, wrap=tk.WORD, height=10, width=25, font=("Arial", 8)
        )
        instructions.pack(padx=10, pady=5)
        instructions.insert(
            "1.0",
            "1. Open a PDF file\n2. Select field type\n3. Click and drag on PDF to create field\n4. Fields will be added at mouse release\n5. Save to create fillable PDF",
        )
        instructions.config(state=tk.DISABLED)

        # Center panel - PDF Canvas
        center_panel = ttk.Frame(main_container)
        center_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Canvas with scrollbars
        canvas_frame = ttk.Frame(center_panel)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg="gray", cursor="cross")
        v_scroll = ttk.Scrollbar(
            canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview
        )
        h_scroll = ttk.Scrollbar(
            canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview
        )

        self.canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Canvas bindings
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)

        # Right panel - Fields list
        right_panel = ttk.LabelFrame(main_container, text="Form Fields", width=250)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        right_panel.pack_propagate(False)

        # Fields listbox
        list_frame = ttk.Frame(right_panel)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.fields_listbox = tk.Listbox(list_frame)
        list_scroll = ttk.Scrollbar(
            list_frame, orient=tk.VERTICAL, command=self.fields_listbox.yview
        )
        self.fields_listbox.configure(yscrollcommand=list_scroll.set)

        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.fields_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Field operations
        ttk.Button(right_panel, text="Delete Selected", command=self.delete_field).pack(
            fill=tk.X, padx=5, pady=2
        )
        ttk.Button(right_panel, text="Clear All", command=self.clear_all_fields).pack(
            fill=tk.X, padx=5, pady=2
        )

    def on_field_type_change(self):
        self.current_field_type = self.field_type_var.get()

    def open_pdf(self):
        filename = filedialog.askopenfilename(
            title="Select PDF", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if filename:
            try:
                self.pdf_doc = fitz.open(filename)
                self.current_page = 0
                self.fields = []
                self.page_label.config(text=f"/ {len(self.pdf_doc)}")
                self.render_page()
                self.update_fields_list()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open PDF: {str(e)}")

    def render_page(self):
        if not self.pdf_doc:
            return

        page = self.pdf_doc[self.current_page]

        # Render at 150 DPI for better quality
        mat = fitz.Matrix(150 / 72, 150 / 72)
        pix = page.get_pixmap(matrix=mat)

        # Convert to PhotoImage
        img_data = pix.tobytes("ppm")
        self.photo = tk.PhotoImage(data=img_data)

        # Update canvas
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))

        # Draw existing fields for this page
        self.draw_fields()

    def draw_fields(self):
        """Draw rectangles for existing fields on current page"""
        if not self.pdf_doc:
            return

        page = self.pdf_doc[self.current_page]
        mat = fitz.Matrix(150 / 72, 150 / 72)

        for i, field in enumerate(self.fields):
            if field.page_num == self.current_page:
                # Convert PDF coordinates to canvas coordinates
                rect = field.rect
                x0, y0, x1, y1 = rect

                # Transform coordinates
                x0_c = x0 * mat.a
                y0_c = y0 * mat.d
                x1_c = x1 * mat.a
                y1_c = y1 * mat.d

                # Choose color based on field type
                colors = {
                    "text": "blue",
                    "multiline": "green",
                    "checkbox": "red",
                    "comb": "purple",
                    "radio": "orange",
                    "textarea": "cyan",
                }
                color = colors.get(field.field_type, "blue")

                self.canvas.create_rectangle(
                    x0_c, y0_c, x1_c, y1_c, outline=color, width=2, tags=f"field_{i}"
                )

    def on_mouse_press(self, event):
        if not self.pdf_doc:
            return
        self.selection_start = (
            self.canvas.canvasx(event.x),
            self.canvas.canvasy(event.y),
        )

    def on_mouse_drag(self, event):
        if not self.pdf_doc or not self.selection_start:
            return

        # Remove previous temp rectangle
        self.canvas.delete("temp_rect")

        # Draw current selection
        x0, y0 = self.selection_start
        x1 = self.canvas.canvasx(event.x)
        y1 = self.canvas.canvasy(event.y)

        self.canvas.create_rectangle(
            x0, y0, x1, y1, outline="yellow", width=2, dash=(5, 5), tags="temp_rect"
        )

    def on_mouse_release(self, event):
        if not self.pdf_doc or not self.selection_start:
            return

        self.canvas.delete("temp_rect")

        x0, y0 = self.selection_start
        x1 = self.canvas.canvasx(event.x)
        y1 = self.canvas.canvasy(event.y)

        # Ensure x0 < x1 and y0 < y1
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0

        # Convert canvas coordinates to PDF coordinates
        mat = fitz.Matrix(150 / 72, 150 / 72)
        pdf_x0 = x0 / mat.a
        pdf_y0 = y0 / mat.d
        pdf_x1 = x1 / mat.a
        pdf_y1 = y1 / mat.d

        # Create field
        field_name = f"{self.current_field_type}_{len(self.fields) + 1}"

        field = FormField(
            field_type=self.current_field_type,
            rect=(pdf_x0, pdf_y0, pdf_x1, pdf_y1),
            name=field_name,
            page_num=self.current_page,
            max_chars=int(self.comb_chars_var.get())
            if self.current_field_type == "comb"
            else 0,
        )

        self.fields.append(field)
        self.selection_start = None

        # Redraw
        self.render_page()
        self.update_fields_list()

    def update_fields_list(self):
        self.fields_listbox.delete(0, tk.END)
        for i, field in enumerate(self.fields):
            self.fields_listbox.insert(
                tk.END, f"[P{field.page_num + 1}] {field.field_type}: {field.name}"
            )

    def delete_field(self):
        selection = self.fields_listbox.curselection()
        if selection:
            idx = selection[0]
            del self.fields[idx]
            self.update_fields_list()
            self.render_page()

    def clear_all_fields(self):
        if messagebox.askyesno("Confirm", "Delete all fields?"):
            self.fields = []
            self.update_fields_list()
            self.render_page()

    def go_to_page(self):
        try:
            page_num = int(self.page_var.get()) - 1
            if 0 <= page_num < len(self.pdf_doc):
                self.current_page = page_num
                self.render_page()
            else:
                messagebox.showwarning(
                    "Invalid Page", f"Page must be between 1 and {len(self.pdf_doc)}"
                )
        except ValueError:
            messagebox.showwarning("Invalid Input", "Please enter a valid page number")

    def recognize_fields(self):
        """Automatically recognize potential form fields in the PDF"""
        if not self.pdf_doc:
            messagebox.showwarning("No PDF", "Please open a PDF first")
            return

        messagebox.showinfo(
            "Auto-Recognition",
            "This feature would use OCR/pattern recognition to detect form fields.\n\n"
            + "For now, please manually create fields by selecting type and drawing rectangles.",
        )

    def save_form_pdf(self):
        if not self.pdf_doc or not self.fields:
            messagebox.showwarning("No Data", "Please open a PDF and add fields first")
            return

        filename = filedialog.asksaveasfilename(
            title="Save Form PDF",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )

        if filename:
            try:
                # Create a new PDF with form fields
                output_doc = fitz.open(self.pdf_doc.name)

                for field in self.fields:
                    page = output_doc[field.page_num]

                    # Create widget based on field type
                    widget = fitz.Widget()
                    widget.field_name = field.name
                    widget.rect = fitz.Rect(field.rect)
                    widget.border_width = 1
                    widget.border_color = (0, 0, 0)
                    widget.fill_color = (1, 1, 1)

                    if field.field_type == "text":
                        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                        widget.text_maxlen = 0

                    elif field.field_type == "multiline":
                        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                        widget.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE
                        widget.text_maxlen = 0

                    elif field.field_type == "textarea":
                        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                        widget.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE
                        widget.text_maxlen = 0

                    elif field.field_type == "checkbox":
                        widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
                        widget.field_value = "Off"

                    elif field.field_type == "comb":
                        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                        widget.field_flags = fitz.PDF_TX_FIELD_IS_COMB
                        widget.text_maxlen = field.max_chars

                    elif field.field_type == "radio":
                        widget.field_type = fitz.PDF_WIDGET_TYPE_RADIOBUTTON
                        widget.field_value = "Off"

                    # Add widget to page
                    annot = page.add_widget(widget)

                # Save the output PDF
                output_doc.save(filename)
                output_doc.close()

                messagebox.showinfo(
                    "Success",
                    f"Form PDF saved successfully!\n\n{len(self.fields)} fields created.",
                )

            except Exception as e:
                messagebox.showerror("Error", f"Failed to save PDF: {str(e)}")


def main():
    root = tk.Tk()
    app = PDFFormBuilder(root)
    root.mainloop()


if __name__ == "__main__":
    main()
