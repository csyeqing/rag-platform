from __future__ import annotations

import re
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import RetrievalProfile, RetrievalProfileTypeEnum, User

DEFAULT_RETRIEVAL_PROFILES: list[dict] = [
    {
        'profile_key': 'general_default',
        'name': '通用文档',
        'profile_type': RetrievalProfileTypeEnum.general,
        'description': '适用于多数知识库的均衡检索策略。',
        'is_default': True,
        'config': {
            'rag_min_top1_score': 0.30,
            'rag_min_support_score': 0.18,
            'rag_min_support_count': 2,
            'rag_min_item_score': 0.10,
            'rag_graph_max_terms': 12,
            'graph_channel_weight': 0.65,
            'graph_only_penalty': 0.55,
            'vector_semantic_min': 0.12,
            'alias_intent_enabled': True,
            'alias_mining_max_terms': 8,
            'co_reference_enabled': True,
            'vector_candidate_multiplier': 3,
            'keyword_candidate_multiplier': 3,
            'graph_candidate_multiplier': 4,
            'fallback_relax_enabled': True,
            'fallback_top1_relax': 0.08,
            'fallback_support_relax': 0.06,
            'fallback_item_relax': 0.04,
            'summary_intent_enabled': True,
            'summary_expand_factor': 3,
            'summary_min_chunks': 8,
            'summary_per_file_cap': 2,
            'summary_min_files': 3,
            'keyword_fallback_expand_on_weak_hits': True,
            'keyword_fallback_max_chunks': 240,
            'keyword_fallback_min_score': 0.08,
            'keyword_fallback_scan_limit': 8000,
        },
    },
    {
        'profile_key': 'novel_story_cn',
        'name': '小说/故事',
        'profile_type': RetrievalProfileTypeEnum.novel_story,
        'description': '强化别名和上下文指代，适合人物称呼频繁变化的文本。',
        'config': {
            'rag_min_top1_score': 0.27,
            'rag_min_support_score': 0.16,
            'rag_min_support_count': 2,
            'rag_min_item_score': 0.08,
            'rag_graph_max_terms': 10,
            'graph_channel_weight': 0.60,
            'graph_only_penalty': 0.50,
            'vector_semantic_min': 0.10,
            'alias_intent_enabled': True,
            'alias_mining_max_terms': 10,
            'co_reference_enabled': True,
            'vector_candidate_multiplier': 3,
            'keyword_candidate_multiplier': 3,
            'graph_candidate_multiplier': 4,
            'fallback_relax_enabled': True,
            'fallback_top1_relax': 0.10,
            'fallback_support_relax': 0.07,
            'fallback_item_relax': 0.04,
            'summary_intent_enabled': True,
            'summary_expand_factor': 4,
            'summary_min_chunks': 12,
            'summary_per_file_cap': 3,
            'summary_min_files': 4,
            'keyword_fallback_expand_on_weak_hits': True,
            'keyword_fallback_max_chunks': 280,
            'keyword_fallback_min_score': 0.06,
            'keyword_fallback_scan_limit': 10000,
        },
    },
    {
        'profile_key': 'enterprise_docs',
        'name': '公司资料',
        'profile_type': RetrievalProfileTypeEnum.enterprise_docs,
        'description': '偏精确检索，减少噪声，强调术语与制度条款匹配。',
        'config': {
            'rag_min_top1_score': 0.34,
            'rag_min_support_score': 0.22,
            'rag_min_support_count': 2,
            'rag_min_item_score': 0.12,
            'rag_graph_max_terms': 8,
            'graph_channel_weight': 0.55,
            'graph_only_penalty': 0.48,
            'vector_semantic_min': 0.14,
            'alias_intent_enabled': False,
            'alias_mining_max_terms': 2,
            'co_reference_enabled': False,
            'vector_candidate_multiplier': 3,
            'keyword_candidate_multiplier': 3,
            'graph_candidate_multiplier': 3,
            'fallback_relax_enabled': True,
            'fallback_top1_relax': 0.06,
            'fallback_support_relax': 0.05,
            'fallback_item_relax': 0.03,
            'summary_intent_enabled': True,
            'summary_expand_factor': 2,
            'summary_min_chunks': 8,
            'summary_per_file_cap': 2,
            'summary_min_files': 3,
            'keyword_fallback_expand_on_weak_hits': True,
            'keyword_fallback_max_chunks': 180,
            'keyword_fallback_min_score': 0.10,
            'keyword_fallback_scan_limit': 6000,
        },
    },
    {
        'profile_key': 'scientific_paper',
        'name': '科学论文',
        'profile_type': RetrievalProfileTypeEnum.scientific_paper,
        'description': '强调术语一致性和高置信命中，适用于方法/实验类问答。',
        'config': {
            'rag_min_top1_score': 0.36,
            'rag_min_support_score': 0.24,
            'rag_min_support_count': 2,
            'rag_min_item_score': 0.14,
            'rag_graph_max_terms': 9,
            'graph_channel_weight': 0.58,
            'graph_only_penalty': 0.50,
            'vector_semantic_min': 0.15,
            'alias_intent_enabled': False,
            'alias_mining_max_terms': 1,
            'co_reference_enabled': False,
            'vector_candidate_multiplier': 3,
            'keyword_candidate_multiplier': 3,
            'graph_candidate_multiplier': 4,
            'fallback_relax_enabled': True,
            'fallback_top1_relax': 0.06,
            'fallback_support_relax': 0.05,
            'fallback_item_relax': 0.03,
            'summary_intent_enabled': True,
            'summary_expand_factor': 3,
            'summary_min_chunks': 9,
            'summary_per_file_cap': 2,
            'summary_min_files': 3,
            'keyword_fallback_expand_on_weak_hits': True,
            'keyword_fallback_max_chunks': 180,
            'keyword_fallback_min_score': 0.10,
            'keyword_fallback_scan_limit': 6000,
        },
    },
    {
        'profile_key': 'humanities_research',
        'name': '文科研究论文',
        'profile_type': RetrievalProfileTypeEnum.humanities_paper,
        'description': '适配人物、概念、流派关系，兼顾上下文叙述类问题。',
        'config': {
            'rag_min_top1_score': 0.32,
            'rag_min_support_score': 0.19,
            'rag_min_support_count': 2,
            'rag_min_item_score': 0.10,
            'rag_graph_max_terms': 12,
            'graph_channel_weight': 0.62,
            'graph_only_penalty': 0.52,
            'vector_semantic_min': 0.12,
            'alias_intent_enabled': True,
            'alias_mining_max_terms': 6,
            'co_reference_enabled': True,
            'vector_candidate_multiplier': 3,
            'keyword_candidate_multiplier': 3,
            'graph_candidate_multiplier': 4,
            'fallback_relax_enabled': True,
            'fallback_top1_relax': 0.08,
            'fallback_support_relax': 0.06,
            'fallback_item_relax': 0.04,
            'summary_intent_enabled': True,
            'summary_expand_factor': 4,
            'summary_min_chunks': 10,
            'summary_per_file_cap': 3,
            'summary_min_files': 4,
            'keyword_fallback_expand_on_weak_hits': True,
            'keyword_fallback_max_chunks': 220,
            'keyword_fallback_min_score': 0.08,
            'keyword_fallback_scan_limit': 8000,
        },
    },
]


def build_runtime_retrieval_config(overrides: dict | None, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    base = {
        'rag_min_top1_score': float(settings.rag_min_top1_score),
        'rag_min_support_score': float(settings.rag_min_support_score),
        'rag_min_support_count': int(settings.rag_min_support_count),
        'rag_min_item_score': float(settings.rag_min_item_score),
        'rag_graph_max_terms': int(settings.rag_graph_max_terms),
        'graph_channel_weight': 0.65,
        'graph_only_penalty': 0.55,
        'vector_semantic_min': 0.12,
        'alias_intent_enabled': True,
        'alias_mining_max_terms': 8,
        'co_reference_enabled': True,
        'vector_candidate_multiplier': 3,
        'keyword_candidate_multiplier': 3,
        'graph_candidate_multiplier': 4,
        'fallback_relax_enabled': True,
        'fallback_top1_relax': 0.08,
        'fallback_support_relax': 0.06,
        'fallback_item_relax': 0.04,
        'summary_intent_enabled': True,
        'summary_expand_factor': 3,
        'summary_min_chunks': 8,
        'summary_per_file_cap': 2,
        'summary_min_files': 3,
        'keyword_fallback_expand_on_weak_hits': True,
        'keyword_fallback_max_chunks': 240,
        'keyword_fallback_min_score': 0.08,
        'keyword_fallback_scan_limit': 8000,
    }
    if isinstance(overrides, dict):
        base.update(overrides)

    return {
        'rag_min_top1_score': _as_float(base.get('rag_min_top1_score'), fallback=0.30, lower=0.0, upper=1.5),
        'rag_min_support_score': _as_float(base.get('rag_min_support_score'), fallback=0.18, lower=0.0, upper=1.5),
        'rag_min_support_count': _as_int(base.get('rag_min_support_count'), fallback=2, lower=1, upper=8),
        'rag_min_item_score': _as_float(base.get('rag_min_item_score'), fallback=0.10, lower=0.0, upper=1.5),
        'rag_graph_max_terms': _as_int(base.get('rag_graph_max_terms'), fallback=12, lower=4, upper=40),
        'graph_channel_weight': _as_float(base.get('graph_channel_weight'), fallback=0.65, lower=0.1, upper=1.2),
        'graph_only_penalty': _as_float(base.get('graph_only_penalty'), fallback=0.55, lower=0.1, upper=1.0),
        'vector_semantic_min': _as_float(base.get('vector_semantic_min'), fallback=0.12, lower=0.0, upper=1.0),
        'alias_intent_enabled': bool(base.get('alias_intent_enabled', True)),
        'alias_mining_max_terms': _as_int(base.get('alias_mining_max_terms'), fallback=8, lower=0, upper=24),
        'co_reference_enabled': bool(base.get('co_reference_enabled', True)),
        'vector_candidate_multiplier': _as_int(base.get('vector_candidate_multiplier'), fallback=3, lower=2, upper=20),
        'keyword_candidate_multiplier': _as_int(base.get('keyword_candidate_multiplier'), fallback=3, lower=2, upper=20),
        'graph_candidate_multiplier': _as_int(base.get('graph_candidate_multiplier'), fallback=4, lower=2, upper=24),
        'fallback_relax_enabled': bool(base.get('fallback_relax_enabled', True)),
        'fallback_top1_relax': _as_float(base.get('fallback_top1_relax'), fallback=0.08, lower=0.0, upper=0.30),
        'fallback_support_relax': _as_float(base.get('fallback_support_relax'), fallback=0.06, lower=0.0, upper=0.30),
        'fallback_item_relax': _as_float(base.get('fallback_item_relax'), fallback=0.04, lower=0.0, upper=0.20),
        'summary_intent_enabled': bool(base.get('summary_intent_enabled', True)),
        'summary_expand_factor': _as_int(base.get('summary_expand_factor'), fallback=3, lower=1, upper=8),
        'summary_min_chunks': _as_int(base.get('summary_min_chunks'), fallback=8, lower=4, upper=24),
        'summary_per_file_cap': _as_int(base.get('summary_per_file_cap'), fallback=2, lower=1, upper=6),
        'summary_min_files': _as_int(base.get('summary_min_files'), fallback=3, lower=1, upper=10),
        'keyword_fallback_expand_on_weak_hits': bool(base.get('keyword_fallback_expand_on_weak_hits', True)),
        'keyword_fallback_max_chunks': _as_int(base.get('keyword_fallback_max_chunks'), fallback=240, lower=20, upper=800),
        'keyword_fallback_min_score': _as_float(base.get('keyword_fallback_min_score'), fallback=0.08, lower=0.0, upper=1.5),
        'keyword_fallback_scan_limit': _as_int(base.get('keyword_fallback_scan_limit'), fallback=8000, lower=200, upper=20000),
    }


def list_profiles(db: Session, *, include_inactive: bool = False) -> list[RetrievalProfile]:
    query = db.query(RetrievalProfile)
    if not include_inactive:
        query = query.filter(RetrievalProfile.is_active.is_(True))
    return (
        query.order_by(
            RetrievalProfile.is_default.desc(),
            RetrievalProfile.is_builtin.desc(),
            RetrievalProfile.created_at.asc(),
        ).all()
    )


def get_profile_or_404(db: Session, profile_id: UUID) -> RetrievalProfile:
    profile = db.query(RetrievalProfile).filter(RetrievalProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Retrieval profile not found')
    return profile


def get_default_profile(db: Session) -> RetrievalProfile | None:
    return (
        db.query(RetrievalProfile)
        .filter(RetrievalProfile.is_active.is_(True), RetrievalProfile.is_default.is_(True))
        .order_by(RetrievalProfile.created_at.asc())
        .first()
    )


def get_profile_config_by_id(db: Session, profile_id: UUID | None) -> tuple[UUID | None, dict]:
    profile: RetrievalProfile | None = None
    if profile_id:
        profile = (
            db.query(RetrievalProfile)
            .filter(RetrievalProfile.id == profile_id, RetrievalProfile.is_active.is_(True))
            .first()
        )
    if profile is None:
        profile = get_default_profile(db)
    if profile is None:
        return None, build_runtime_retrieval_config(None)
    return profile.id, build_runtime_retrieval_config(profile.config_json or {})


def create_profile(
    db: Session,
    *,
    current_user: User,
    profile_key: str,
    name: str,
    profile_type: str,
    description: str | None,
    config: dict,
    is_default: bool,
    is_builtin: bool = False,
    is_active: bool = True,
) -> RetrievalProfile:
    key = normalize_profile_key(profile_key)
    exists = db.query(RetrievalProfile).filter(RetrievalProfile.profile_key == key).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='profile_key already exists')

    profile_enum = _parse_profile_type(profile_type)
    normalized_config = build_runtime_retrieval_config(config)
    created = RetrievalProfile(
        profile_key=key,
        name=name.strip(),
        profile_type=profile_enum,
        description=(description or '').strip() or None,
        config_json=normalized_config,
        is_default=bool(is_default),
        is_builtin=bool(is_builtin),
        is_active=bool(is_active),
        created_by=current_user.id,
    )
    db.add(created)
    db.flush()
    if created.is_default:
        _unset_other_defaults(db, keep_id=created.id)
    db.commit()
    db.refresh(created)
    return created


def update_profile(
    db: Session,
    *,
    profile: RetrievalProfile,
    profile_key: str | None = None,
    name: str | None = None,
    profile_type: str | None = None,
    description: str | None = None,
    config: dict | None = None,
    is_default: bool | None = None,
    is_active: bool | None = None,
) -> RetrievalProfile:
    if profile_key is not None:
        key = normalize_profile_key(profile_key)
        key_exists = (
            db.query(RetrievalProfile)
            .filter(RetrievalProfile.profile_key == key, RetrievalProfile.id != profile.id)
            .first()
        )
        if key_exists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='profile_key already exists')
        profile.profile_key = key

    if name is not None:
        profile.name = name.strip()
    if profile_type is not None:
        profile.profile_type = _parse_profile_type(profile_type)
    if description is not None:
        profile.description = description.strip() or None
    if config is not None:
        profile.config_json = build_runtime_retrieval_config(config)
    if is_active is not None:
        profile.is_active = bool(is_active)
    if is_default is not None:
        profile.is_default = bool(is_default)

    db.add(profile)
    db.flush()
    if profile.is_default:
        _unset_other_defaults(db, keep_id=profile.id)
    else:
        has_default = db.query(RetrievalProfile).filter(RetrievalProfile.is_default.is_(True)).first()
        if not has_default:
            profile.is_default = True
            db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def delete_profile(db: Session, profile: RetrievalProfile) -> None:
    if profile.is_builtin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Built-in profile cannot be deleted')
    profile_was_default = profile.is_default
    db.delete(profile)
    db.flush()
    if profile_was_default:
        fallback = (
            db.query(RetrievalProfile)
            .filter(RetrievalProfile.is_active.is_(True))
            .order_by(RetrievalProfile.is_builtin.desc(), RetrievalProfile.created_at.asc())
            .first()
        )
        if fallback:
            fallback.is_default = True
            db.add(fallback)
    db.commit()


def ensure_default_profiles(db: Session) -> None:
    existing = {item.profile_key: item for item in db.query(RetrievalProfile).all()}
    created_any = False
    for item in DEFAULT_RETRIEVAL_PROFILES:
        key = item['profile_key']
        if key in existing:
            continue
        row = RetrievalProfile(
            profile_key=key,
            name=item['name'],
            profile_type=item['profile_type'],
            description=item.get('description'),
            config_json=build_runtime_retrieval_config(item.get('config') or {}),
            is_default=bool(item.get('is_default', False)),
            is_builtin=True,
            is_active=True,
            created_by=None,
        )
        db.add(row)
        created_any = True

    if created_any:
        db.flush()

    has_default = db.query(RetrievalProfile).filter(RetrievalProfile.is_default.is_(True)).first()
    if not has_default:
        fallback = (
            db.query(RetrievalProfile)
            .filter(RetrievalProfile.is_active.is_(True))
            .order_by(RetrievalProfile.is_builtin.desc(), RetrievalProfile.created_at.asc())
            .first()
        )
        if fallback:
            fallback.is_default = True
            db.add(fallback)
    db.commit()


def normalize_profile_key(value: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9_\-]', '_', value.strip().lower())
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    if len(cleaned) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='profile_key is invalid')
    return cleaned[:80]


def _parse_profile_type(value: str) -> RetrievalProfileTypeEnum:
    try:
        return RetrievalProfileTypeEnum(value)
    except ValueError as exc:
        choices = ', '.join(item.value for item in RetrievalProfileTypeEnum)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'profile_type must be one of: {choices}',
        ) from exc


def _unset_other_defaults(db: Session, *, keep_id: UUID) -> None:
    (
        db.query(RetrievalProfile)
        .filter(RetrievalProfile.id != keep_id, RetrievalProfile.is_default.is_(True))
        .update({'is_default': False}, synchronize_session=False)
    )


def _as_float(value: object, *, fallback: float, lower: float, upper: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(lower, min(upper, parsed))


def _as_int(value: object, *, fallback: int, lower: int, upper: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(lower, min(upper, parsed))
