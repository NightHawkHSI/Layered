"""export_dialog.py — Modern export options dialog for PyQt6.

Provides a polished export workflow for:
    • Single composite image export
    • Per-layer export with manifest.json
    • Alpha preservation / flattening
    • Format-aware UI behavior
    • Smart extension handling
    • Validation + UX improvements
    • Clean modern layout

Supported formats are pulled from export.FORMATS:
    {
        "PNG":  ("png",  True),
        "JPG":  ("jpg",  False),
        ...
    }
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
)

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# ----------------------------------------------------------------------
# Example fallback
# Replace with:
# from ..export import FORMATS
# ----------------------------------------------------------------------

try:
    from app.io.export import FORMATS
except Exception:
    FORMATS = {
        "PNG": ("png", True),
        "WEBP": ("webp", True),
        "TIFF": ("tiff", True),
        "DDS": ("dds", True),
        "BMP": ("bmp", False),
        "JPG": ("jpg", False),
    }


class ExportDialog(QDialog):
    """Advanced export settings dialog."""

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        default_dir: Optional[Path] = None,
    ) -> None:
        super().__init__(parent)

        self._default_dir = Path(
            default_dir or Path.cwd()
        )

        self._flatten_bg = (
            255,
            255,
            255,
        )

        self._build_window()
        self._build_ui()
        self._connect_signals()

        self._refresh_format_state()
        self._update_path_mode()

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------

    def _build_window(self) -> None:
        self.setWindowTitle(
            "Export Artwork"
        )

        self.resize(620, 420)

        self.setMinimumWidth(520)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        root.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        root.setSpacing(18)

        # --------------------------------------------------------------
        # Header
        # --------------------------------------------------------------

        title = QLabel(
            "Export Settings"
        )

        title.setStyleSheet(
            """
            QLabel {
                font-size: 20px;
                font-weight: 700;
            }
            """
        )

        subtitle = QLabel(
            "Configure output format, transparency, "
            "and export destination."
        )

        subtitle.setStyleSheet(
            """
            QLabel {
                color: #999;
            }
            """
        )

        root.addWidget(title)
        root.addWidget(subtitle)

        # --------------------------------------------------------------
        # Format
        # --------------------------------------------------------------

        self.format_combo = QComboBox()

        self.format_combo.addItems(
            FORMATS.keys()
        )

        self.format_combo.setMinimumHeight(32)

        self.format_info = QLabel()

        self.format_info.setWordWrap(True)

        self.format_info.setStyleSheet(
            """
            QLabel {
                color: #999;
            }
            """
        )

        # --------------------------------------------------------------
        # Export mode
        # --------------------------------------------------------------

        self.mode_composite = QRadioButton(
            "Single composite image"
        )

        self.mode_layers = QRadioButton(
            "Per-layer export + manifest.json"
        )

        self.mode_composite.setChecked(True)

        mode_layout = QVBoxLayout()

        mode_layout.setSpacing(8)

        mode_layout.addWidget(
            self.mode_composite
        )

        mode_layout.addWidget(
            self.mode_layers
        )

        mode_group = QGroupBox(
            "Export Mode"
        )

        mode_group.setLayout(
            mode_layout
        )

        # --------------------------------------------------------------
        # Transparency
        # --------------------------------------------------------------

        self.alpha_check = QCheckBox(
            "Preserve alpha channel"
        )

        self.alpha_check.setChecked(True)

        self.alpha_hint = QLabel()

        self.alpha_hint.setWordWrap(True)

        self.alpha_hint.setStyleSheet(
            """
            QLabel {
                color: #999;
            }
            """
        )

        # --------------------------------------------------------------
        # Flatten background
        # --------------------------------------------------------------

        self.bg_btn = QPushButton()

        self.bg_btn.setMinimumHeight(32)

        self.bg_preview = QFrame()

        self.bg_preview.setFixedSize(
            28,
            28,
        )

        self.bg_preview.setFrameShape(
            QFrame.Shape.Box
        )

        bg_layout = QHBoxLayout()

        bg_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        bg_layout.setSpacing(10)

        bg_layout.addWidget(
            self.bg_btn
        )

        bg_layout.addWidget(
            self.bg_preview
        )

        bg_layout.addStretch(1)

        # --------------------------------------------------------------
        # Output path
        # --------------------------------------------------------------

        self.path_label = QLabel()

        self.path_edit = QLineEdit()

        self.path_edit.setPlaceholderText(
            "Choose export destination..."
        )

        self.path_edit.setMinimumHeight(34)

        self.path_btn = QPushButton(
            "Browse..."
        )

        self.path_btn.setMinimumHeight(34)

        path_layout = QHBoxLayout()

        path_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        path_layout.setSpacing(10)

        path_layout.addWidget(
            self.path_edit,
            1,
        )

        path_layout.addWidget(
            self.path_btn
        )

        # --------------------------------------------------------------
        # Form layout
        # --------------------------------------------------------------

        form = QFormLayout()

        form.setSpacing(16)

        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTop
        )

        form.addRow(
            "Format:",
            self.format_combo,
        )

        form.addRow(
            "",
            self.format_info,
        )

        form.addRow(
            "",
            mode_group,
        )

        form.addRow(
            "Transparency:",
            self.alpha_check,
        )

        form.addRow(
            "",
            self.alpha_hint,
        )

        form.addRow(
            "Flatten:",
            bg_layout,
        )

        form.addRow(
            self.path_label,
            path_layout,
        )

        root.addLayout(form)

        # --------------------------------------------------------------
        # Buttons
        # --------------------------------------------------------------

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )

        self.export_btn = self.buttons.button(
            QDialogButtonBox.StandardButton.Ok
        )

        self.export_btn.setText(
            "Export"
        )

        self.export_btn.setMinimumHeight(
            34
        )

        root.addStretch(1)
        root.addWidget(self.buttons)

        # --------------------------------------------------------------
        # Style
        # --------------------------------------------------------------

        self.setStyleSheet(
            """
            QDialog {
                background: #242833;
            }

            QLabel {
                color: #ECECEC;
                font-size: 13px;
            }

            QGroupBox {
                border: 1px solid #444;
                border-radius: 10px;
                margin-top: 8px;
                padding-top: 12px;
                font-weight: 600;
                color: #F0F0F0;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }

            QComboBox,
            QLineEdit {
                background: #2E3442;
                border: 1px solid #4A5266;
                border-radius: 6px;
                padding: 6px 10px;
                color: white;
            }

            QComboBox:hover,
            QLineEdit:hover {
                border-color: #6A84C7;
            }

            QPushButton {
                background: #3C465A;
                border: 1px solid #55627D;
                border-radius: 6px;
                padding: 6px 14px;
                color: white;
            }

            QPushButton:hover {
                background: #4A5B7A;
                border-color: #7DA2FF;
            }

            QPushButton:pressed {
                background: #36425A;
            }

            QPushButton:disabled {
                color: #777;
                border-color: #444;
                background: #2A2D36;
            }

            QRadioButton,
            QCheckBox {
                spacing: 8px;
            }
            """
        )

        self._update_bg_button()

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self.format_combo.currentTextChanged.connect(
            self._refresh_format_state
        )

        self.alpha_check.toggled.connect(
            self._refresh_alpha_state
        )

        self.mode_composite.toggled.connect(
            self._update_path_mode
        )

        self.bg_btn.clicked.connect(
            self._pick_bg
        )

        self.path_btn.clicked.connect(
            self._pick_path
        )

        self.buttons.accepted.connect(
            self._validate_and_accept
        )

        self.buttons.rejected.connect(
            self.reject
        )

    # ------------------------------------------------------------------
    # State updates
    # ------------------------------------------------------------------

    def _refresh_format_state(self) -> None:
        fmt = self.format_combo.currentText()

        extension, supports_alpha = FORMATS[
            fmt
        ]

        if supports_alpha:
            self.format_info.setText(
                f"{fmt} supports transparency."
            )
        else:
            self.format_info.setText(
                f"{fmt} does not support transparency. "
                "Transparent pixels will be flattened."
            )

        self.alpha_check.setEnabled(
            supports_alpha
        )

        if not supports_alpha:
            self.alpha_check.setChecked(False)

        self._refresh_alpha_state()

    def _refresh_alpha_state(self) -> None:
        keep_alpha = (
            self.alpha_check.isChecked()
        )

        enable_flatten = not keep_alpha

        self.bg_btn.setEnabled(
            enable_flatten
        )

        self.bg_preview.setEnabled(
            enable_flatten
        )

        if keep_alpha:
            self.alpha_hint.setText(
                "Transparent pixels will remain transparent."
            )
        else:
            self.alpha_hint.setText(
                "Transparent pixels will be replaced "
                "with the selected background color."
            )

        self._animate_widget_enabled(
            self.bg_btn,
            enable_flatten,
        )

        self._animate_widget_enabled(
            self.bg_preview,
            enable_flatten,
        )

    def _update_path_mode(self) -> None:
        if self.mode_composite.isChecked():
            self.path_label.setText(
                "Output File:"
            )
        else:
            self.path_label.setText(
                "Output Folder:"
            )

    # ------------------------------------------------------------------
    # Widget fade
    # ------------------------------------------------------------------

    def _animate_widget_enabled(
        self,
        widget: QWidget,
        enabled: bool,
    ) -> None:
        effect = widget.graphicsEffect()

        if not isinstance(
            effect,
            QGraphicsOpacityEffect,
        ):
            effect = (
                QGraphicsOpacityEffect()
            )

            widget.setGraphicsEffect(
                effect
            )

        anim = QPropertyAnimation(
            effect,
            b"opacity",
            self,
        )

        anim.setDuration(120)

        anim.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )

        anim.setStartValue(
            effect.opacity()
        )

        anim.setEndValue(
            1.0 if enabled else 0.45
        )

        anim.start()

        self._opacity_anim = anim

    # ------------------------------------------------------------------
    # Background color
    # ------------------------------------------------------------------

    def _update_bg_button(self) -> None:
        r, g, b = self._flatten_bg

        hex_color = (
            QColor(r, g, b)
            .name()
            .upper()
        )

        self.bg_btn.setText(
            f"Background Color: {hex_color}"
        )

        self.bg_preview.setStyleSheet(
            f"""
            QFrame {{
                background: {hex_color};
                border: 1px solid #555;
                border-radius: 5px;
            }}
            """
        )

    def _pick_bg(self) -> None:
        r, g, b = self._flatten_bg

        color = QColorDialog.getColor(
            QColor(r, g, b),
            self,
            "Choose Flatten Background",
        )

        if not color.isValid():
            return

        self._flatten_bg = (
            color.red(),
            color.green(),
            color.blue(),
        )

        self._update_bg_button()

    # ------------------------------------------------------------------
    # Path picking
    # ------------------------------------------------------------------

    def _pick_path(self) -> None:
        fmt = self.format_combo.currentText()

        extension, _ = FORMATS[fmt]

        if self.mode_composite.isChecked():
            default_path = (
                self._default_dir
                / f"export.{extension}"
            )

            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Image",
                str(default_path),
                f"{fmt} (*.{extension})",
            )

        else:
            path = QFileDialog.getExistingDirectory(
                self,
                "Choose Export Folder",
                str(self._default_dir),
            )

        if path:
            self.path_edit.setText(path)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_and_accept(self) -> None:
        path = (
            self.path_edit.text()
            .strip()
        )

        if not path:
            QMessageBox.warning(
                self,
                "Missing Export Path",
                "Please choose an export destination.",
            )

            return

        if self.mode_composite.isChecked():
            export_path = Path(path)

            if not export_path.suffix:
                extension, _ = FORMATS[
                    self.format_combo.currentText()
                ]

                export_path = (
                    export_path.with_suffix(
                        f".{extension}"
                    )
                )

                self.path_edit.setText(
                    str(export_path)
                )

        self.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selected_format(self) -> str:
        return (
            self.format_combo.currentText()
        )

    def selected_extension(self) -> str:
        extension, _ = FORMATS[
            self.selected_format()
        ]

        return extension

    def supports_alpha(self) -> bool:
        _, supports_alpha = FORMATS[
            self.selected_format()
        ]

        return supports_alpha

    def export_path(self) -> Path:
        return Path(
            self.path_edit.text().strip()
        )

    def flatten_color(
        self,
    ) -> tuple[int, int, int]:
        return self._flatten_bg

    def keep_alpha(self) -> bool:
        return (
            self.alpha_check.isChecked()
        )

    def is_per_layer_export(
        self,
    ) -> bool:
        return (
            self.mode_layers.isChecked()
        )

    def options(self) -> dict:
        """Return export configuration."""
        return {
            "format": self.selected_format(),
            "per_layer": self.is_per_layer_export(),
            "keep_alpha": self.keep_alpha(),
            "flatten_bg": self.flatten_color(),
            "path": str(
                self.export_path()
            ),
        }

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @classmethod
    def get_options(
        cls,
        parent: Optional[QWidget] = None,
        default_dir: Optional[Path] = None,
    ) -> Optional[dict]:
        dialog = cls(
            parent=parent,
            default_dir=default_dir,
        )

        if dialog.exec():
            return dialog.options()

        return None


# ----------------------------------------------------------------------
# Standalone test
# ----------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    dialog = ExportDialog()

    if dialog.exec():
        print("\nExport Options")
        print("----------------")

        for key, value in dialog.options().items():
            print(f"{key}: {value}")

    sys.exit(app.exec())