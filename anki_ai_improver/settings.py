"""Minimal add-on settings dialog and Tools menu registration."""

from pathlib import Path

from aqt import mw
from aqt.qt import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout

from .config import load_api_key, save_api_key


def _user_files():
    return Path(__file__).parent / "user_files"


def _addon_name() -> str:
    return mw.addonManager.addonFromModule(__name__)


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI Card Improver Settings")
        addon_name = _addon_name()
        values = mw.addonManager.getConfig(addon_name) or {}
        self.base_url = QLineEdit(str(values.get("base_url", "")), self)
        self.model = QLineEdit(str(values.get("model", "")), self)
        self.api_key = QLineEdit(load_api_key(_user_files()) or "", self)
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)

        form = QFormLayout()
        form.addRow("Base URL", self.base_url)
        form.addRow("Model", self.model)
        form.addRow("API key", self.api_key)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def accept(self) -> None:
        addon_name = _addon_name()
        values = mw.addonManager.getConfig(addon_name) or {}
        values["base_url"] = self.base_url.text().strip()
        values["model"] = self.model.text().strip()
        mw.addonManager.writeConfig(addon_name, values)
        save_api_key(
            _user_files(),
            self.api_key.text(),
        )
        super().accept()


def show_settings(parent=None) -> None:
    SettingsDialog(parent or mw).exec()


def register_settings() -> None:
    mw.addonManager.setConfigAction(__name__, lambda: show_settings(mw))
    action = mw.form.menuTools.addAction("AI Card Improver Settings…")
    action.triggered.connect(lambda: show_settings(mw))
