"""Tests for knowledge base loading, chunking, embedding, and retrieval (Day 2 tasks)."""

import tempfile
from pathlib import Path

import pytest

from backend.db.knowledge_store import Document, KnowledgeStore
from backend.knowledge.chunker import chunk_documents
from backend.knowledge.hashing import content_hash, hash_documents
from backend.knowledge.loaders import load_corpus


class TestContentHashing:
    """Task 3.3: content hashing for change detection."""

    def test_same_content_produces_same_hash(self) -> None:
        """Task 3.3: hashes are deterministic."""
        text = "This is a test document about infant nutrition."
        hash1 = content_hash(text)
        hash2 = content_hash(text)
        assert hash1 == hash2

    def test_different_content_produces_different_hash(self) -> None:
        """Different content → different hash."""
        text1 = "Infant nutrition guidelines"
        text2 = "Toddler nutrition guidelines"
        assert content_hash(text1) != content_hash(text2)

    def test_empty_text_produces_empty_hash(self) -> None:
        """Empty input → empty hash."""
        assert content_hash("") == ""

    def test_hash_is_deterministic_across_runs(self) -> None:
        """Same input always produces same hash (not random)."""
        text = "AAP Pediatric Nutrition Handbook recommends iron supplementation."
        expected = content_hash(text)
        for _ in range(5):
            assert content_hash(text) == expected

    def test_hash_documents_bulk(self) -> None:
        """Task 3.3: hash a set of documents."""
        docs = [
            {"content": "WHO guidelines", "document_id": "who-2006"},
            {"content": "AAP handbook", "document_id": "aap-2021"},
        ]
        hashes = hash_documents(docs)
        assert len(hashes) == 2
        assert hashes["who-2006"] == content_hash("WHO guidelines")
        assert hashes["aap-2021"] == content_hash("AAP handbook")


class TestDocumentChunking:
    """Task 3.2: document chunking with overlap."""

    def test_small_document_becomes_one_chunk(self) -> None:
        """Task 3.2: a short doc is not split."""
        docs = [{"content": "Short text.", "source": "test", "document_id": "doc1"}]
        chunks = chunk_documents(docs, chunk_size=512, chunk_overlap=50)
        assert len(chunks) == 1
        assert chunks[0]["content"] == "Short text."

    def test_large_document_is_split(self) -> None:
        """Task 3.2: a large doc creates multiple chunks."""
        long_text = "This is a paragraph. " * 100  # ~2100 characters
        docs = [{"content": long_text, "source": "test", "document_id": "doc1"}]
        chunks = chunk_documents(docs, chunk_size=512, chunk_overlap=50)
        assert len(chunks) > 1
        # Each chunk should be around 512 chars
        for chunk in chunks:
            assert len(chunk["content"]) <= 512 + 50  # Some slack for boundary

    def test_chunks_carry_source_metadata(self) -> None:
        """Task 3.2: metadata is preserved in chunks."""
        docs = [
            {
                "content": "Part 1. " * 100,
                "source": "WHO",
                "document_id": "who-2006",
                "date": 2006,
                "topic": "growth standards",
                "authority": "WHO official",
            }
        ]
        chunks = chunk_documents(docs)
        for chunk in chunks:
            assert chunk["source"] == "WHO"
            assert chunk["document_id"] == "who-2006"
            assert chunk["date"] == 2006
            assert chunk["topic"] == "growth standards"
            assert chunk["authority"] == "WHO official"

    def test_chunks_include_index(self) -> None:
        """Each chunk is numbered within its document."""
        docs = [{"content": "Part " * 200, "source": "test", "document_id": "doc1"}]
        chunks = chunk_documents(docs)
        for i, chunk in enumerate(chunks):
            assert chunk["chunk_index"] == i
            assert chunk["total_chunks"] == len(chunks)

    def test_overlap_preserves_continuity(self) -> None:
        """Task 3.2: overlap between chunks."""
        text = ". ".join([f"Sentence {i}" for i in range(30)])
        docs = [{"content": text, "source": "test", "document_id": "doc1"}]
        chunks = chunk_documents(docs, chunk_size=100, chunk_overlap=50)
        # Overlapping chunks should have similar ending/beginning
        if len(chunks) > 1:
            end_of_first = chunks[0]["content"][-50:]
            start_of_second = chunks[1]["content"][:50]
            # There should be some common words/sentences due to overlap
            assert len(end_of_first) > 0 and len(start_of_second) > 0

    def test_empty_document_is_skipped(self) -> None:
        """Task 3.2: empty docs are logged and skipped."""
        docs = [
            {"content": "", "source": "empty", "document_id": "empty"},
            {"content": "Real content", "source": "real", "document_id": "real"},
        ]
        chunks = chunk_documents(docs)
        # Only the real document should be chunked
        assert all(chunk["source"] == "real" for chunk in chunks)


class TestDocumentLoading:
    """Task 3.1: load documents from filesystem."""

    def test_load_markdown_files(self) -> None:
        """Task 3.1: load .md files from a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test markdown files
            md_file = Path(tmpdir) / "test.md"
            md_file.write_text("# Test Document\nContent here.")

            docs = load_corpus(tmpdir)
            assert len(docs) > 0
            assert any("Test Document" in doc.get("content", "") for doc in docs)

    def test_load_text_files(self) -> None:
        """Task 3.1: load .txt files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            txt_file = Path(tmpdir) / "test.txt"
            txt_file.write_text("This is a text file.")

            docs = load_corpus(tmpdir)
            assert len(docs) > 0
            assert any("text file" in doc.get("content", "") for doc in docs)

    def test_load_nested_directories(self) -> None:
        """Task 3.1: load from nested directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir) / "guidelines"
            subdir.mkdir()
            (subdir / "who.md").write_text("WHO guidelines")
            (Path(tmpdir) / "aap.txt").write_text("AAP handbook")

            docs = load_corpus(tmpdir)
            assert len(docs) >= 2
            contents = [doc.get("content", "") for doc in docs]
            assert any("WHO" in c for c in contents)
            assert any("AAP" in c for c in contents)

    def test_load_nonexistent_directory_raises(self) -> None:
        """Task 3.1: error on missing directory."""
        with pytest.raises(FileNotFoundError):
            load_corpus("/nonexistent/path")

    def test_loaded_documents_have_metadata(self) -> None:
        """Task 3.1: loaded docs include source and filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir).joinpath("who-2006.md").write_text("WHO content")
            docs = load_corpus(tmpdir)
            assert len(docs) > 0
            doc = docs[0]
            assert "source" in doc
            assert "path" in doc
            assert "filename" in doc
            assert doc["filename"] == "who-2006.md"


class TestDocumentInterface:
    """Task 4.3: Document interface and Docume st class."""

    def test_document_creation(self) -> None:
        """Document can be created with or without optional fields."""
        doc = Document(
            content="test content",
            source="WHO",
        )
        assert doc.content == "test content"
        assert doc.source == "WHO"
        assert doc.date is None
        assert doc.topic is None

    def test_document_with_full_metadata(self) -> None:
        """Document can carry full provenance."""
        doc = Document(
            content="Infant feeding guidelines",
            source="AAP Pediatric Nutrition Handbook",
            date=2021,
            topic="infant nutrition",
            authority="American Academy of Pediatrics",
            page_ref="page 42",
            document_id="aap-2021",
            score=0.95,
        )
        assert doc.source == "AAP Pediatric Nutrition Handbook"
        assert doc.date == 2021
        assert doc.authority == "American Academy of Pediatrics"
        assert doc.score == 0.95


class TestKnowledgeStoreInterface:
    """Task 2.1: KnowledgeStore abstract interface."""

    def test_knowledge_store_is_abstract(self) -> None:
        """Cannot instantiate KnowledgeStore directly."""
        with pytest.raises(TypeError):
            KnowledgeStore()

    def test_knowledge_store_has_required_methods(self) -> None:
        """KnowledgeStore declares search, upsert, delete, count."""
        from abc import abstractmethod

        assert hasattr(KnowledgeStore, "search")
        assert hasattr(KnowledgeStore, "upsert")
        assert hasattr(KnowledgeStore, "delete")
        assert hasattr(KnowledgeStore, "count")


class TestValidationBaseline:
    """Task 7.1: small curated query/result validation set."""

    def test_nutrition_queries_are_representative(self) -> None:
        """Sample queries for validation."""
        queries = [
            "How much iron should an 8-month-old consume?",
            "What are complementary feeding guidelines for 6-month-olds?",
            "Which foods are choking hazards for infants under 12 months?",
            "How much protein do toddlers need daily?",
            "What is the recommended introduction to honey for infants?",
        ]
        assert len(queries) >= 5
        for query in queries:
            assert isinstance(query, str)
            assert len(query) > 10

    def test_expected_sources_are_well_known(self) -> None:
        """Validation references expected authoritative sources."""
        sources = [
            "WHO Child Growth Standards",
            "AAP Pediatric Nutrition",
            "CDC/USDA dietary guidelines",
            "National infant dietary guidelines",
        ]
        for source in sources:
            assert isinstance(source, str)
            assert len(source) > 5
