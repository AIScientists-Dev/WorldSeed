#!/usr/bin/env python3
"""Search one supported source for one entity/query and append candidates to a bundle manifest."""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


USER_AGENT = "WorldSeedAssetSourcing/0.2 (+https://github.com/AIScientists-Dev/WorldSeed)"
DEFAULT_LIMIT = 8
DETAIL_LIMIT = 10
DOWNLOAD_MIN_BYTES = 1_500
HTTP_TIMEOUT = 30
HTTP_RETRIES = 3

SOURCE_LABELS = {
    "met": "The Met",
    "aic": "Art Institute of Chicago",
    "cleveland": "Cleveland Museum of Art",
    "vam": "V&A",
    "wellcome": "Wellcome Collection",
    "ycba": "Yale Center for British Art",
    "walters": "Walters Art Museum",
    "wikimedia": "Wikimedia Commons",
    "nasa": "NASA",
    "openverse": "Openverse",
}

HOST_MIN_INTERVAL_MS = {
    "api.openverse.org": 150,
    "commons.wikimedia.org": 200,
    "collectionapi.metmuseum.org": 300,
    "api.wellcomecollection.org": 250,
    "iiif.wellcomecollection.org": 150,
    "api.artic.edu": 200,
    "openaccess-api.clevelandart.org": 200,
    "images-api.nasa.gov": 250,
    "api.vam.ac.uk": 250,
    "collections.britishart.yale.edu": 400,
    "art.thewalters.org": 400,
}

ROLE_HINTS: dict[str, dict[str, tuple[str, ...]]] = {
    "zone": {
        "adjacent": ("interior", "room", "hall", "house", "salon", "parlor", "drawing room", "garden", "library"),
        "vibe": ("painting", "print", "view", "chamber", "gallery"),
    },
    "agent": {
        "adjacent": ("portrait", "figure", "woman", "man", "person", "lady", "gentleman", "performer", "scholar"),
        "vibe": ("painting", "study", "scene", "dress", "costume", "performance", "music", "stage"),
    },
    "item": {
        "adjacent": ("object", "artifact", "ornament", "still life", "instrument", "vessel", "paper", "jewel"),
        "vibe": ("engraving", "drawing", "print", "design"),
    },
    "symbolic": {
        "adjacent": ("illustration", "engraving", "print", "painting", "scene", "bird", "animal", "celestial"),
        "vibe": ("symbol", "allegory", "myth", "night", "moon", "star"),
    },
}


def ms_since(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return html_lib.unescape(re.sub(r"\s+", " ", value)).strip()


def normalize_text(value: str) -> str:
    value = strip_html(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def phrase_in_text(text: str, phrase: str) -> bool:
    normalized_text = f" {normalize_text(text)} "
    normalized_phrase = f" {normalize_text(phrase)} "
    return normalized_phrase in normalized_text


def entity_terms(entity: dict[str, Any]) -> list[str]:
    label = str(entity.get("label") or entity.get("id") or "").strip()
    normalized = normalize_text(label)
    tokens = [token for token in normalized.split() if len(token) >= 3]
    terms: list[str] = []
    if normalized:
        terms.append(normalized)
    for token in tokens:
        if token not in terms:
            terms.append(token)
    return terms


def _infer_query_type(query_type: str, query: str, entity: dict[str, Any]) -> str:
    if query_type:
        return query_type
    role = str(entity.get("role") or "").strip().lower()
    label = str(entity.get("label") or entity.get("id") or "").strip().lower()
    lowered = query.lower()
    if role == "zone" and any(term in lowered for term in ("interior", "room", "hall", "gallery", "salon")):
        return "related"
    if role == "agent" and any(term in lowered for term in ("portrait", "figure", "singer", "performer", "scholar")):
        return "related"
    if role == "symbolic" and any(term in lowered for term in ("print", "illustration", "engraving", "symbol", "allegory")):
        return "vibe"
    if lowered.strip() == label:
        return "literal"
    return "literal"


def _guess_extension(url: str, headers: dict[str, str]) -> str:
    content_type = headers.get("content-type", "").lower()
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    if "gif" in content_type:
        return ".gif"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    path = urllib.parse.urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


def _is_pdf(url: str, headers: dict[str, str]) -> bool:
    if "pdf" in headers.get("content-type", "").lower():
        return True
    return urllib.parse.urlparse(url).path.lower().endswith(".pdf")


def _candidate_key(entity_id: str, source: str, title: str, source_url: str) -> str:
    return "::".join(
        (
            entity_id.strip(),
            source.strip().lower(),
            normalize_text(title),
            normalize_text(source_url),
        )
    )


@dataclass
class SearchCandidate:
    source: str
    title: str
    creator: str
    date: str
    image_url: str
    download_url: str
    source_url: str
    rights_text: str
    extra: dict[str, Any]


class Fetcher:
    def __init__(self) -> None:
        self.context = self._make_context()
        self.last_request_at: dict[str, float] = {}

    @staticmethod
    def _make_context() -> ssl.SSLContext:
        try:
            import certifi  # type: ignore

            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            return ssl._create_unverified_context()

    def _request(
        self,
        url: str,
        *,
        data: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[bytes, dict[str, str], int]:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        }
        if extra_headers:
            headers.update(extra_headers)
        request = urllib.request.Request(url, data=data, headers=headers)
        host = urllib.parse.urlparse(url).netloc.lower()
        min_interval_ms = HOST_MIN_INTERVAL_MS.get(host, 0)
        last = self.last_request_at.get(host, 0.0)
        if min_interval_ms:
            elapsed_ms = int((time.perf_counter() - last) * 1000)
            if elapsed_ms < min_interval_ms:
                time.sleep((min_interval_ms - elapsed_ms) / 1000)

        transient_codes = {403, 429, 500, 502, 503, 504}
        last_error: Exception | None = None
        for attempt in range(HTTP_RETRIES):
            start = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT, context=self.context) as response:
                    payload = response.read()
                    response_headers = {k.lower(): v for k, v in response.headers.items()}
                self.last_request_at[host] = time.perf_counter()
                return payload, response_headers, ms_since(start)
            except urllib.error.HTTPError as exc:
                self.last_request_at[host] = time.perf_counter()
                last_error = exc
                if exc.code not in transient_codes or attempt == HTTP_RETRIES - 1:
                    raise
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                sleep_s = float(retry_after) if retry_after and retry_after.isdigit() else (attempt + 1) * 2
                time.sleep(sleep_s)
            except Exception as exc:
                self.last_request_at[host] = time.perf_counter()
                last_error = exc
                if attempt == HTTP_RETRIES - 1:
                    raise
                time.sleep((attempt + 1) * 1.5)
        assert last_error is not None
        raise last_error

    def json(self, url: str, *, extra_headers: dict[str, str] | None = None) -> tuple[dict[str, Any], int]:
        payload, _, elapsed = self._request(url, extra_headers=extra_headers)
        return json.loads(payload.decode("utf-8")), elapsed

    def bytes(self, url: str) -> tuple[bytes, dict[str, str], int]:
        return self._request(url)

    def text(self, url: str, *, extra_headers: dict[str, str] | None = None) -> tuple[str, int]:
        payload, _, elapsed = self._request(url, extra_headers=extra_headers)
        return payload.decode("utf-8", errors="replace"), elapsed


def openverse_search(fetcher: Fetcher, query: str, limit: int) -> tuple[list[SearchCandidate], int, int]:
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode({"q": query, "page_size": limit})
    payload, search_ms = fetcher.json(url)
    candidates: list[SearchCandidate] = []
    for item in payload.get("results", []):
        if not isinstance(item, dict):
            continue
        download_url = str(item.get("thumbnail") or item.get("url") or "").strip()
        image_url = str(item.get("url") or download_url).strip()
        if not download_url:
            continue
        rights = " ".join(
            part
            for part in (str(item.get("license") or "").strip(), str(item.get("license_version") or "").strip())
            if part
        ).strip()
        candidates.append(
            SearchCandidate(
                source="openverse",
                title=str(item.get("title") or "Untitled").strip(),
                creator=str(item.get("creator") or item.get("source") or "Unknown").strip(),
                date="",
                image_url=image_url,
                download_url=download_url,
                source_url=str(item.get("foreign_landing_url") or "").strip(),
                rights_text=rights or "Unknown",
                extra={"provider_source": str(item.get("source") or "").strip()},
            )
        )
    return candidates, search_ms, 0


def wikimedia_search(fetcher: Fetcher, query: str, limit: int) -> tuple[list[SearchCandidate], int, int]:
    search_url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srnamespace": "6",
            "format": "json",
            "srlimit": str(limit),
            "origin": "*",
        }
    )
    payload, search_ms = fetcher.json(search_url)
    titles = [
        str(item.get("title") or "").strip()
        for item in payload.get("query", {}).get("search", [])
        if isinstance(item, dict)
    ]
    hydration_ms = 0
    candidates: list[SearchCandidate] = []
    for title in titles:
        detail_url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
            {
                "action": "query",
                "titles": title,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "format": "json",
                "origin": "*",
            }
        )
        try:
            detail_payload, detail_ms = fetcher.json(detail_url)
        except Exception:
            continue
        hydration_ms += detail_ms
        pages = detail_payload.get("query", {}).get("pages", {})
        if not isinstance(pages, dict):
            continue
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            imageinfo = page.get("imageinfo")
            if not isinstance(imageinfo, list) or not imageinfo:
                continue
            info = imageinfo[0]
            if not isinstance(info, dict):
                continue
            ext = info.get("extmetadata") or {}
            if not isinstance(ext, dict):
                ext = {}
            filename = title.removeprefix("File:")
            download_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(filename)}?width=900"
            rights = strip_html(str(ext.get("LicenseShortName", {}).get("value", ""))) or "Unknown"
            creator = strip_html(str(ext.get("Artist", {}).get("value", ""))) or "Unknown"
            date = strip_html(str(ext.get("DateTimeOriginal", {}).get("value", "")))
            object_name = strip_html(str(ext.get("ObjectName", {}).get("value", ""))) or filename.rsplit(".", 1)[0]
            candidates.append(
                SearchCandidate(
                    source="wikimedia",
                    title=object_name,
                    creator=creator,
                    date=date,
                    image_url=str(info.get("url") or "").strip(),
                    download_url=download_url,
                    source_url=str(info.get("descriptionurl") or "").strip(),
                    rights_text=rights,
                    extra={"filename": filename},
                )
            )
            if len(candidates) >= limit:
                return candidates, search_ms, hydration_ms
    return candidates, search_ms, hydration_ms


def met_search(fetcher: Fetcher, query: str, limit: int) -> tuple[list[SearchCandidate], int, int]:
    search_url = "https://collectionapi.metmuseum.org/public/collection/v1/search?" + urllib.parse.urlencode(
        {"hasImages": "true", "q": query}
    )
    payload, search_ms = fetcher.json(search_url)
    ids = payload.get("objectIDs") or []
    if not isinstance(ids, list):
        return [], search_ms, 0
    hydration_ms = 0
    candidates: list[SearchCandidate] = []
    for object_id in ids[:DETAIL_LIMIT]:
        detail_url = f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"
        try:
            detail, detail_ms = fetcher.json(detail_url)
        except Exception:
            continue
        hydration_ms += detail_ms
        if not detail.get("isPublicDomain") or not detail.get("primaryImageSmall"):
            continue
        candidates.append(
            SearchCandidate(
                source="met",
                title=str(detail.get("title") or "Untitled").strip(),
                creator=str(detail.get("artistDisplayName") or "Unknown").strip(),
                date=str(detail.get("objectDate") or "").strip(),
                image_url=str(detail.get("primaryImage") or detail.get("primaryImageSmall") or "").strip(),
                download_url=str(detail.get("primaryImageSmall") or "").strip(),
                source_url=str(detail.get("objectURL") or "").strip(),
                rights_text="Public Domain (Met Open Access)",
                extra={"object_id": detail.get("objectID")},
            )
        )
        if len(candidates) >= limit:
            break
    return candidates, search_ms, hydration_ms


def wellcome_search(fetcher: Fetcher, query: str, limit: int) -> tuple[list[SearchCandidate], int, int]:
    url = "https://api.wellcomecollection.org/catalogue/v2/images?" + urllib.parse.urlencode(
        {"query": query, "pageSize": str(limit)}
    )
    payload, search_ms = fetcher.json(url)
    candidates: list[SearchCandidate] = []
    for item in payload.get("results", []):
        if not isinstance(item, dict):
            continue
        thumbnail = item.get("thumbnail") or {}
        source = item.get("source") or {}
        locations = item.get("locations") or []
        if not isinstance(thumbnail, dict) or not isinstance(source, dict):
            continue
        license_label = ""
        if isinstance(locations, list):
            for location in locations:
                if not isinstance(location, dict):
                    continue
                license_label = str(location.get("license", {}).get("label") or "").strip()
                if license_label:
                    break
        thumb_url = str(thumbnail.get("url") or "").strip()
        if not thumb_url:
            continue
        iiif_base = thumb_url.replace("/info.json", "")
        contributors = source.get("contributors") or []
        creator = "Unknown"
        if isinstance(contributors, list) and contributors:
            contributor = contributors[0]
            if isinstance(contributor, dict):
                agent = contributor.get("agent") or {}
                if isinstance(agent, dict):
                    creator = str(agent.get("label") or "Unknown").strip()
        source_id = str(source.get("id") or "").strip()
        candidates.append(
            SearchCandidate(
                source="wellcome",
                title=str(source.get("title") or "Untitled").strip(),
                creator=creator,
                date="",
                image_url=iiif_base + "/full/1200,/0/default.jpg",
                download_url=iiif_base + "/full/800,/0/default.jpg",
                source_url=f"https://wellcomecollection.org/works/{source_id}" if source_id else "",
                rights_text=license_label or "Unknown",
                extra={"wellcome_id": source_id},
            )
        )
    return candidates, search_ms, 0


def aic_search(fetcher: Fetcher, query: str, limit: int) -> tuple[list[SearchCandidate], int, int]:
    url = "https://api.artic.edu/api/v1/artworks/search?" + urllib.parse.urlencode(
        {
            "q": query,
            "query[term][is_public_domain]": "true",
            "fields": "id,title,artist_display,date_display,image_id",
            "limit": str(limit),
        }
    )
    payload, search_ms = fetcher.json(url)
    candidates: list[SearchCandidate] = []
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        image_id = str(item.get("image_id") or "").strip()
        if not image_id:
            continue
        candidates.append(
            SearchCandidate(
                source="aic",
                title=str(item.get("title") or "Untitled").strip(),
                creator=str(item.get("artist_display") or "Unknown").splitlines()[0].strip(),
                date=str(item.get("date_display") or "").strip(),
                image_url=f"https://www.artic.edu/iiif/2/{image_id}/full/1200,/0/default.jpg",
                download_url=f"https://www.artic.edu/iiif/2/{image_id}/full/800,/0/default.jpg",
                source_url=f"https://www.artic.edu/artworks/{item.get('id')}",
                rights_text="Public Domain (AIC)",
                extra={"image_id": image_id},
            )
        )
    return candidates, search_ms, 0


def cleveland_search(fetcher: Fetcher, query: str, limit: int) -> tuple[list[SearchCandidate], int, int]:
    url = "https://openaccess-api.clevelandart.org/api/artworks/?" + urllib.parse.urlencode(
        {"q": query, "has_image": "1", "limit": str(limit)}
    )
    payload, search_ms = fetcher.json(url)
    candidates: list[SearchCandidate] = []
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        images = item.get("images") or {}
        if not isinstance(images, dict):
            images = {}
        web_image = images.get("web") or {}
        print_image = images.get("print") or {}
        if not isinstance(web_image, dict):
            web_image = {}
        if not isinstance(print_image, dict):
            print_image = {}
        download_url = str(web_image.get("url") or "").strip()
        image_url = str(print_image.get("url") or download_url).strip()
        if not download_url:
            continue
        creators = item.get("creators") or []
        creator = "Unknown"
        if isinstance(creators, list) and creators:
            creator_entry = creators[0]
            if isinstance(creator_entry, dict):
                creator = str(creator_entry.get("description") or "Unknown").strip()
        candidates.append(
            SearchCandidate(
                source="cleveland",
                title=str(item.get("title") or "Untitled").strip(),
                creator=creator,
                date=str(item.get("creation_date") or "").strip(),
                image_url=image_url,
                download_url=download_url,
                source_url=f"https://www.clevelandart.org/art/{item.get('id')}",
                rights_text="Open Access / CC0",
                extra={"id": item.get("id")},
            )
        )
    return candidates, search_ms, 0


def nasa_search(fetcher: Fetcher, query: str, limit: int) -> tuple[list[SearchCandidate], int, int]:
    url = "https://images-api.nasa.gov/search?" + urllib.parse.urlencode({"q": query, "media_type": "image"})
    payload, search_ms = fetcher.json(url)
    items = payload.get("collection", {}).get("items", [])
    if not isinstance(items, list):
        items = []
    candidates: list[SearchCandidate] = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        links = item.get("links") or []
        data = item.get("data") or []
        if not isinstance(links, list) or not links or not isinstance(data, list) or not data:
            continue
        link = links[0] if isinstance(links[0], dict) else {}
        meta = data[0] if isinstance(data[0], dict) else {}
        thumb = str(link.get("href") or "").strip()
        if not thumb:
            continue
        original = thumb.replace("~thumb", "~orig")
        candidates.append(
            SearchCandidate(
                source="nasa",
                title=str(meta.get("title") or "Untitled").strip(),
                creator=str(meta.get("center") or meta.get("photographer") or "NASA").strip(),
                date=str(meta.get("date_created") or "").strip(),
                image_url=original,
                download_url=thumb,
                source_url=str(item.get("href") or "").strip(),
                rights_text="Public Domain (NASA)",
                extra={},
            )
        )
    return candidates, search_ms, 0


def vam_search(fetcher: Fetcher, query: str, limit: int) -> tuple[list[SearchCandidate], int, int]:
    url = "https://api.vam.ac.uk/v2/objects/search?" + urllib.parse.urlencode(
        {"q": query, "images_exist": "1", "page_size": str(limit)}
    )
    payload, search_ms = fetcher.json(url)
    records = payload.get("records", [])
    if not isinstance(records, list):
        records = []
    candidates: list[SearchCandidate] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        images = item.get("_images") or {}
        if not isinstance(images, dict):
            images = {}
        iiif = str(images.get("_iiif_image_base_url") or "").strip()
        if not iiif:
            continue
        system_number = str(item.get("systemNumber") or "").strip()
        maker = item.get("_primaryMaker") or {}
        if not isinstance(maker, dict):
            maker = {}
        candidates.append(
            SearchCandidate(
                source="vam",
                title=str(item.get("_primaryTitle") or "Untitled").strip(),
                creator=str(maker.get("name") or "Unknown").strip(),
                date=str(item.get("_primaryDate") or "").strip(),
                image_url=iiif + "/full/1200,/0/default.jpg",
                download_url=iiif + "/full/800,/0/default.jpg",
                source_url=f"https://collections.vam.ac.uk/item/{system_number}" if system_number else "",
                rights_text="V&A collection item",
                extra={"system_number": system_number},
            )
        )
    return candidates, search_ms, 0


def ycba_search(fetcher: Fetcher, query: str, limit: int) -> tuple[list[SearchCandidate], int, int]:
    url = "https://collections.britishart.yale.edu/?" + urllib.parse.urlencode({"q": query})
    start = time.perf_counter()
    result = subprocess.run(
        ["curl", "-sS", "--max-time", str(HTTP_TIMEOUT), url],
        capture_output=True,
        text=True,
        check=False,
    )
    search_ms = ms_since(start)
    if result.returncode != 0:
        stderr = result.stderr.strip() or f"curl exited {result.returncode}"
        raise RuntimeError(f"YCBA curl fetch failed: {stderr}")
    text = result.stdout
    candidates: list[SearchCandidate] = []
    for chunk in text.split('<li class="y-card-layout__item">')[1:]:
        body = chunk.split("</li>", 1)[0]
        href_match = re.search(r'<a class="y-card-basic "\s+href="(?P<href>[^"]+)">', body)
        thumb_match = re.search(
            r'src="(?P<src>https://media\.collections\.yale\.edu/thumbnail/ycba/[^"]+)"[^>]*alt="(?P<alt>[^"]+)"',
            body,
            re.S,
        )
        title_match = re.search(r'<p class="y-card-basic__title">(?P<title>.*?)</p>', body, re.S)
        creator_match = re.search(r'<div class="y-card-basic__content-wrapper">.*?<p>(?P<creator>.*?)</p>', body, re.S)
        year_match = re.search(r'<p class="y-card-basic__year">(?P<year>.*?)</p>', body, re.S)
        if not thumb_match or not href_match:
            continue
        href = html_lib.unescape(href_match.group("href")).strip()
        title = strip_html(title_match.group("title")) if title_match else strip_html(thumb_match.group("alt"))
        creator = strip_html(creator_match.group("creator")) if creator_match else "Unknown"
        year = strip_html(year_match.group("year")) if year_match else ""
        thumb_url = html_lib.unescape(thumb_match.group("src")).strip()
        page_url = urllib.parse.urljoin("https://collections.britishart.yale.edu/", href)
        candidates.append(
            SearchCandidate(
                source="ycba",
                title=title or "Untitled",
                creator=creator or "Unknown",
                date=year,
                image_url=thumb_url,
                download_url=thumb_url,
                source_url=page_url,
                rights_text="Unknown / item page required",
                extra={"source_type": "html_search"},
            )
        )
        if len(candidates) >= limit:
            break
    return candidates, search_ms, 0


def walters_search(fetcher: Fetcher, query: str, limit: int) -> tuple[list[SearchCandidate], int, int]:
    url = "https://art.thewalters.org/search/?" + urllib.parse.urlencode({"q": query})
    text, search_ms = fetcher.text(url)
    card_pattern = re.compile(
        r'<div class="cards__item">\s*<div class="card">(?P<body>.*?)</div><!-- /\.card -->\s*</div><!-- /\.cards__item -->',
        re.S,
    )
    candidates: list[SearchCandidate] = []
    for match in card_pattern.finditer(text):
        body = match.group("body")
        thumb_match = re.search(
            r'src="(?P<src>https://art\.thewalters\.org/images/art/thumbnails/[^"]+)"\s+alt="(?P<alt>[^"]+)"',
            body,
            re.S,
        )
        title_match = re.search(r"<h3>(?P<title>.*?)</h3>", body, re.S)
        creator_match = re.search(r'<div class="card__author">\s*(?P<creator>.*?)\s*</div>', body, re.S)
        date_match = re.search(r'<div class="card__date">(?P<date>.*?)</div>', body, re.S)
        href_match = re.search(r'<a href="(?P<href>https://art\.thewalters\.org/object/[^"]+/)" class="card__link">', body)
        if not thumb_match or not href_match:
            continue
        thumb_url = html_lib.unescape(thumb_match.group("src")).strip()
        title = strip_html(title_match.group("title")) if title_match else strip_html(thumb_match.group("alt"))
        creator = strip_html(creator_match.group("creator")) if creator_match else "Unknown"
        date = strip_html(date_match.group("date")) if date_match else ""
        candidates.append(
            SearchCandidate(
                source="walters",
                title=title or "Untitled",
                creator=creator or "Unknown",
                date=date,
                image_url=thumb_url,
                download_url=thumb_url,
                source_url=html_lib.unescape(href_match.group("href")).strip(),
                rights_text="Unknown / item page required",
                extra={"source_type": "html_search"},
            )
        )
        if len(candidates) >= limit:
            break
    return candidates, search_ms, 0


SEARCHERS: dict[str, Callable[[Fetcher, str, int], tuple[list[SearchCandidate], int, int]]] = {
    "aic": aic_search,
    "cleveland": cleveland_search,
    "met": met_search,
    "nasa": nasa_search,
    "openverse": openverse_search,
    "vam": vam_search,
    "walters": walters_search,
    "wellcome": wellcome_search,
    "wikimedia": wikimedia_search,
    "ycba": ycba_search,
}


def classify_fit(entity: dict[str, Any], candidate: SearchCandidate, query_type: str) -> tuple[str, str]:
    role = str(entity.get("role") or "").strip().lower()
    terms = entity_terms(entity)
    if not terms:
        return "miss", "entity has no usable label terms"

    title = strip_html(candidate.title)
    creator = strip_html(candidate.creator)
    title_text = normalize_text(title)
    creator_text = normalize_text(creator)
    full_text = normalize_text(f"{title} {creator}")
    role_hints = ROLE_HINTS.get(role, ROLE_HINTS["item"])

    exact_hits = [term for term in terms if phrase_in_text(title_text, term)]
    creator_hits = [term for term in terms if phrase_in_text(creator_text, term) and term not in exact_hits]
    adjacent_hits = [term for term in role_hints["adjacent"] if phrase_in_text(full_text, term)]
    vibe_hits = [term for term in role_hints["vibe"] if phrase_in_text(full_text, term)]

    if exact_hits:
        label = "exact"
    elif adjacent_hits:
        label = "adjacent"
    elif vibe_hits:
        label = "vibe"
    else:
        label = "miss"

    bits: list[str] = []
    if exact_hits:
        bits.append(f"title matches {', '.join(exact_hits[:3])}")
    elif adjacent_hits:
        bits.append(f"metadata suggests {', '.join(adjacent_hits[:3])}")
    elif vibe_hits:
        bits.append(f"metadata suggests {', '.join(vibe_hits[:3])}")
    else:
        bits.append("weak metadata match")
    if creator_hits:
        bits.append(f"creator also contains {', '.join(creator_hits[:2])}")
    if query_type:
        bits.append(f"{query_type} query")
    return label, "; ".join(bits)


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


@contextmanager
def _manifest_lock(manifest_path: Path):
    import fcntl

    lock_path = manifest_path.with_suffix(manifest_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _find_entity(manifest: dict[str, Any], entity_id: str) -> dict[str, Any]:
    entities = manifest.get("entities", [])
    if not isinstance(entities, list):
        raise ValueError("manifest.entities must be a list")
    for entity in entities:
        if isinstance(entity, dict) and str(entity.get("id", "")).strip() == entity_id:
            return entity
    raise ValueError(f"Entity not found in manifest: {entity_id}")


def _download_candidate(
    fetcher: Fetcher,
    bundle_dir: Path,
    entity_id: str,
    source: str,
    index: int,
    download_url: str,
) -> tuple[str, int, str]:
    payload, headers, elapsed = fetcher.bytes(download_url)
    if _is_pdf(download_url, headers):
        raise ValueError("download resolved to PDF")
    if len(payload) < DOWNLOAD_MIN_BYTES:
        raise ValueError(f"download too small ({len(payload)} bytes)")
    ext = _guess_extension(download_url, headers)
    image_dir = bundle_dir / "images" / entity_id
    image_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{source}_{index:02d}{ext}"
    out_path = image_dir / filename
    out_path.write_bytes(payload)
    return out_path.as_posix(), elapsed, headers.get("content-type", "")


def _append_run(manifest: dict[str, Any], run_summary: dict[str, Any]) -> None:
    runs = manifest.setdefault("search_runs", [])
    if not isinstance(runs, list):
        manifest["search_runs"] = []
        runs = manifest["search_runs"]
    runs.append(run_summary)


def _merge_candidates(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in existing + incoming:
        if not isinstance(candidate, dict):
            continue
        key = _candidate_key(
            str(candidate.get("entity_id", "")),
            str(candidate.get("source", "")),
            str(candidate.get("title", "")),
            str(candidate.get("source_url", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(candidate)
    return merged


def _merge_runs(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for run in existing + incoming:
        if not isinstance(run, dict):
            continue
        key = json.dumps(
            {
                "entity_id": run.get("entity_id"),
                "source": run.get("source"),
                "query": run.get("query"),
                "query_type": run.get("query_type"),
                "query_round": run.get("query_round"),
                "source_tier": run.get("source_tier"),
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(run)
    return merged


def _merge_manifest_updates(latest: dict[str, Any], updated: dict[str, Any]) -> dict[str, Any]:
    latest_candidates = latest.get("candidates", [])
    updated_candidates = updated.get("candidates", [])
    latest_runs = latest.get("search_runs", [])
    updated_runs = updated.get("search_runs", [])
    if not isinstance(latest_candidates, list):
        latest_candidates = []
    if not isinstance(updated_candidates, list):
        updated_candidates = []
    if not isinstance(latest_runs, list):
        latest_runs = []
    if not isinstance(updated_runs, list):
        updated_runs = []

    merged = dict(latest)
    merged["scene_id"] = latest.get("scene_id") or updated.get("scene_id")
    merged["premise"] = latest.get("premise") or updated.get("premise", "")
    merged["entities"] = latest.get("entities") or updated.get("entities", [])
    merged["recommendation_mode"] = latest.get("recommendation_mode") or updated.get("recommendation_mode", "unreviewed")
    merged["candidates"] = _merge_candidates(latest_candidates, updated_candidates)
    merged["search_runs"] = _merge_runs(latest_runs, updated_runs)
    if updated.get("reviewer") and not merged.get("reviewer"):
        merged["reviewer"] = updated.get("reviewer")
    return merged


def append_candidates(
    manifest: dict[str, Any],
    *,
    bundle_dir: Path,
    entity: dict[str, Any],
    source: str,
    query: str,
    query_type: str,
    query_round: int,
    source_tier: str,
    limit: int,
    download: bool,
) -> dict[str, Any]:
    fetcher = Fetcher()
    start = time.perf_counter()
    searcher = SEARCHERS.get(source)
    if searcher is None:
        raise ValueError(f"Unsupported source: {source}")

    results, search_ms, hydration_ms = searcher(fetcher, query, limit)
    entity_id = str(entity.get("id") or "").strip()
    existing_keys = {
        _candidate_key(
            str(item.get("entity_id", "")),
            str(item.get("source", "")),
            str(item.get("title", "")),
            str(item.get("source_url", "")),
        )
        for item in manifest.get("candidates", [])
        if isinstance(item, dict)
    }

    appended = 0
    downloaded = 0
    skipped_dupes = 0
    errors: list[str] = []
    candidates = manifest.setdefault("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("manifest.candidates must be a list")

    for raw_index, result in enumerate(results, start=1):
        if not result.download_url and not result.image_url:
            continue
        key = _candidate_key(entity_id, source, result.title, result.source_url)
        if key in existing_keys:
            skipped_dupes += 1
            continue
        download_url = result.download_url or result.image_url
        local_image_path = ""
        download_ms = 0
        download_error = ""
        content_type = ""
        if download:
            try:
                local_image_path, download_ms, content_type = _download_candidate(
                    fetcher, bundle_dir, entity_id, source, raw_index, download_url
                )
                downloaded += 1
            except Exception as exc:
                download_error = str(exc)
                errors.append(f"{result.title}: {download_error}")

        search_fit_label, search_fit_note = classify_fit(entity, result, query_type)
        candidate = {
            "entity_id": entity_id,
            "entity_label": str(entity.get("label") or entity_id),
            "entity_role": str(entity.get("role") or ""),
            "source": source,
            "source_label": SOURCE_LABELS.get(source, source),
            "query": query,
            "query_type": query_type,
            "query_round": query_round,
            "source_tier": source_tier,
            "latency_search_ms": search_ms,
            "latency_hydration_ms": hydration_ms,
            "latency_download_ms": download_ms,
            "title": result.title,
            "creator": result.creator,
            "date": result.date,
            "image_url": result.image_url,
            "download_url": result.download_url,
            "source_url": result.source_url,
            "local_image_path": local_image_path,
            "rights_text": result.rights_text,
            "search_fit_label": search_fit_label,
            "search_fit_note": search_fit_note,
            "download_error": download_error,
            "content_type": content_type,
            "extra": result.extra,
        }
        candidates.append(candidate)
        existing_keys.add(key)
        appended += 1

    manifest.setdefault("recommendation_mode", "unreviewed")
    summary = {
        "entity_id": entity_id,
        "source": source,
        "query": query,
        "query_type": query_type,
        "query_round": query_round,
        "source_tier": source_tier,
        "requested_limit": limit,
        "result_count": len(results),
        "appended_count": appended,
        "downloaded_count": downloaded,
        "skipped_duplicates": skipped_dupes,
        "search_ms": search_ms,
        "hydration_ms": hydration_ms,
        "wall_time_ms": ms_since(start),
        "errors": errors,
    }
    _append_run(manifest, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Search one source for one entity/query and append candidates")
    parser.add_argument("--manifest", required=True, help="Bundle manifest JSON to append into")
    parser.add_argument("--entity-id", required=True, help="Entity id in the manifest")
    parser.add_argument("--source", required=True, choices=sorted(SEARCHERS.keys()), help="Supported source id")
    parser.add_argument("--query", required=True, help="Exact query string to run")
    parser.add_argument("--query-type", default="", help="Query mode label, e.g. literal/related/vibe")
    parser.add_argument("--query-round", type=int, default=1, help="Query rewrite round number")
    parser.add_argument("--source-tier", default="default", help="Tier label to store in the manifest")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Max candidates to request")
    parser.add_argument(
        "--download",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Download review-size images for appended candidates",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    bundle_dir = manifest_path.parent
    manifest = _load_json(manifest_path)
    entity = _find_entity(manifest, args.entity_id)
    query_type = _infer_query_type(args.query_type, args.query, entity)
    summary = append_candidates(
        manifest,
        bundle_dir=bundle_dir,
        entity=entity,
        source=args.source,
        query=args.query,
        query_type=query_type,
        query_round=max(1, args.query_round),
        source_tier=args.source_tier,
        limit=max(1, args.limit),
        download=bool(args.download),
    )
    with _manifest_lock(manifest_path):
        latest_manifest = _load_json(manifest_path)
        merged_manifest = _merge_manifest_updates(latest_manifest, manifest)
        _save_json(manifest_path, merged_manifest)
    json.dump(summary, sys.stdout, indent=2, ensure_ascii=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
