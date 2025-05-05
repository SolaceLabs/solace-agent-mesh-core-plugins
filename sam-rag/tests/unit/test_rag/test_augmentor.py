"""
Unit tests for the AugmentationService class.
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock, Mock

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# Mock modules
sys.modules["litellm"] = MagicMock()
import litellm

sys.modules["solace_ai_connector"] = MagicMock()
sys.modules["solace_ai_connector.common"] = MagicMock()
sys.modules["solace_ai_connector.common.log"] = MagicMock()
sys.modules["solace_ai_connector.common.log"].log = MagicMock()

from src.agents.rag.services.rag.augmentation_service import AugmentationService


class TestAugmentationService(unittest.TestCase):
    """Test cases for the AugmentationService class."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock configuration
        self.config = {
            "embedding": {
                "embedder_type": "openai",
                "embedder_params": {
                    "model": "text-embedding-ada-002",
                    "api_key": "test-key",
                },
            },
            "vector_db": {
                "db_type": "qdrant",
                "db_params": {
                    "url": "http://localhost:6333",
                    "collection_name": "test_collection",
                },
            },
            "llm": {
                "load_balancer": [
                    {
                        "model_name": "gpt-4o",
                        "litellm_params": {
                            "model": "openai/gpt-4o",
                            "api_key": "test-key",
                            "api_base": "https://api.openai.com/v1",
                            "temperature": 0.01,
                        },
                    }
                ]
            },
            "augmentor": {
                "merge_threshold": 0.7,
                "max_tokens_per_message": 1000,
            },
        }

        # Create patcher for Retriever
        self.retriever_patcher = patch(
            "src.agents.rag.services.rag.augmentation_service.Retriever"
        )
        self.mock_retriever_class = self.retriever_patcher.start()
        self.mock_retriever_instance = self.mock_retriever_class.return_value

        # Create patcher for litellm
        self.litellm_patcher = patch("litellm.completion")
        self.mock_litellm_completion = self.litellm_patcher.start()

        # Setup mock response for litellm.completion
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = "Improved text from LiteLLM"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        self.mock_litellm_completion.return_value = mock_response

        # Create augmentation service instance
        self.augmentor = AugmentationService(self.config)

    def tearDown(self):
        """Tear down test fixtures."""
        self.retriever_patcher.stop()
        self.litellm_patcher.stop()

    def test_init(self):
        """Test initialization."""
        # Check that services were initialized with correct configs
        self.mock_retriever_class.assert_called_once_with(self.config)
        self.assertEqual(self.augmentor.llm_config, self.config["llm"])
        self.assertEqual(
            self.augmentor.load_balancer_config, self.config["llm"]["load_balancer"]
        )
        self.assertTrue(self.augmentor.llm_available)

    def test_merge_chunks_by_source(self):
        """Test _merge_chunks_by_source method."""
        # Setup test data
        chunks = [
            {
                "text": "Chunk 1 text",
                "metadata": {"source": "doc1", "page": 1},
                "score": 0.9,
            },
            {
                "text": "Chunk 2 text",
                "metadata": {"source": "doc1", "page": 2},
                "score": 0.8,
            },
            {
                "text": "Chunk 3 text",
                "metadata": {"source": "doc2", "page": 1},
                "score": 0.7,
            },
        ]

        # Call the method
        result = self.augmentor._merge_chunks_by_source(chunks)

        # Assertions
        self.assertEqual(len(result), 2)  # Two sources

        # Check first merged chunk (doc1)
        self.assertEqual(result[0]["source"], "doc1")
        self.assertEqual(result[0]["score"], 0.9)  # Highest score
        self.assertEqual(result[0]["text"], "Chunk 1 text\nChunk 2 text")
        self.assertEqual(result[0]["metadata"], {"source": "doc1", "page": 1})

        # Check second merged chunk (doc2)
        self.assertEqual(result[1]["source"], "doc2")
        self.assertEqual(result[1]["score"], 0.7)
        self.assertEqual(result[1]["text"], "Chunk 3 text")
        self.assertEqual(result[1]["metadata"], {"source": "doc2", "page": 1})

    def test_invoke_litellm(self):
        """Test _invoke_litellm method."""
        # Call the method
        result = self.augmentor._invoke_litellm("Test prompt")

        # Assertions
        self.assertEqual(result, "Improved text from LiteLLM")
        self.mock_litellm_completion.assert_called_once()

        # Check that the correct parameters were passed to litellm.completion
        call_args = self.mock_litellm_completion.call_args[1]
        self.assertEqual(
            call_args["messages"], [{"role": "user", "content": "Test prompt"}]
        )
        self.assertEqual(
            call_args["model"], "openai/gpt-4o"
        )  # Default from the first model in load_balancer

    def test_augment_chunks_with_llm(self):
        """Test _augment_chunks_with_llm method."""
        # Setup test data
        chunks = [
            {
                "text": "Original text 1",
                "metadata": {"source": "doc1", "page": 1},
                "source": "doc1",
                "score": 0.9,
            },
            {
                "text": "Original text 2",
                "metadata": {"source": "doc2", "page": 1},
                "source": "doc2",
                "score": 0.8,
            },
        ]

        # Mock _invoke_litellm to return different responses for different calls
        with patch.object(
            self.augmentor,
            "_invoke_litellm",
            side_effect=["Improved text 1", "Improved text 2"],
        ):
            # Call the method
            result = self.augmentor._augment_chunks_with_llm("test query", chunks)

            # Assertions
            self.assertEqual(len(result), 2)

            # Check first augmented chunk
            self.assertEqual(result[0]["content"], "Improved text 1")
            self.assertEqual(result[0]["source"], "doc1")
            self.assertEqual(result[0]["metadata"], {"source": "doc1", "page": 1})
            self.assertEqual(result[0]["score"], 0.9)

            # Check second augmented chunk
            self.assertEqual(result[1]["content"], "Improved text 2")
            self.assertEqual(result[1]["source"], "doc2")
            self.assertEqual(result[1]["metadata"], {"source": "doc2", "page": 1})
            self.assertEqual(result[1]["score"], 0.8)

            # Check that _invoke_litellm was called with correct prompts
            self.assertEqual(self.augmentor._invoke_litellm.call_count, 2)
            prompt1 = self.augmentor._invoke_litellm.call_args_list[0][0][0]
            self.assertIn("test query", prompt1)
            self.assertIn("Original text 1", prompt1)

            prompt2 = self.augmentor._invoke_litellm.call_args_list[1][0][0]
            self.assertIn("test query", prompt2)
            self.assertIn("Original text 2", prompt2)

    def test_augment_chunks_with_llm_no_llm(self):
        """Test _augment_chunks_with_llm method when LLM is not available."""
        # Setup test data
        chunks = [
            {
                "text": "Original text 1",
                "metadata": {"source": "doc1", "page": 1},
                "source": "doc1",
                "score": 0.9,
            },
        ]

        # Create augmentation service without LLM
        config_no_llm = self.config.copy()
        config_no_llm["llm"] = {}  # Empty LLM config
        augmentor_no_llm = AugmentationService(config_no_llm)
        augmentor_no_llm.llm_available = False

        # Call the method
        result = augmentor_no_llm._augment_chunks_with_llm("test query", chunks)

        # Assertions
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "Original text 1")  # Original text used

    def test_augment(self):
        """Test augment method."""
        # Setup mocks
        retrieved_chunks = [
            {
                "text": "Chunk 1 text",
                "metadata": {"source": "doc1", "page": 1},
                "score": 0.9,
            },
            {
                "text": "Chunk 2 text",
                "metadata": {"source": "doc1", "page": 2},
                "score": 0.8,
            },
        ]
        self.mock_retriever_instance.retrieve.return_value = retrieved_chunks

        # Mock the internal methods
        merged_chunks = [
            {
                "text": "Merged text",
                "metadata": {"source": "doc1", "page": 1},
                "source": "doc1",
                "score": 0.9,
            },
        ]
        augmented_chunks = [
            {
                "content": "Augmented content",
                "source": "doc1",
                "metadata": {"source": "doc1", "page": 1},
                "score": 0.9,
            },
        ]

        with patch.object(
            self.augmentor, "_merge_chunks_by_source", return_value=merged_chunks
        ):
            with patch.object(
                self.augmentor,
                "_augment_chunks_with_llm",
                return_value=augmented_chunks,
            ):
                # Call the method
                result = self.augmentor.augment("test query")

                # Assertions
                self.mock_retriever_instance.retrieve.assert_called_once_with(
                    "test query", filter=None
                )
                self.assertEqual(result, augmented_chunks)

    # Remove test_augment_with_metadata as this method doesn't exist in AugmentationService

    # Remove test_augment_multiple as this method doesn't exist in AugmentationService


if __name__ == "__main__":
    unittest.main()
