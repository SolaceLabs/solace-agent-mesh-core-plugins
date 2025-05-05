"""
Unit tests for the PreprocessorBase class.
"""

import unittest
import sys
import os
from unittest.mock import MagicMock

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from src.agents.rag.services.preprocessor.preprocessor_base import PreprocessorBase


class ConcretePreprocessor(PreprocessorBase):
    """Concrete implementation of PreprocessorBase for testing."""

    def __init__(self, config=None):
        super().__init__(config)
        self.can_process_result = True
        self.preprocess_result = "Preprocessed content"

    def preprocess(self, file_path):
        return self.preprocess_result

    def can_process(self, file_path):
        return self.can_process_result


class TestPreprocessorBase(unittest.TestCase):
    """Test cases for the PreprocessorBase class."""

    def test_init_default_config(self):
        """Test initialization with default config."""
        preprocessor = ConcretePreprocessor()
        self.assertEqual(preprocessor.config, {})

    def test_init_custom_config(self):
        """Test initialization with custom config."""
        config = {"key": "value"}
        preprocessor = ConcretePreprocessor(config)
        self.assertEqual(preprocessor.config, config)

    def test_preprocess_method(self):
        """Test the preprocess method."""
        preprocessor = ConcretePreprocessor()
        result = preprocessor.preprocess("dummy/path")
        self.assertEqual(result, "Preprocessed content")

    def test_can_process_method(self):
        """Test the can_process method."""
        preprocessor = ConcretePreprocessor()

        # Test when can_process returns True
        preprocessor.can_process_result = True
        result = preprocessor.can_process("dummy/path")
        self.assertTrue(result)

        # Test when can_process returns False
        preprocessor.can_process_result = False
        result = preprocessor.can_process("dummy/path")
        self.assertFalse(result)

    def test_abstract_methods(self):
        """Test that abstract methods raise NotImplementedError when not implemented."""
        # Attempt to instantiate the abstract base class directly
        with self.assertRaises(TypeError):
            PreprocessorBase()


if __name__ == "__main__":
    unittest.main()
