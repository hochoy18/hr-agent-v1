"""
增强文档服务，集成LangChain进行文档处理和向量化：
    面向RAG和pgvector。支持语义切分、强制切分过长 chunk、合并过短 chunk、上传并处理文档、
    生成 chunk embedding、写入 LangChain/pgvector 表、语义搜索和文本 fallback 搜索。
    相比 document_service.py，它更偏知识库问答的文档索引流程
"""
import logging
import os
import hashlib
from pathlib import Path
from typing import List, Optional, Dict, Any, BinaryIO
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, desc, func, text
from sqlalchemy.orm import selectinload

# LangChain imports
from langchain_core.documents import Document as LangChainDocument
from langchain_postgres import PGVector

# Document processing imports
import PyPDF2
from docx import Document as DocxDocument
import tempfile
from datetime import datetime

from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.services.llm_service import LLMService
from app.services.embedding_service import get_embedding_service
from app.schemas.document import DocumentCreate, DocumentUpdate
from app.core.config import settings
from app.utils.text_utils import extract_text_content
from app.services.lightweight_document_service import BaseDocumentService

logger = logging.getLogger(__name__)


class EnhancedDocumentService(BaseDocumentService):
    """增强文档管理服务，集成LangChain功能"""

    def __init__(self, db: AsyncSession):
        super().__init__(db)
        self.llm_service = LLMService()

        # 使用共享嵌入服务避免重复初始化
        self.embedding_service = get_embedding_service()
        self.embeddings = self.embedding_service.get_embeddings()
        self.text_splitter = self.embedding_service.get_text_splitter()

        # PGVector数据库连接字符串（使用psycopg2进行同步连接）
        self.connection_string = settings.DATABASE_URL

        logger.info("增强文档服务已使用共享嵌入服务初始化")

    def _split_by_semantic_points(self, text: str, split_points: List[str]) -> List[str]:
        """根据语义分割点切分文本"""
        chunks = []
        current_pos = 0

        # 按顺序查找每个分割点并切分文本
        for point in split_points:
            pos = text.find(point, current_pos)
            if pos != -1:
                # 添加当前位置到分割点位置的文本块
                if pos > current_pos:
                    chunk = text[current_pos:pos].strip()
                    if chunk:
                        chunks.append(chunk)
                current_pos = pos

        # 添加最后一个文本块
        if current_pos < len(text):
            chunk = text[current_pos:].strip()
            if chunk:
                chunks.append(chunk)

        return chunks

    async def get_semantic_split_points(self, content: str) -> List[str]:
        try:
            # 通过聊天模型生成分割点，仅返回以 `~~` 分隔的分割点字符串
            system_prompt = (
                "你是一个文档结构分析助手。只输出用于 split 的分割点字符串，"
                "用`~~`分隔，不要输出任何其他文字。确保每个分割点在原文中唯一，"
                "如果遇到重复标题或目录项，需要在分割点后追加少量后续字符形成唯一片段。"
            )
            user_prompt = (
                "# 任务\n请分析文档，识别适合作为分割点的文本片段。\n\n"
                "# 规则\n"
                "1) 分割点应位于章节、各级标题、句子或段落的开头；\n"
                "2) 分割后每段尽量保持在500至1000字，严禁>1500字；\n"
                "3) 若存在重复片段（例如目录与正文相同标题），需在分割点后追加少量后续内容以确保唯一；\n"
                "4) 仅输出分割点字符串，使用`~~`分隔，不要解释或添加其他文本。\n\n"
                f"# 文档（截断）\n{content[:10000]}"
            )

            response = await self.llm_service.client.chat.completions.create(
                model=self.llm_service.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=1000,
            )
            raw = response.choices[0].message.content or ""
            points = [p.strip() for p in raw.split("~~") if p.strip()]
            if not points:
                return []

            # 去重并保持顺序
            seen = set()
            unique_points = []
            for p in points:
                if p not in seen:
                    seen.add(p)
                    unique_points.append(p)

            # 保证每个分割点在正文中唯一：必要时追加后续字符
            def ensure_unique(point: str) -> str:
                start = content.find(point)
                if start == -1:
                    return ""  # 模型输出不在原文中，丢弃
                
                # 统计出现次数
                count = 0
                search_pos = 0
                while True:
                    idx = content.find(point, search_pos)
                    if idx == -1:
                        break
                    count += 1
                    search_pos = idx + 1
                
                if count <= 1:
                    return point
                
                # 重复：逐步扩展片段直到唯一或达到限制
                # 最多追加 100 个字符，步长 10
                max_extra = 100
                step = 10
                extra = 0
                while extra <= max_extra:
                    candidate = content[start:start + len(point) + extra]
                    if len(candidate) <= len(point):  # 避免空候选
                        extra += step
                        continue
                    
                    # 重新统计候选字符串的出现次数
                    c = 0
                    sp = 0
                    while True:
                        j = content.find(candidate, sp)
                        if j == -1:
                            break
                        c += 1
                        sp = j + 1
                    
                    if c <= 1:
                        return candidate
                    extra += step
                
                # 仍不唯一则返回原始（极少数情况），后续切分时按位置处理
                return point

            adjusted_points_with_index: List[tuple[int, str]] = []
            for p in unique_points:
                adj = ensure_unique(p)
                if not adj:
                    continue
                idx = content.find(adj)
                if idx != -1:
                    adjusted_points_with_index.append((idx, adj))

            # 按在正文中的出现位置排序
            adjusted_points_with_index.sort(key=lambda x: x[0])
            final_points = [pt for _, pt in adjusted_points_with_index]
            return final_points
        except Exception as e:
            logger.error(f"增强文档服务获取语义分割点时出错: {e}")
            return []

    def _force_split_long_chunk(self, chunk: str) -> List[str]:
        """强制分割超长段落（超过1500字符）"""
        max_length = 1500
        chunks = []

        # 先尝试按换行符分割
        if '\n' in chunk:
            lines = chunk.split('\n')
            current_chunk = ""
            for line in lines:
                if len(current_chunk) + len(line) + 1 > max_length:
                    if current_chunk:
                        chunks.append(current_chunk)
                        current_chunk = line
                    else:
                        # 单行就超过最大长度，需要递归分割
                        line_chunks = self._force_split_long_chunk(line)
                        chunks.extend(line_chunks)
                        current_chunk = ""
                else:
                    if current_chunk:
                        current_chunk += "\n" + line
                    else:
                        current_chunk = line
            if current_chunk:
                chunks.append(current_chunk)
        else:
            # 没有换行符则直接按长度分割
            chunks = [chunk[i:i + max_length] for i in range(0, len(chunk), max_length)]

        return chunks

    def _merge_short_chunks(self, chunks: List[str], min_length: int = 200, max_length: int = 1500) -> List[str]:
        """合并过短片段，避免产生极短段落，同时不超过最大长度"""
        if not chunks:
            return []
        merged: List[str] = []
        i = 0
        while i < len(chunks):
            cur = chunks[i]
            
            # 如果当前片段过短且不是最后一个，尝试合并
            if len(cur) < min_length and i + 1 < len(chunks):
                # 尝试合并多个连续的短片段
                merged_chunk = cur
                j = i + 1
                
                while j < len(chunks) and len(merged_chunk) < min_length:
                    nxt = chunks[j]
                    # 添加适当的分隔符
                    separator = "\n" if not merged_chunk.endswith("\n") else ""
                    potential_chunk = merged_chunk + separator + nxt
                    
                    if len(potential_chunk) <= max_length:
                        merged_chunk = potential_chunk
                        j += 1
                    else:
                        break
                
                # 如果成功合并了至少一个片段
                if j > i + 1:
                    merged.append(merged_chunk)
                    i = j
                    continue
                else:
                    # 只合并下一个片段
                    nxt = chunks[i + 1]
                    if len(cur) + len(nxt) + 1 <= max_length:
                        separator = "\n" if not cur.endswith("\n") else ""
                        merged.append(cur + separator + nxt)
                        i += 2
                        continue
            
            merged.append(cur)
            i += 1
        return merged

    async def _split_text(self, content: str) -> List[str]:
        """主分割流程：使用 LLM 分割点 + 切分 + 长度约束"""
        # 1) 获取分割点（可能为空）
        points = await self.get_semantic_split_points(content)
        # 2) 根据分割点切分；若为空则整体作为一个片段
        if points:
            chunks = self._split_by_semantic_points(content, points)
        else:
            chunks = [content]
        # 3) 对超长片段进行强制分割（>1500）
        normalized: List[str] = []
        for ch in chunks:
            if len(ch) > 1500:
                normalized.extend(self._force_split_long_chunk(ch))
            else:
                normalized.append(ch)
        # 4) 合并过短片段（<200）
        normalized = self._merge_short_chunks(normalized, min_length=200, max_length=1500)
        # 5) 去除空白
        normalized = [c.strip() for c in normalized if c and c.strip()]
        return normalized

    async def upload_document(
        self,
        file,  # 上传文档对象
        user_id: UUID,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        knowledge_base_id: Optional[str] = None
    ) -> Document:
        """上传并处理文档"""
        # 如果提供，将knowledge_base_id从字符串转换为UUID
        kb_id = None
        if knowledge_base_id:
            try:
                kb_id = UUID(knowledge_base_id)
            except (ValueError, TypeError):
                logger.warning(f"无效的知识库ID格式: {knowledge_base_id}")
                kb_id = None

        return await self.upload_and_process_document(
            file=file.file,
            filename=file.filename,
            user_id=user_id,
            knowledge_base_id=kb_id,
            category=category,
            tags=tags
        )

    async def upload_and_process_document(
        self,
        file: BinaryIO,
        filename: str,
        user_id: UUID,
        knowledge_base_id: Optional[UUID] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Document:
        """上传文档并在同一请求中完成解析、分块和向量化。"""
        saved_file_path: Optional[str] = None
        added_vector_ids: List[str] = []
        old_vector_ids: List[str] = []
        try:
            file_content = file.read()
            file.seek(0)
            if not file_content:
                raise ValueError("上传文件内容为空")

            file_hash = hashlib.sha256(file_content).hexdigest()
            existing_doc = await self._get_document_by_hash(
                file_hash,
                user_id,
                knowledge_base_id,
            )
            if existing_doc and existing_doc.processing_status == "completed":
                existing_path = self._resolve_file_path(existing_doc.file_path)
                if existing_path.exists():
                    logger.info(f"哈希为 {file_hash} 的文档在当前知识库中已完成处理")
                    return existing_doc

            mime_type = self._get_mime_type(filename)
            if existing_doc:
                document = existing_doc
                document.processing_status = "processing"
                document.processing_error = None
                if not self._resolve_file_path(document.file_path).exists():
                    saved_file_path = await self._save_file(file_content, filename, user_id)
                    document.file_path = saved_file_path
            else:
                saved_file_path = await self._save_file(file_content, filename, user_id)
                document = Document(
                    filename=filename,
                    original_filename=filename,
                    file_path=saved_file_path,
                    file_size=len(file_content),
                    file_hash=file_hash,
                    mime_type=mime_type,
                    extracted_content=None,
                    embedding=None,
                    category=category,
                    tags=tags,
                    user_id=user_id,
                    knowledge_base_id=knowledge_base_id,
                    processing_status="processing",
                    processing_error=None,
                    chunk_count=0,
                )
                self.db.add(document)

            await self.db.flush()
            if existing_doc:
                old_vector_ids = await self._get_document_vector_ids(document.id)
            extracted_content = await extract_text_content(document.file_path, document.mime_type)
            if not extracted_content or not extracted_content.strip():
                raise ValueError("文档未能解析出有效文本内容")
            document.extracted_content = extracted_content.strip()
            added_vector_ids = await self._create_document_chunks_with_pgvector(document, document.extracted_content)
            if not added_vector_ids:
                raise ValueError("文档未生成有效向量分块")

            document.processing_status = "completed"
            document.processing_error = None
            document.processed_at = datetime.utcnow()
            document.chunk_count = len(added_vector_ids)
            await self.db.commit()
            if old_vector_ids:
                try:
                    self._delete_vector_ids(user_id, old_vector_ids)
                except Exception as cleanup_error:
                    logger.warning("文档 %s 旧向量延迟清理失败: %s", document.id, cleanup_error)
            await self.db.refresh(document)
            logger.info(f"文档上传与索引完成: {document.id}")
            return document

        except Exception as e:
            logger.error(f"上传并处理文档时出错: {e}")
            await self.db.rollback()
            if added_vector_ids:
                self._delete_vector_ids(user_id, added_vector_ids)
            if saved_file_path:
                failed_path = self._resolve_file_path(saved_file_path)
                if failed_path.exists():
                    failed_path.unlink()
            raise

    async def _get_document_vector_ids(self, document_id: UUID) -> List[str]:
        result = await self.db.execute(text("""
            SELECT id
            FROM langchain_pg_embedding
            WHERE cmetadata->>'document_id' = :document_id
        """), {"document_id": str(document_id)})
        return [str(row.id) for row in result.fetchall()]

    async def _create_document_chunks_with_pgvector(self, document: Document, content: str) -> List[str]:
        """使用PGVector为嵌入向量创建文档块"""
        # text_chunks = self.get_semantic_split_points(content)
        text_chunks = await self._split_text(content)
        if not text_chunks:
            logger.warning(f"未为文档 {document.id} 提供文本块")
            return []

        # 创建带有元数据的LangChain文档（内容块）
        chunks_collection = f"document_chunks_{document.user_id}".replace("-", "_")
        
        langchain_docs = []
        for i, chunk_text in enumerate(text_chunks):
            # 直接在创建时包含所有必要的元数据
            doc = LangChainDocument(
                page_content=chunk_text,
                metadata={
                    "document_id": str(document.id),
                    "knowledge_base_id": str(document.knowledge_base_id),
                    "chunk_index": i,
                    "chunk_size": len(chunk_text),
                    "filename": document.filename,
                    "category": document.category or "general",
                    "file_path": document.file_path,
                    "mime_type": document.mime_type,
                    "source_type": "content",
                    "collection_name": chunks_collection
                }
            )
            langchain_docs.append(doc)

        # 获取向量存储
        vector_store = PGVector(
            connection=self.connection_string,
            embeddings=self.embeddings,
            collection_name=chunks_collection,
            use_jsonb=True
        )

        logger.info(
            f"正在向PGVector集合 {chunks_collection} 添加 {len(langchain_docs)} 个文档块"
        )

        # 将文档添加到向量存储（同步操作）
        try:
            added_ids = [str(item) for item in vector_store.add_documents(langchain_docs)]
            logger.info(
                f"成功向PGVector集合 {chunks_collection} 添加了 {len(langchain_docs)} 个文档块"
            )
            logger.info(
                f"为文档 {document.id} 创建了 {len(text_chunks)} 个块"
            )
            return added_ids
        except Exception as e:
            logger.error(f"向PGVector添加文档时出错: {e}")
            # 不在这里处理数据库事务，让调用方处理
            raise

    def _delete_vector_ids(self, user_id: UUID, vector_ids: List[str]) -> None:
        """删除本次处理写入的向量，用于数据库事务失败时的补偿回滚。"""
        if not vector_ids:
            return
        collection_name = f"document_chunks_{user_id}".replace("-", "_")
        vector_store = PGVector(
            connection=self.connection_string,
            embeddings=self.embeddings,
            collection_name=collection_name,
            use_jsonb=True,
        )
        vector_store.delete(ids=vector_ids)

    async def semantic_search(
        self,
        query: str,
        user_id: UUID,
        limit: int = 10,
        knowledge_base_id: Optional[UUID] = None,
        category: Optional[str] = None,
        similarity_threshold: float = 0.8
    ) -> List[Dict[str, Any]]:
        """使用PGVector执行语义搜索"""
        try:
            collection_name = f"document_chunks_{user_id}".replace("-", "_")

            vector_store = PGVector(
                connection=self.connection_string,
                embeddings=self.embeddings,
                collection_name=collection_name,
                use_jsonb=True
            )

            filter_conditions = {}
            if knowledge_base_id:
                filter_conditions["knowledge_base_id"] = str(knowledge_base_id)
            if category:
                filter_conditions["category"] = category

            results = vector_store.similarity_search_with_score(
                query=query,
                k=limit,
                filter=filter_conditions if filter_conditions else None
            )
            
            # 格式化结果
            search_results = []
            for doc, score in results:
                if score <= similarity_threshold:
                    search_results.append({
                        "document_id": doc.metadata.get("document_id"),
                        "filename": doc.metadata.get("filename"),
                        "content": doc.page_content,
                        "chunk_index": doc.metadata.get("chunk_index"),
                        "category": doc.metadata.get("category"),
                        "similarity": float(score),
                        "metadata": doc.metadata
                    })
            
            return search_results
            
        except Exception as e:
            logger.error(f"语义搜索时出错: {e}")
            # 回退到文本搜索
            return await self._fallback_text_search(query, user_id, limit, knowledge_base_id, category)

    async def _fallback_text_search(
        self,
        query: str,
        user_id: UUID,
        limit: int,
        knowledge_base_id: Optional[UUID] = None,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """向量搜索失败时的回退文本搜索"""
        try:
            base_query = select(Document).where(Document.user_id == user_id)
            
            if knowledge_base_id:
                base_query = base_query.where(Document.knowledge_base_id == knowledge_base_id)
            
            if category:
                base_query = base_query.where(Document.category == category)
            
            # 简单文本搜索
            text_query = base_query.where(
                Document.extracted_content.ilike(f"%{query}%")
            ).limit(limit)
            
            result = await self.db.execute(text_query)
            documents = result.scalars().all()
            
            # 格式化结果
            search_results = []
            for doc in documents:
                search_results.append({
                    "document_id": str(doc.id),
                    "filename": doc.filename,
                    "content": doc.extracted_content[:500] if doc.extracted_content else "",
                    "category": doc.category,
                    "similarity": 0.5,  # 文本搜索的默认相似度
                    "created_at": doc.created_at.isoformat()
                })
            
            return search_results
            
        except Exception as e:
            logger.error(f"回退文本搜索时出错: {e}")
            return []

    async def get_user_documents(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 100,
        category: Optional[str] = None,
        knowledge_base_id: Optional[UUID] = None
    ) -> List[Document]:
        """获取用户文档，支持可选过滤"""
        try:
            query = select(Document).where(Document.user_id == user_id)
            
            if category:
                query = query.where(Document.category == category)
            
            if knowledge_base_id:
                query = query.where(Document.knowledge_base_id == knowledge_base_id)
            
            query = query.offset(skip).limit(limit).order_by(desc(Document.created_at))
            
            result = await self.db.execute(query)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"获取用户文档时出错: {e}")
            raise

    async def get_by_id(self, document_id: str, user_id: Optional[UUID] = None) -> Optional[Document]:
        """根据ID获取文档，可选择验证用户权限"""
        try:
            # 将字符串ID转换为UUID
            doc_uuid = UUID(document_id)
            
            # 构建查询
            query = select(Document).where(Document.id == doc_uuid)
            if user_id:
                query = query.where(Document.user_id == user_id)
            
            result = await self.db.execute(query)
            document = result.scalar_one_or_none()
            
            # 添加日志记录文档状态
            if document:
                content_length = len(document.extracted_content) if document.extracted_content else 0
                logger.info(f"找到文档 {document_id}，内容长度: {content_length}")
            else:
                if user_id:
                    logger.warning(f"为用户 {user_id} 未找到文档 {document_id}")
                else:
                    logger.warning(f"未找到文档 {document_id}")

            return document

        except (ValueError, TypeError) as e:
            logger.error(f"无效的文档ID格式 {document_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"获取文档 {document_id} 时出错: {e}")
            return None

    async def get_document_chunks(self, document_id: str, user_id: UUID) -> List[Dict[str, Any]]:
        """从langchain_pg_embedding表获取文档块用于预览"""
        try:
            # 首先检查文档是否存在且用户有权限
            document = await self.get_by_id(document_id)
            if not document:
                raise ValueError("文档未找到")
            
            if document.user_id != user_id:
                raise ValueError("权限被拒绝")
            
            # 直接查询langchain_pg_embedding表
            query = text("""
                SELECT 
                    id,
                    document,
                    cmetadata
                FROM langchain_pg_embedding 
                WHERE cmetadata->>'document_id' = :document_id
                ORDER BY CAST(cmetadata->>'chunk_index' AS INTEGER)
            """)
            
            result = await self.db.execute(query, {"document_id": str(document_id)})
            rows = result.fetchall()
            
            # 格式化块用于响应
            formatted_chunks = []
            for row in rows:
                metadata = row.cmetadata if row.cmetadata else {}
                formatted_chunks.append({
                    "id": str(row.id),
                    "content": row.document,
                    "chunk_index": metadata.get("chunk_index", 0),
                    "chunk_size": metadata.get("chunk_size", len(row.document) if row.document else 0),
                    "metadata": metadata
                })
            return formatted_chunks
            
        except Exception as e:
            logger.error(f"获取文档块时出错: {e}")
            raise

    async def delete(self, document: Document) -> None:
        """从langchain_pg_embedding删除文档及其块"""
        try:
            # 从langchain_pg_embedding表删除文档块
            delete_query = text("""
                DELETE FROM langchain_pg_embedding 
                WHERE cmetadata->>'document_id' = :document_id
            """)
            await self.db.execute(delete_query, {"document_id": str(document.id)})
            
            # 删除文档
            await self.db.delete(document)
            await self.db.commit()
            
            # 如果文件存在则清理
            if document.file_path:
                document_path = self._resolve_file_path(document.file_path)
                if document_path.exists():
                    document_path.unlink()
                
            logger.info(f"已删除文档 {document.id} 及其嵌入向量")
            
        except Exception as e:
            logger.error(f"删除文档时出错: {e}")
            await self.db.rollback()
            raise

    async def _get_document_by_hash(
        self,
        file_hash: str,
        user_id: UUID,
        knowledge_base_id: Optional[UUID] = None,
    ) -> Optional[Document]:
        """根据用户、知识库和文件哈希获取文档。"""
        query = select(Document).where(
            Document.file_hash == file_hash,
            Document.user_id == user_id
        )
        if knowledge_base_id:
            query = query.where(Document.knowledge_base_id == knowledge_base_id)
        else:
            query = query.where(Document.knowledge_base_id.is_(None))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    def _resolve_file_path(self, file_path: str) -> Path:
        path = Path(file_path)
        if path.is_absolute():
            return path
        backend_root = Path(__file__).resolve().parents[2]
        return (backend_root / path).resolve()

    def _get_mime_type(self, filename: str) -> str:
        """根据文件名确定MIME类型"""
        extension = filename.lower().split('.')[-1] if '.' in filename else ''
        mime_types = {
            'pdf': 'application/pdf',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'txt': 'text/plain',
            'md': 'text/markdown',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'xls': 'application/vnd.ms-excel'
        }
        return mime_types.get(extension, 'application/octet-stream')

    async def _save_temp_file(self, content: bytes, filename: str) -> str:
        """临时保存文件以进行处理"""
        temp_dir = tempfile.gettempdir()
        safe_filename = Path(filename).name
        temp_file_path = os.path.join(temp_dir, f"temp_{safe_filename}")
        
        with open(temp_file_path, 'wb') as f:
            f.write(content)
        
        return temp_file_path

    async def _save_file(self, content: bytes, filename: str, user_id: UUID) -> str:
        """永久保存文件"""
        # 创建用户特定的上传目录
        configured_upload_dir = Path(settings.UPLOAD_DIR)
        if not configured_upload_dir.is_absolute():
            configured_upload_dir = Path(__file__).resolve().parents[2] / configured_upload_dir
        upload_dir = configured_upload_dir.resolve() / str(user_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_filename = Path(filename).name
        
        # 生成唯一文件名
        file_path = upload_dir / safe_filename
        counter = 1
        base_name, extension = os.path.splitext(safe_filename)
        
        while file_path.exists():
            new_filename = f"{base_name}_{counter}{extension}"
            file_path = upload_dir / new_filename
            counter += 1
        
        # 保存文件
        with file_path.open('wb') as f:
            f.write(content)
        
        return str(file_path)

    
