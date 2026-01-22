import json
import os
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
    # Appearance properties
    border_color: Tuple[float, float, float] = (0, 0, 0)  # RGB 0-1
    fill_color: Tuple[float, float, float] = (1, 1, 1)  # RGB 0-1
    border_width: float = 1.0
    font_size: float = 12.0
    font_color: Tuple[float, float, float] = (0, 0, 0)  # RGB 0-1


class PDFFormBuilder:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Form Builder")
        self.root.geometry("1400x800")

        self.pdf_doc = None
        self.current_page = 0
        self.fields = []
        self.current_field_type = "text"
        self.selection_start = None
        self.temp_rect = None
        self.selected_field_idx = None

        # Default style settings - will be loaded from config
        self.config_file = os.path.join(
            os.path.expanduser("~"), ".pdf_form_builder_config.json"
        )
        self.load_default_styles()

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
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )
        ttk.Button(
            toolbar, text="Default Style Settings", command=self.open_style_settings
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
            "1. Open a PDF file\n2. Select field type\n3. Click and drag on PDF to create field\n4. Select field from list to customize\n5. Save to create fillable PDF",
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

        # Right panel - Fields list and properties
        right_panel = ttk.Frame(main_container, width=350)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        right_panel.pack_propagate(False)

        # Fields list
        fields_frame = ttk.LabelFrame(right_panel, text="Form Fields")
        fields_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        list_frame = ttk.Frame(fields_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.fields_listbox = tk.Listbox(list_frame, height=8)
        list_scroll = ttk.Scrollbar(
            list_frame, orient=tk.VERTICAL, command=self.fields_listbox.yview
        )
        self.fields_listbox.configure(yscrollcommand=list_scroll.set)
        self.fields_listbox.bind("<<ListboxSelect>>", self.on_field_select)

        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.fields_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Field operations
        btn_frame = ttk.Frame(fields_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="Delete Selected", command=self.delete_field).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(btn_frame, text="Clear All", command=self.clear_all_fields).pack(
            side=tk.LEFT, padx=2
        )

        # Properties panel
        props_frame = ttk.LabelFrame(right_panel, text="Field Properties")
        props_frame.pack(fill=tk.BOTH, padx=5, pady=5)

        # Create scrollable frame for properties
        props_canvas = tk.Canvas(props_frame, height=300)
        props_scrollbar = ttk.Scrollbar(
            props_frame, orient=tk.VERTICAL, command=props_canvas.yview
        )
        scrollable_frame = ttk.Frame(props_canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: props_canvas.configure(scrollregion=props_canvas.bbox("all")),
        )

        props_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        props_canvas.configure(yscrollcommand=props_scrollbar.set)

        props_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        props_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Field Name
        ttk.Label(scrollable_frame, text="Field Name:", font=("Arial", 9, "bold")).grid(
            row=0, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.field_name_var = tk.StringVar()
        name_entry = ttk.Entry(
            scrollable_frame, textvariable=self.field_name_var, width=20
        )
        name_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Button(
            scrollable_frame, text="Update", command=self.update_field_name
        ).grid(row=0, column=2, padx=5)

        # Border Width
        ttk.Label(
            scrollable_frame, text="Border Width:", font=("Arial", 9, "bold")
        ).grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.border_width_var = tk.StringVar(value="1.0")
        ttk.Spinbox(
            scrollable_frame,
            from_=0,
            to=10,
            increment=0.5,
            textvariable=self.border_width_var,
            width=10,
            command=self.update_field_appearance,
        ).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)

        # Font Size
        ttk.Label(scrollable_frame, text="Font Size:", font=("Arial", 9, "bold")).grid(
            row=2, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.font_size_var = tk.StringVar(value="12")
        ttk.Spinbox(
            scrollable_frame,
            from_=6,
            to=72,
            increment=1,
            textvariable=self.font_size_var,
            width=10,
            command=self.update_field_appearance,
        ).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)

        # Border Color
        ttk.Label(
            scrollable_frame, text="Border Color:", font=("Arial", 9, "bold")
        ).grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.border_color_btn = tk.Button(
            scrollable_frame,
            text="Choose",
            command=lambda: self.choose_color("border"),
            width=10,
            bg="black",
        )
        self.border_color_btn.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)

        # Fill Color
        ttk.Label(scrollable_frame, text="Fill Color:", font=("Arial", 9, "bold")).grid(
            row=4, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.fill_color_btn = tk.Button(
            scrollable_frame,
            text="Choose",
            command=lambda: self.choose_color("fill"),
            width=10,
            bg="white",
        )
        self.fill_color_btn.grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)

        # Font Color
        ttk.Label(scrollable_frame, text="Font Color:", font=("Arial", 9, "bold")).grid(
            row=5, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.font_color_btn = tk.Button(
            scrollable_frame,
            text="Choose",
            command=lambda: self.choose_color("font"),
            width=10,
            bg="black",
        )
        self.font_color_btn.grid(row=5, column=1, sticky=tk.W, padx=5, pady=5)

        # Apply button
        ttk.Button(
            scrollable_frame, text="Apply Changes", command=self.update_field_appearance
        ).grid(row=6, column=0, columnspan=3, pady=10, padx=5, sticky=tk.EW)

        # Info label
        self.info_label = ttk.Label(
            scrollable_frame,
            text="Select a field to customize",
            foreground="gray",
            wraplength=300,
        )
        self.info_label.grid(row=7, column=0, columnspan=3, pady=10, padx=5)

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
                self.selected_field_idx = None
                self.page_label.config(text=f"/ {len(self.pdf_doc)}")

                # Automatically detect existing fields
                self.detect_existing_fields()

                # Render page (will be called again in detect_existing_fields, but that's okay)
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

                # Highlight selected field
                width = 3 if i == self.selected_field_idx else 2

                self.canvas.create_rectangle(
                    x0_c,
                    y0_c,
                    x1_c,
                    y1_c,
                    outline=color,
                    width=width,
                    tags=f"field_{i}",
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
            border_color=self.default_border_color,
            fill_color=self.default_fill_color,
            font_color=self.default_font_color,
            border_width=self.default_border_width,
            font_size=self.default_font_size,
        )

        self.fields.append(field)
        self.selection_start = None

        # Redraw
        self.render_page()
        self.update_fields_list()

    def on_field_select(self, event):
        """Handle field selection from listbox"""
        selection = self.fields_listbox.curselection()
        if selection:
            self.selected_field_idx = selection[0]
            field = self.fields[self.selected_field_idx]

            # Update property controls
            self.field_name_var.set(field.name)
            self.border_width_var.set(str(field.border_width))
            self.font_size_var.set(str(field.font_size))

            # Update color buttons
            self.border_color_btn.config(bg=self.rgb_to_hex(field.border_color))
            self.fill_color_btn.config(bg=self.rgb_to_hex(field.fill_color))
            self.font_color_btn.config(bg=self.rgb_to_hex(field.font_color))

            self.info_label.config(text=f"Editing: {field.name} ({field.field_type})")

            # Redraw to highlight selected field
            self.render_page()

    def update_field_name(self):
        """Update the name of the selected field"""
        if self.selected_field_idx is not None:
            new_name = self.field_name_var.get().strip()
            if new_name:
                self.fields[self.selected_field_idx].name = new_name
                self.update_fields_list()
                self.info_label.config(text=f"Field name updated to: {new_name}")
            else:
                messagebox.showwarning("Invalid Name", "Field name cannot be empty")

    def update_field_appearance(self):
        """Update the appearance properties of the selected field"""
        if self.selected_field_idx is not None:
            field = self.fields[self.selected_field_idx]

            try:
                field.border_width = float(self.border_width_var.get())
                field.font_size = float(self.font_size_var.get())

                self.info_label.config(text=f"Appearance updated for: {field.name}")
            except ValueError:
                messagebox.showwarning(
                    "Invalid Value", "Please enter valid numeric values"
                )

    def choose_color(self, color_type):
        """Open color chooser dialog"""
        if self.selected_field_idx is None:
            messagebox.showinfo("No Selection", "Please select a field first")
            return

        from tkinter import colorchooser

        field = self.fields[self.selected_field_idx]

        # Get current color
        if color_type == "border":
            current = self.rgb_to_hex(field.border_color)
        elif color_type == "fill":
            current = self.rgb_to_hex(field.fill_color)
        else:  # font
            current = self.rgb_to_hex(field.font_color)

        # Open color chooser
        color = colorchooser.askcolor(
            initialcolor=current, title=f"Choose {color_type} color"
        )

        if color[0]:  # color[0] is RGB tuple (0-255)
            rgb_normalized = tuple(c / 255.0 for c in color[0])

            if color_type == "border":
                field.border_color = rgb_normalized
                self.border_color_btn.config(bg=color[1])
            elif color_type == "fill":
                field.fill_color = rgb_normalized
                self.fill_color_btn.config(bg=color[1])
            else:  # font
                field.font_color = rgb_normalized
                self.font_color_btn.config(bg=color[1])

    def rgb_to_hex(self, rgb):
        """Convert RGB tuple (0-1) to hex color string"""
        r, g, b = [int(c * 255) for c in rgb]
        return f"#{r:02x}{g:02x}{b:02x}"

    def load_default_styles(self):
        """Load default style settings from config file"""
        default_config = {
            "border_color": (0, 0, 0),
            "fill_color": (1, 1, 1),
            "font_color": (0, 0, 0),
            "border_width": 1.0,
            "font_size": 12.0,
        }

        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r") as f:
                    config = json.load(f)
                    self.default_border_color = tuple(
                        config.get("border_color", default_config["border_color"])
                    )
                    self.default_fill_color = tuple(
                        config.get("fill_color", default_config["fill_color"])
                    )
                    self.default_font_color = tuple(
                        config.get("font_color", default_config["font_color"])
                    )
                    self.default_border_width = config.get(
                        "border_width", default_config["border_width"]
                    )
                    self.default_font_size = config.get(
                        "font_size", default_config["font_size"]
                    )
            else:
                # Use defaults
                self.default_border_color = default_config["border_color"]
                self.default_fill_color = default_config["fill_color"]
                self.default_font_color = default_config["font_color"]
                self.default_border_width = default_config["border_width"]
                self.default_font_size = default_config["font_size"]
        except Exception as e:
            print(f"Error loading config: {e}")
            # Use defaults on error
            self.default_border_color = default_config["border_color"]
            self.default_fill_color = default_config["fill_color"]
            self.default_font_color = default_config["font_color"]
            self.default_border_width = default_config["border_width"]
            self.default_font_size = default_config["font_size"]

    def save_default_styles(self):
        """Save default style settings to config file"""
        try:
            config = {
                "border_color": list(self.default_border_color),
                "fill_color": list(self.default_fill_color),
                "font_color": list(self.default_font_color),
                "border_width": self.default_border_width,
                "font_size": self.default_font_size,
            }
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def open_style_settings(self):
        """Open dialog to configure default style settings"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Default Style Settings")
        settings_window.geometry("450x550")
        settings_window.transient(self.root)
        settings_window.grab_set()

        # Make window resizable
        settings_window.resizable(True, True)

        # Main scrollable frame
        canvas = tk.Canvas(settings_window)
        scrollbar = ttk.Scrollbar(
            settings_window, orient="vertical", command=canvas.yview
        )
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")

        main_frame = ttk.Frame(scrollable_frame, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            main_frame, text="Default Field Appearance", font=("Arial", 12, "bold")
        ).pack(pady=(0, 10))

        ttk.Label(
            main_frame,
            text="These settings will apply to all new fields you create.",
            wraplength=350,
            foreground="gray",
        ).pack(pady=(0, 20))

        # Settings grid
        settings_frame = ttk.Frame(main_frame)
        settings_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))

        row = 0

        # Border Width
        ttk.Label(settings_frame, text="Border Width:", font=("Arial", 9, "bold")).grid(
            row=row, column=0, sticky=tk.W, pady=10, padx=5
        )
        border_width_var = tk.StringVar(value=str(self.default_border_width))
        ttk.Spinbox(
            settings_frame,
            from_=0,
            to=10,
            increment=0.5,
            textvariable=border_width_var,
            width=15,
        ).grid(row=row, column=1, sticky=tk.W, padx=10, pady=10)
        row += 1

        # Font Size
        ttk.Label(settings_frame, text="Font Size:", font=("Arial", 9, "bold")).grid(
            row=row, column=0, sticky=tk.W, pady=10, padx=5
        )
        font_size_var = tk.StringVar(value=str(self.default_font_size))
        ttk.Spinbox(
            settings_frame,
            from_=6,
            to=72,
            increment=1,
            textvariable=font_size_var,
            width=15,
        ).grid(row=row, column=1, sticky=tk.W, padx=10, pady=10)
        row += 1

        # Border Color
        ttk.Label(settings_frame, text="Border Color:", font=("Arial", 9, "bold")).grid(
            row=row, column=0, sticky=tk.W, pady=10, padx=5
        )
        border_color_display = tk.Button(
            settings_frame,
            text="Choose Color",
            bg=self.rgb_to_hex(self.default_border_color),
            width=15,
            relief=tk.RAISED,
            bd=2,
        )
        border_color_display.grid(row=row, column=1, sticky=tk.W, padx=10, pady=10)
        border_color_value = [self.default_border_color]

        def choose_border_color():
            from tkinter import colorchooser

            color = colorchooser.askcolor(
                initialcolor=self.rgb_to_hex(border_color_value[0]),
                title="Choose Border Color",
            )
            if color[0]:
                border_color_value[0] = tuple(c / 255.0 for c in color[0])
                border_color_display.config(bg=color[1])

        border_color_display.config(command=choose_border_color)
        row += 1

        # Fill Color
        ttk.Label(settings_frame, text="Fill Color:", font=("Arial", 9, "bold")).grid(
            row=row, column=0, sticky=tk.W, pady=10, padx=5
        )
        fill_color_display = tk.Button(
            settings_frame,
            text="Choose Color",
            bg=self.rgb_to_hex(self.default_fill_color),
            width=15,
            relief=tk.RAISED,
            bd=2,
        )
        fill_color_display.grid(row=row, column=1, sticky=tk.W, padx=10, pady=10)
        fill_color_value = [self.default_fill_color]

        def choose_fill_color():
            from tkinter import colorchooser

            color = colorchooser.askcolor(
                initialcolor=self.rgb_to_hex(fill_color_value[0]),
                title="Choose Fill Color",
            )
            if color[0]:
                fill_color_value[0] = tuple(c / 255.0 for c in color[0])
                fill_color_display.config(bg=color[1])

        fill_color_display.config(command=choose_fill_color)
        row += 1

        # Font Color
        ttk.Label(settings_frame, text="Font Color:", font=("Arial", 9, "bold")).grid(
            row=row, column=0, sticky=tk.W, pady=10, padx=5
        )
        font_color_display = tk.Button(
            settings_frame,
            text="Choose Color",
            bg=self.rgb_to_hex(self.default_font_color),
            width=15,
            relief=tk.RAISED,
            bd=2,
        )
        font_color_display.grid(row=row, column=1, sticky=tk.W, padx=10, pady=10)
        font_color_value = [self.default_font_color]

        def choose_font_color():
            from tkinter import colorchooser

            color = colorchooser.askcolor(
                initialcolor=self.rgb_to_hex(font_color_value[0]),
                title="Choose Font Color",
            )
            if color[0]:
                font_color_value[0] = tuple(c / 255.0 for c in color[0])
                font_color_display.config(bg=color[1])

        font_color_display.config(command=choose_font_color)
        row += 1

        # Separator
        ttk.Separator(main_frame, orient="horizontal").pack(fill="x", pady=10)

        # Buttons frame - fixed at bottom
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, pady=10)

        def save_settings():
            try:
                self.default_border_width = float(border_width_var.get())
                self.default_font_size = float(font_size_var.get())
                self.default_border_color = border_color_value[0]
                self.default_fill_color = fill_color_value[0]
                self.default_font_color = font_color_value[0]

                # Save to config file
                self.save_default_styles()

                messagebox.showinfo(
                    "Success",
                    "Default style settings saved!\n\n"
                    + "New fields will use these settings.\n"
                    + "Settings are now persistent.",
                    parent=settings_window,
                )
                settings_window.destroy()
            except ValueError:
                messagebox.showwarning(
                    "Invalid Input",
                    "Please enter valid numeric values.",
                    parent=settings_window,
                )

        def reset_to_defaults():
            border_width_var.set("1.0")
            font_size_var.set("12.0")
            border_color_value[0] = (0, 0, 0)
            fill_color_value[0] = (1, 1, 1)
            font_color_value[0] = (0, 0, 0)
            border_color_display.config(bg="#000000")
            fill_color_display.config(bg="#ffffff")
            font_color_display.config(bg="#000000")

        ttk.Button(
            button_frame, text="Save Settings", command=save_settings, width=15
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            button_frame, text="Reset to Defaults", command=reset_to_defaults, width=18
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            button_frame, text="Cancel", command=settings_window.destroy, width=12
        ).pack(side=tk.LEFT, padx=5)

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
            self.selected_field_idx = None
            self.update_fields_list()
            self.render_page()
            self.info_label.config(text="Select a field to customize")

    def clear_all_fields(self):
        if messagebox.askyesno("Confirm", "Delete all fields?"):
            self.fields = []
            self.selected_field_idx = None
            self.update_fields_list()
            self.render_page()
            self.info_label.config(text="Select a field to customize")

    def detect_existing_fields(self):
        """Detect and load existing form fields from the PDF"""
        if not self.pdf_doc:
            return

        try:
            detected_count = 0

            # Progress dialog
            progress_window = tk.Toplevel(self.root)
            progress_window.title("Detecting Fields")
            progress_window.geometry("400x150")
            progress_window.transient(self.root)
            progress_window.grab_set()

            ttk.Label(
                progress_window,
                text="Scanning PDF for form fields...",
                font=("Arial", 10),
            ).pack(pady=20)
            progress_bar = ttk.Progressbar(
                progress_window, length=350, mode="determinate"
            )
            progress_bar.pack(pady=10)
            status_label = ttk.Label(progress_window, text="")
            status_label.pack(pady=10)

            progress_window.update()

            total_pages = len(self.pdf_doc)
            progress_bar["maximum"] = total_pages

            for page_num in range(total_pages):
                status_label.config(
                    text=f"Processing page {page_num + 1} of {total_pages}..."
                )
                progress_bar["value"] = page_num + 1
                progress_window.update()

                page = self.pdf_doc[page_num]

                # Get all widgets (form fields) on the page
                widgets = page.widgets()

                for widget in widgets:
                    try:
                        # Extract widget properties
                        field_name = widget.field_name or f"field_{detected_count + 1}"
                        field_rect = widget.rect

                        # Determine field type
                        field_type = self._get_field_type_from_widget(widget)

                        # Extract appearance properties
                        border_color = (
                            widget.border_color if widget.border_color else (0, 0, 0)
                        )
                        fill_color = (
                            widget.fill_color if widget.fill_color else (1, 1, 1)
                        )
                        border_width = (
                            widget.border_width if widget.border_width else 1.0
                        )
                        font_size = (
                            widget.text_fontsize if widget.text_fontsize else 12.0
                        )
                        font_color = (
                            widget.text_color if widget.text_color else (0, 0, 0)
                        )

                        # Get max chars for comb fields
                        max_chars = 0
                        if widget.field_type == fitz.PDF_WIDGET_TYPE_TEXT:
                            max_chars = widget.text_maxlen or 0

                        # Create FormField object
                        field = FormField(
                            field_type=field_type,
                            rect=(
                                field_rect.x0,
                                field_rect.y0,
                                field_rect.x1,
                                field_rect.y1,
                            ),
                            name=field_name,
                            page_num=page_num,
                            max_chars=max_chars,
                            border_color=border_color,
                            fill_color=fill_color,
                            border_width=border_width,
                            font_size=font_size,
                            font_color=font_color,
                        )

                        self.fields.append(field)
                        detected_count += 1

                    except Exception as e:
                        print(f"Error processing widget: {str(e)}")
                        continue

            progress_window.destroy()

            if detected_count > 0:
                self.update_fields_list()
                self.render_page()
                messagebox.showinfo(
                    "Fields Detected",
                    f"Found {detected_count} existing form field(s).\n\n"
                    + "You can edit their properties or add new fields.",
                    parent=self.root,
                )
            # If no fields detected, don't show any message - user can just start creating fields

        except Exception as e:
            print(f"Field detection error: {str(e)}")
            # Don't show error dialog - just continue without loading fields

    def _get_field_type_from_widget(self, widget):
        """Determine our field type from PyMuPDF widget type"""
        widget_type = widget.field_type

        if widget_type == fitz.PDF_WIDGET_TYPE_TEXT:
            # Check for multiline or comb flags
            field_flags = widget.field_flags if hasattr(widget, "field_flags") else 0

            if field_flags & fitz.PDF_TX_FIELD_IS_COMB:
                return "comb"
            elif field_flags & fitz.PDF_TX_FIELD_IS_MULTILINE:
                # Distinguish between multiline and textarea based on size
                rect = widget.rect
                height = rect.y1 - rect.y0
                if height > 50:
                    return "textarea"
                else:
                    return "multiline"
            else:
                return "text"

        elif widget_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
            return "checkbox"

        elif widget_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
            return "radio"

        elif widget_type == fitz.PDF_WIDGET_TYPE_COMBOBOX:
            return "text"  # Treat as text field

        elif widget_type == fitz.PDF_WIDGET_TYPE_LISTBOX:
            return "textarea"  # Treat as text area

        else:
            return "text"  # Default to text field

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
                    widget.border_width = field.border_width
                    widget.border_color = field.border_color
                    widget.fill_color = field.fill_color
                    widget.text_font = "helv"
                    widget.text_fontsize = field.font_size
                    widget.text_color = field.font_color

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
