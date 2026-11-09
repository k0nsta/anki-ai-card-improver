"""Plain-text review dialog for proposed note changes."""

from collections.abc import Callable

from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from .client import Proposal
from .errors import AiError
from .logic import is_stale, merge_accepted
from .prompts import NoteSnapshot


class DiffDialog(QDialog):
    def __init__(
        self,
        parent,
        snapshot: NoteSnapshot,
        proposal: Proposal,
        prompt_name: str,
        prompt_names: list[str],
        retry: Callable[[str, Callable[[Proposal], None], Callable[[Exception], None]], None],
        apply: Callable[[dict[str, str]], None],
        current_state: Callable[[], tuple[int | None, int | None, int | None]],
    ) -> None:
        super().__init__(parent)
        self.snapshot = snapshot
        self.proposal = proposal
        self.retry_request = retry
        self.apply_changes = apply
        self.current_state = current_state
        self.checkboxes: dict[str, QCheckBox] = {}
        self.setWindowTitle("Review AI Suggestions")

        self.prompt = QComboBox(self)
        self.prompt.addItems(prompt_names)
        selected = self.prompt.findText(prompt_name)
        if selected >= 0:
            self.prompt.setCurrentIndex(selected)
        self.retry_button = QPushButton("Retry", self)
        self.retry_button.clicked.connect(self._retry)
        prompt_row = QHBoxLayout()
        prompt_row.addWidget(QLabel("Prompt", self))
        prompt_row.addWidget(self.prompt, 1)
        prompt_row.addWidget(self.retry_button)

        self.fields_layout = QVBoxLayout()
        self._populate_fields()
        self.raw_view = QTextBrowser(self)
        self.raw_view.setPlainText(proposal.raw)
        self.raw_view.hide()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(prompt_row)
        layout.addLayout(self.fields_layout)
        layout.addWidget(self.raw_view)
        layout.addWidget(buttons)

    def _populate_fields(self) -> None:
        while self.fields_layout.count():
            item = self.fields_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.checkboxes.clear()
        for name, new_value in self.proposal.changed.items():
            checkbox = QCheckBox(name, self)
            checkbox.setChecked(True)
            self.checkboxes[name] = checkbox
            old_view = QTextBrowser(self)
            old_view.setPlainText(self.snapshot.fields[name])
            new_view = QTextBrowser(self)
            new_view.setPlainText(new_value)
            old_view.setMinimumHeight(70)
            new_view.setMinimumHeight(70)
            self.fields_layout.addWidget(checkbox)
            self.fields_layout.addWidget(QLabel("Current", self))
            self.fields_layout.addWidget(old_view)
            self.fields_layout.addWidget(QLabel("Suggested", self))
            self.fields_layout.addWidget(new_view)

    def _retry(self) -> None:
        self.retry_button.setEnabled(False)

        def receive(proposal: Proposal) -> None:
            self.proposal = proposal
            self.raw_view.setPlainText(proposal.raw)
            self.raw_view.hide()
            self._populate_fields()
            self.retry_button.setEnabled(True)

        def failed(error: Exception) -> None:
            self.retry_button.setEnabled(True)
            if isinstance(error, AiError) and error.kind == "bad_response":
                self.show_bad_response(error.message)
            else:
                QMessageBox.warning(self, "AI Card Improver", str(error))

        self.retry_request(self.prompt.currentText(), receive, failed)

    def show_bad_response(self, raw: str) -> None:
        self.raw_view.setPlainText(raw)
        self.raw_view.show()

    def _accept(self) -> None:
        note_id, mtime, target_id = self.current_state()
        if is_stale(self.snapshot, note_id, mtime, target_id):
            QMessageBox.warning(
                self,
                "Note changed",
                "This note or card changed while the AI request was running. No changes were applied.",
            )
            self.reject()
            return
        accepted = [name for name, checkbox in self.checkboxes.items() if checkbox.isChecked()]
        self.apply_changes(merge_accepted(self.snapshot.fields, self.proposal, accepted))
        self.accept()
