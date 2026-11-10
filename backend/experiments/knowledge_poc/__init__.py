"""知识库实验命令：真实组件冒烟、检索评测及显式模型问答。"""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import tiktoken
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.bootstrap.services import check_model_references
from app.config import load_config
from app.employees.references import model_employees
from app.infrastructure.credentials import CredentialVault
from app.infrastructure.database.session import Database
from app.knowledge.chunking import split_document
from app.knowledge.contracts import ChunkingRules, TokenCount
from app.llm.config import LLMConfig
from app.llm.factory import model_session
from app.model_connections.service import ModelConnectionService
from app.values import digest
from experiments.knowledge_poc.answering import InvalidAnswerError, answer_question
from experiments.knowledge_poc.contracts import RetrievalPreset, RetrievalResult
from experiments.knowledge_poc.evaluation import evaluate_retrieval, load_dataset
from experiments.knowledge_poc.indexing import Release, build_release, save_json
from experiments.knowledge_poc.retrieval import KnowledgeRetriever, retrieve

DATASET = Path(__file__).resolve().parents[2] / "datasets/travel-expense"


class FixtureEmbeddings(Embeddings):
    """只验证向量存储接线；字符散列不具有语义，不用于向量效果评测。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        values = [0.0] * 16
        for char in text:
            values[hashlib.sha256(char.encode()).digest()[0] % 16] += 1
        return values


class EmbeddingSettings(BaseModel):
    """显式本机配置；Key 仅从指定环境变量读取，不保存到结果。"""

    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1)
    base_url: str = Field(pattern=r"^https://[^\s]+$")
    api_key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    token_encoding: str = Field(min_length=1)
    max_input_tokens: int = Field(gt=0)

    @property
    def space_id(self) -> str:
        return digest(self.model_dump(exclude={"api_key_env"}))


class BoundedEmbeddings(Embeddings):
    def __init__(self, model: Embeddings, count: TokenCount, limit: int):
        self.model, self.count, self.limit = model, count, limit

    def _validate(self, texts: list[str]) -> None:
        if any(self.count(text) > self.limit for text in texts):
            raise ValueError("embedding input exceeds declared token limit")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self._validate(texts)
        return self.model.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        self._validate([text])
        return self.model.embed_query(text)


def token_counter(name: str) -> TokenCount:
    encoding = tiktoken.get_encoding(name)
    return lambda text: len(encoding.encode(text, disallowed_special=()))


def build(
    args: argparse.Namespace,
    embeddings: Embeddings,
    space_id: str,
    count: TokenCount,
    tokenizer: str,
    kind: str,
) -> str:
    documents = load_dataset(args.dataset)
    preset = RetrievalPreset()
    chunks = tuple(
        c
        for d in documents
        for c in split_document(d, ChunkingRules.model_validate(preset.model_dump()), count)
    )
    return build_release(
        args.output.resolve(),
        args.scope,
        documents,
        chunks,
        embeddings,
        space_id=space_id,
        preset=preset,
        tokenizer=tokenizer,
        embedding_kind=kind,
    )


def smoke(args: argparse.Namespace) -> None:
    embeddings = FixtureEmbeddings()
    count = token_counter("cl100k_base")
    id = build(args, embeddings, "fixture-character-hash-v1", count, "cl100k_base", "fixture")
    release = Release(
        args.output.resolve(), args.scope, id, embeddings, "fixture-character-hash-v1"
    )
    result = retrieve(release, "高铁一等座需要什么批准？", "hybrid", RetrievalPreset(), count)
    adapter = KnowledgeRetriever(release=release, preset=RetrievalPreset(), count=count)
    assert adapter.invoke("高铁一等座需要什么批准？")
    rows = evaluate_retrieval(release, args.dataset, "bm25", RetrievalPreset(), count)
    report = {
        "release_id": id,
        "scope_id": args.scope,
        "mode": "component_smoke",
        "embedding_kind": "fixture",
        "semantic_quality_verified": False,
        "documents": len(release.documents),
        "chunks": len(release.chunks),
        "hybrid_evidence_count": len(result.evidence),
        "bm25_dev_cases": rows,
    }
    path = args.output / f"smoke-{id}.json"
    save_json(path, report)
    print(
        json.dumps({k: v for k, v in report.items() if k != "bm25_dev_cases"}, ensure_ascii=False)
    )
    print(f"report: {path}")


def chat_config(connection_id: str) -> LLMConfig:
    app_config = load_config()
    database = Database(app_config.database)
    try:
        service = ModelConnectionService(
            database,
            CredentialVault(app_config.model_encryption_key_file, app_config.model_encryption_key),
            employee_references=model_employees,
            check_references=check_model_references,
        )
        return service.resolve(connection_id)
    finally:
        database.close()


def save_progress(path: Path, rows: list[dict]) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(
            {"review_status": "pending", "planned_count": len(rows), "results": rows},
            stream,
            ensure_ascii=False,
        )
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


async def generate_answers(rows: list[dict], connection_id: str, path: Path) -> None:
    """先保存计划与检索，再逐题调用；失败不从结果总数中消失。"""
    save_progress(path, rows)
    async with model_session(chat_config(connection_id), max_tokens=1000) as chat:
        for row in rows:
            if row["status"] != "retrieved":
                continue
            try:
                result = RetrievalResult.model_validate(row["retrieval"])
                answer, diagnostic = await answer_question(chat, row["question"], result)
                row["answer"] = answer.model_dump(mode="json")
                row["generation"] = diagnostic
                row["status"] = "answered"
            except Exception as error:
                row["status"] = "generation_failed"
                row["error_type"] = type(error).__name__
                if isinstance(error, InvalidAnswerError):
                    row["generation"] = {"raw": error.raw, "usage": error.usage}
            save_progress(path, rows)


async def ask(args: argparse.Namespace) -> None:
    """独立检验 BM25 + 已有聊天连接，不冒充已验证的语义向量。"""
    release = Release(
        args.output.resolve(),
        args.scope,
        args.release,
        FixtureEmbeddings(),
        "fixture-character-hash-v1",
    )
    result = retrieve(
        release, args.question, "bm25", RetrievalPreset(), token_counter("cl100k_base")
    )
    rows = [
        {
            "question": args.question,
            "strategy": "bm25",
            "status": "retrieved",
            "retrieval": result.model_dump(mode="json"),
        }
    ]
    path = args.output / f"answer-{uuid4().hex}.json"
    await generate_answers(rows, args.chat_connection_id, path)
    print(
        json.dumps(
            {"status": rows[0]["status"], "answer": rows[0].get("answer")}, ensure_ascii=False
        )
    )
    print(f"report: {path}")


async def online(args: argparse.Namespace) -> None:
    settings = EmbeddingSettings.model_validate_json(args.embedding_config.read_text())
    secret = os.environ.get(settings.api_key_env)
    if not secret:
        raise ValueError("embedding API key environment variable is not configured")
    count = token_counter(settings.token_encoding)
    with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as transport:
        model = OpenAIEmbeddings(
            model=settings.model_id,
            base_url=settings.base_url,
            api_key=SecretStr(secret),
            max_retries=0,
            check_embedding_ctx_length=False,
            http_client=transport,
        )
        embeddings = BoundedEmbeddings(model, count, settings.max_input_tokens)
        # 明确预检；调用失败不生成一个伪语义发布。
        probe = embeddings.embed_documents(["知识库向量连通测试。", "住宿报销标准。"])
        if len(probe) != 2 or not probe[0]:
            raise ValueError("invalid embedding preflight")
        id = args.release or build(
            args, embeddings, settings.space_id, count, settings.token_encoding, "semantic_api"
        )
        release = Release(args.output.resolve(), args.scope, id, embeddings, settings.space_id)
        rows = []
        for strategy in ("bm25", "vector", "hybrid"):
            rows += evaluate_retrieval(release, args.dataset, strategy, RetrievalPreset(), count)
        path = args.output / f"evaluation-{uuid4().hex}.json"
        if args.chat_connection_id:
            await generate_answers(rows, args.chat_connection_id, path)
        else:
            save_progress(path, rows)
        print(f"report: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("smoke", "evaluate", "ask"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--scope", default="travel-expense-poc")
    parser.add_argument("--embedding-config", type=Path)
    parser.add_argument("--chat-connection-id")
    parser.add_argument("--release")
    parser.add_argument("--question")
    args = parser.parse_args()
    if args.mode == "smoke":
        smoke(args)
    elif args.mode == "ask":
        if not all((args.release, args.chat_connection_id, args.question)):
            parser.error("ask requires --release, --chat-connection-id and --question")
        asyncio.run(ask(args))
    else:
        if not args.embedding_config:
            parser.error("evaluate requires --embedding-config")
        asyncio.run(online(args))


if __name__ == "__main__":
    main()
