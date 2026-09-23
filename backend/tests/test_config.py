import os
from pathlib import Path
import unittest
from unittest.mock import patch

from app.config import ROOT_DIR, get_settings


class PortableConfigTest(unittest.TestCase):
    def test_default_archive_is_relative_to_backend_not_developer_machine(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = get_settings.__wrapped__()
        self.assertEqual(settings.data_zip_path, ROOT_DIR / "data" / "source.zip")
        self.assertEqual(settings.max_recommendations, 0)
        self.assertEqual(settings.ai_provider, "template")
        self.assertEqual(settings.openai_api_key, "")

    def test_relative_archive_is_resolved_against_backend_directory(self):
        with patch.dict(os.environ, {"DATA_ZIP_PATH": "other/input.zip"}, clear=True):
            settings = get_settings.__wrapped__()
        self.assertEqual(settings.data_zip_path, ROOT_DIR / "other" / "input.zip")

    def test_existing_absolute_archive_path_is_preserved(self):
        archive = Path(__file__).resolve().parent / "input.zip"
        with patch.dict(os.environ, {"DATA_ZIP_PATH": str(archive)}, clear=True):
            self.assertEqual(get_settings.__wrapped__().data_zip_path, archive)
