"""
Sanctions screening service.

Data source: OpenSanctions (https://www.opensanctions.org)
  - Free bulk downloads, CC-BY 4.0
  - Default: default dataset (sanctions + PEPs + watchlists)
    https://data.opensanctions.org/datasets/latest/default/entities.ftm.json

Design:
  - Download once, parse, bulk-insert into sanctions_entities
  - screen(name, country, ...) uses rapidfuzz token-set + partial matching
  - Every screen logged to sanctions_screens with hits in sanctions_hits
  - Thresholds configurable via env
"""
import os
import io
import json
import time
import threading
import requests
from datetime import datetime
from rapidfuzz import fuzz

from app import db
from app.models.sanctions import (
    SanctionsEntity, SanctionsScreen, SanctionsHit,
    SanctionsStatus, SanctionsListType,
)


DATA_URL = os.getenv(
    'SANCTIONS_DATA_URL',
    'https://data.opensanctions.org/datasets/latest/default/entities.ftm.json'
)
HTTP_TIMEOUT = int(os.getenv('SANCTIONS_HTTP_TIMEOUT', '120'))
# Score thresholds (0..100 from rapidfuzz, we store 0..1)
THRESHOLD_REVIEW = float(os.getenv('SANCTIONS_THRESHOLD_REVIEW', '0.88'))
THRESHOLD_STRONG = float(os.getenv('SANCTIONS_THRESHOLD_STRONG', '0.95'))
MAX_HITS_PER_SCREEN = int(os.getenv('SANCTIONS_MAX_HITS', '10'))


# ----------------------------------------------------------------- download
def _topic_list(topics):
    if not topics:
        return []
    if isinstance(topics, list):
        return [str(t) for t in topics]
    return [str(topics)]


def _list_type_from_topics(topics):
    t = ' '.join(_topic_list(topics)).lower()
    if 'sanction' in t:
        return SanctionsListType.SANCTIONS
    if 'role.pep' in t or 'pep' in t:
        return SanctionsListType.PEP
    if 'crime' in t or 'wanted' in t:
        return SanctionsListType.WATCHLIST
    return SanctionsListType.OTHER


def _entity_from_ftm(record: dict):
    """Convert one FollowTheMoney entity dict into a SanctionsEntity row."""
    props = record.get('properties') or {}
    schema = record.get('schema') or ''
    # OpenSanctions uses schema 'Person', 'Company', 'Organization', etc.

    # Primary name
    names = props.get('name') or []
    if not names:
        return None
    name = str(names[0])[:400]
    if not name:
        return None

    # Aliases (including other names)
    aliases = [str(a) for a in (props.get('alias') or [])]
    extra_names = [str(a) for a in names[1:]]
    all_alt = aliases + extra_names

    # Countries
    countries = props.get('country') or []
    countries_str = ','.join(str(c) for c in countries)[:200]

    # Birth date
    birth = props.get('birthDate') or []
    birth_str = str(birth[0])[:40] if birth else None

    # Datasets
    datasets = record.get('datasets') or []
    topics = record.get('properties', {}).get('topics') or []
    # topics is often under properties.topics or record.properties.topics
    topics_str = ','.join(_topic_list(topics))[:400]

    name_lower = name.lower()
    aliases_lower = ' | '.join(a.lower() for a in all_alt)[:2000]

    return SanctionsEntity(
        opensanctions_id=str(record.get('id') or '')[:80] or None,
        schema=schema[:40] or None,
        name=name,
        name_lower=name_lower,
        aliases=json.dumps(all_alt) if all_alt else None,
        aliases_lower=aliases_lower or None,
        countries=countries_str or None,
        birth_date=birth_str,
        datasets=json.dumps(datasets) if datasets else None,
        list_type=_list_type_from_topics(topics),
        topics=topics_str or None,
    )


def download_and_load(progress_cb=None, limit=None):
    """
    Download OpenSanctions FTM JSON stream, parse, insert into DB.
    Truncates sanctions_entities first (full reload).
    `limit` is useful for testing — only import N records.
    """
    from app import create_app
    app = create_app()

    headers = {'User-Agent': 'AflathoonExchange/1.0 (+https://aflathoon.local)'}
    r = requests.get(DATA_URL, headers=headers, stream=True, timeout=HTTP_TIMEOUT)
    r.raise_for_status()

    with app.app_context():
        SanctionsEntity.query.delete()
        db.session.commit()

        count = 0
        batch = []
        batch_size = 500

        for line in r.iter_lines():
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ent = _entity_from_ftm(rec)
            if not ent:
                continue
            batch.append(ent)
            count += 1

            if len(batch) >= batch_size:
                db.session.add_all(batch)
                db.session.commit()
                batch = []
                if progress_cb:
                    progress_cb(count)

            if limit and count >= limit:
                break

        if batch:
            db.session.add_all(batch)
            db.session.commit()

        if progress_cb:
            progress_cb(count, done=True)
        return count


# ----------------------------------------------------------------- screen
def _candidate_entities(name_lower, country=None, limit=5000):
    """
    Narrow the entity list before fuzzy matching.
    Uses SQL LIKE on the first significant token + optional country filter.
    Falls back to nothing if the name is too short.
    """
    tokens = [t for t in name_lower.split() if len(t) >= 3]
    if not tokens:
        return []
    # Prefer the longest token for the LIKE filter
    longest = max(tokens, key=len)
    q = SanctionsEntity.query.filter(SanctionsEntity.name_lower.like(f'%{longest}%'))
    if country:
        country_up = country.upper()
        q = q.filter(SanctionsEntity.countries.like(f'%{country_up}%'))
    return q.limit(limit).all()


def _fuzzy_match(subject_lower, entity):
    """Return (score_0_to_1, matched_name, reason)."""
    # Token-set ratio is good for reordered names
    s1 = fuzz.token_set_ratio(subject_lower, entity.name_lower) / 100.0
    # Partial ratio catches substring matches
    s2 = fuzz.partial_ratio(subject_lower, entity.name_lower) / 100.0
    best = max(s1, s2)
    reason = 'fuzzy_name'

    # Try aliases too
    if entity.aliases_lower:
        for alias in entity.aliases_lower.split(' | '):
            a = alias.strip()
            if not a:
                continue
            sa1 = fuzz.token_set_ratio(subject_lower, a) / 100.0
            sa2 = fuzz.partial_ratio(subject_lower, a) / 100.0
            sa = max(sa1, sa2)
            if sa > best:
                best = sa
                reason = 'fuzzy_alias'

    return best, entity.name, reason


def screen(name, country=None, user_id=None, subject_type='user',
           context='manual'):
    """
    Screen a name against the sanctions data.
    Returns the SanctionsScreen row.
    """
    subject_lower = (name or '').strip().lower()
    if not subject_lower:
        row = SanctionsScreen(
            user_id=user_id, subject_name=name or '', subject_country=country,
            subject_type=subject_type, context=context,
            status=SanctionsStatus.CLEAR, hit_count=0, best_score=0.0,
        )
        db.session.add(row); db.session.commit()
        return row

    # Create the screen record first so we can attach hits
    screen_row = SanctionsScreen(
        user_id=user_id,
        subject_name=name,
        subject_country=country,
        subject_type=subject_type,
        context=context,
        status=SanctionsStatus.CLEAR,
    )
    db.session.add(screen_row)
    db.session.flush()

    candidates = _candidate_entities(subject_lower, country=country)
    hits = []
    best_score = 0.0
    for ent in candidates:
        score, matched_name, reason = _fuzzy_match(subject_lower, ent)
        if score >= THRESHOLD_REVIEW:
            hits.append((score, ent, matched_name, reason))
            if score > best_score:
                best_score = score

    # Sort by score desc, keep top N
    hits.sort(key=lambda t: t[0], reverse=True)
    hits = hits[:MAX_HITS_PER_SCREEN]

    for score, ent, matched_name, reason in hits:
        db.session.add(SanctionsHit(
            screen_id=screen_row.id,
            entity_id=ent.id,
            score=score,
            matched_name=matched_name,
            reason=reason,
        ))

    if hits:
        screen_row.status = SanctionsStatus.REVIEW
        screen_row.hit_count = len(hits)
        screen_row.best_score = best_score
    else:
        screen_row.status = SanctionsStatus.CLEAR
        screen_row.hit_count = 0
        screen_row.best_score = 0.0

    db.session.commit()
    return screen_row


# ----------------------------------------------------------------- stats
def stats():
    total = SanctionsEntity.query.count()
    by_type = dict(
        db.session.query(SanctionsEntity.list_type, db.func.count())
        .group_by(SanctionsEntity.list_type).all()
    )
    open_review = SanctionsScreen.query.filter_by(status=SanctionsStatus.REVIEW).count()
    blocked = SanctionsScreen.query.filter_by(status=SanctionsStatus.BLOCKED).count()
    return {
        'entities': total,
        'by_type': {str(k.value if k else 'other'): v for k, v in by_type.items()},
        'screens_in_review': open_review,
        'screens_blocked': blocked,
    }
