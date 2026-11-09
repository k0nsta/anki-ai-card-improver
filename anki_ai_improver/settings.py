"""Settings dialog and Tools menu registration."""

from pathlib import Path

from aqt import mw
from aqt.qt import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .config import (
    Settings,
    add_prompt,
    delete_prompt,
    load_api_key,
    remove_deck_prompt,
    rename_prompt,
    save_api_key,
    set_deck_prompt,
)


def _user_files():
    return Path(__file__).parent / "user_files"


def _addon_name() -> str:
    return mw.addonManager.addonFromModule(__name__)


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI Card Improver Settings")
        self.addon_name = _addon_name()
        self.values = mw.addonManager.getConfig(self.addon_name) or {}
        self.settings = Settings.from_dict(
            {
                **self.values,
                "base_url": self.values.get("base_url") or "https://example.invalid/v1",
                "model": self.values.get("model") or "not-configured",
            }
        )
        self.base_url = QLineEdit(str(self.values.get("base_url", "")), self)
        self.model = QLineEdit(str(self.values.get("model", "")), self)
        self.api_key = QLineEdit(load_api_key(_user_files()) or "", self)
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)

        tabs = QTabWidget(self)
        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._prompts_tab(), "Prompts")
        tabs.addTab(self._decks_tab(), "Decks")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    def _general_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        form.addRow("Base URL", self.base_url)
        form.addRow("Model", self.model)
        form.addRow("API key", self.api_key)
        return page

    def _prompts_tab(self) -> QWidget:
        page = QWidget(self)
        self.prompt_list = QListWidget(page)
        self.prompt_text = QPlainTextEdit(page)
        self.prompt_text.textChanged.connect(self._store_prompt_text)
        self.prompt_list.currentItemChanged.connect(self._select_prompt)

        self.add_prompt_button = QPushButton("Add", page)
        self.rename_prompt_button = QPushButton("Rename", page)
        self.delete_prompt_button = QPushButton("Delete", page)
        self.default_prompt_button = QPushButton("Make default", page)
        self.add_prompt_button.clicked.connect(self._add_prompt)
        self.rename_prompt_button.clicked.connect(self._rename_prompt)
        self.delete_prompt_button.clicked.connect(self._delete_prompt)
        self.default_prompt_button.clicked.connect(self._make_default)

        controls = QHBoxLayout()
        for button in (
            self.add_prompt_button,
            self.rename_prompt_button,
            self.delete_prompt_button,
            self.default_prompt_button,
        ):
            controls.addWidget(button)
        content = QHBoxLayout()
        content.addWidget(self.prompt_list, 1)
        content.addWidget(self.prompt_text, 2)
        layout = QVBoxLayout(page)
        layout.addLayout(controls)
        layout.addLayout(content)
        self._refresh_prompts()
        return page

    def _decks_tab(self) -> QWidget:
        page = QWidget(self)
        self.deck_table = QTableWidget(0, 2, page)
        self.deck_table.setHorizontalHeaderLabels(["Deck", "Prompt"])
        self.deck_table.horizontalHeader().setStretchLastSection(True)
        self.deck_choices = [(int(deck.id), deck.name) for deck in mw.col.decks.all_names_and_ids()]
        for deck_id, prompt_name in self.settings.decks.items():
            if not any(str(existing_id) == deck_id for existing_id, _ in self.deck_choices):
                self.deck_choices.append((int(deck_id), f"Unknown deck ({deck_id})"))

        for deck_id, prompt_name in self.settings.decks.items():
            self._add_mapping_row(int(deck_id), prompt_name)
        add_button = QPushButton("Add mapping", page)
        remove_button = QPushButton("Remove mapping", page)
        add_button.clicked.connect(self._add_mapping)
        remove_button.clicked.connect(self._remove_mapping)
        controls = QHBoxLayout()
        controls.addWidget(add_button)
        controls.addWidget(remove_button)
        controls.addStretch(1)
        layout = QVBoxLayout(page)
        layout.addLayout(controls)
        layout.addWidget(self.deck_table)
        return page

    def _prompt_name(self) -> str | None:
        item = self.prompt_list.currentItem()
        return item.data(256) if item is not None else None

    def _store_prompt_text(self) -> None:
        name = self._prompt_name()
        if name is not None:
            self.settings.prompts[name] = self.prompt_text.toPlainText()

    def _refresh_prompts(self, selected: str | None = None) -> None:
        self.prompt_list.blockSignals(True)
        self.prompt_list.clear()
        for name in self.settings.prompts:
            marker = " (default)" if name == self.settings.default_prompt else ""
            list_item = QListWidgetItem(f"{name}{marker}", self.prompt_list)
            list_item.setData(256, name)
            if name == (selected or self.settings.default_prompt):
                self.prompt_list.setCurrentItem(list_item)
        self.prompt_list.blockSignals(False)
        self._select_prompt(self.prompt_list.currentItem(), None)

    def _select_prompt(self, current, _previous) -> None:
        if current is None:
            self.prompt_text.setPlainText("")
            self.prompt_text.setEnabled(False)
            self.rename_prompt_button.setEnabled(False)
            self.delete_prompt_button.setEnabled(False)
            self.default_prompt_button.setEnabled(False)
            return
        name = current.data(256)
        self.prompt_text.blockSignals(True)
        self.prompt_text.setPlainText(self.settings.prompts[name])
        self.prompt_text.blockSignals(False)
        self.prompt_text.setEnabled(True)
        self.rename_prompt_button.setEnabled(True)
        self.delete_prompt_button.setEnabled(name != self.settings.default_prompt)
        self.default_prompt_button.setEnabled(name != self.settings.default_prompt)

    def _add_prompt(self) -> None:
        name, accepted = QInputDialog.getText(self, "Add prompt", "Prompt name")
        if not accepted:
            return
        self._store_prompt_text()
        try:
            self.settings = add_prompt(self.settings, name, "")
        except ValueError as error:
            QMessageBox.warning(self, "Prompt not added", str(error))
            return
        self._refresh_prompts(name.strip())
        self._refresh_mapping_prompt_choices()
        self.prompt_text.setFocus()

    def _rename_prompt(self) -> None:
        old_name = self._prompt_name()
        if old_name is None:
            return
        new_name, accepted = QInputDialog.getText(
            self, "Rename prompt", "Prompt name", text=old_name
        )
        if not accepted:
            return
        self._store_prompt_text()
        try:
            self.settings = rename_prompt(self.settings, old_name, new_name)
        except ValueError as error:
            QMessageBox.warning(self, "Prompt not renamed", str(error))
            return
        self._refresh_prompts(new_name.strip())
        self._refresh_mapping_prompt_choices(old_name, new_name.strip())

    def _delete_prompt(self) -> None:
        name = self._prompt_name()
        if name is None:
            return
        for row in range(self.deck_table.rowCount() - 1, -1, -1):
            prompt_picker = self.deck_table.cellWidget(row, 1)
            if prompt_picker is not None and prompt_picker.currentText() == name:
                self.deck_table.removeRow(row)
        try:
            self.settings = delete_prompt(self.settings, name)
        except ValueError as error:
            QMessageBox.warning(self, "Prompt not deleted", str(error))
            return
        self._refresh_prompts()
        self._refresh_mapping_prompt_choices()

    def _make_default(self) -> None:
        name = self._prompt_name()
        if name is None:
            return
        self._store_prompt_text()
        self.settings.default_prompt = name
        self._refresh_prompts(name)

    def _add_mapping(self) -> None:
        if not self.deck_choices:
            QMessageBox.information(self, "No decks", "There are no decks to map.")
            return
        self._add_mapping_row(self.deck_choices[0][0], self.settings.default_prompt)

    def _add_mapping_row(self, deck_id: int, prompt_name: str) -> None:
        row = self.deck_table.rowCount()
        self.deck_table.insertRow(row)
        deck_picker = QComboBox(self.deck_table)
        for choice_id, deck_name in self.deck_choices:
            deck_picker.addItem(deck_name, str(choice_id))
        index = deck_picker.findData(str(deck_id))
        if index >= 0:
            deck_picker.setCurrentIndex(index)
        prompt_picker = QComboBox(self.deck_table)
        prompt_picker.addItems(list(self.settings.prompts))
        prompt_index = prompt_picker.findText(prompt_name)
        if prompt_index >= 0:
            prompt_picker.setCurrentIndex(prompt_index)
        self.deck_table.setCellWidget(row, 0, deck_picker)
        self.deck_table.setCellWidget(row, 1, prompt_picker)

    def _remove_mapping(self) -> None:
        row = self.deck_table.currentRow()
        if row >= 0:
            self.deck_table.removeRow(row)

    def _refresh_mapping_prompt_choices(
        self, renamed_from: str | None = None, renamed_to: str | None = None
    ) -> None:
        names = list(self.settings.prompts)
        for row in range(self.deck_table.rowCount()):
            picker = self.deck_table.cellWidget(row, 1)
            if picker is None:
                continue
            selected = picker.currentText()
            if selected == renamed_from:
                selected = renamed_to or selected
            picker.clear()
            picker.addItems(names)
            index = picker.findText(selected)
            picker.setCurrentIndex(
                index if index >= 0 else picker.findText(self.settings.default_prompt)
            )

    def accept(self) -> None:
        self._store_prompt_text()
        self.values["base_url"] = self.base_url.text().strip()
        self.values["model"] = self.model.text().strip()
        self.values["default_prompt"] = self.settings.default_prompt
        self.values["prompts"] = self.settings.prompts
        mappings = self.settings
        for deck_id in list(mappings.decks):
            mappings = remove_deck_prompt(mappings, deck_id)
        for row in range(self.deck_table.rowCount()):
            deck_picker = self.deck_table.cellWidget(row, 0)
            prompt_picker = self.deck_table.cellWidget(row, 1)
            if deck_picker is not None and prompt_picker is not None:
                mappings = set_deck_prompt(
                    mappings, deck_picker.currentData(), prompt_picker.currentText()
                )
        self.values["decks"] = mappings.decks
        mw.addonManager.writeConfig(self.addon_name, self.values)
        save_api_key(_user_files(), self.api_key.text())
        super().accept()


def show_settings(parent=None) -> None:
    SettingsDialog(parent or mw).exec()


def register_settings() -> None:
    mw.addonManager.setConfigAction(__name__, lambda: show_settings(mw))
    action = mw.form.menuTools.addAction("AI Card Improver Settings…")
    action.triggered.connect(lambda: show_settings(mw))
